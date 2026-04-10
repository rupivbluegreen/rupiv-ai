"""Tests for anomaly detection logic."""

from __future__ import annotations

from decimal import Decimal

from rupiv.analytics.anomaly import AnomalyResult, check_deviation


class TestCheckDeviation:
    """Tests for the check_deviation function."""

    def test_no_historical_data_returns_no_anomaly(self) -> None:
        result = check_deviation(
            metric_name="mrr",
            current_value=Decimal("1000"),
            historical_values=[],
            threshold_pct=Decimal("20"),
            direction="drop",
        )
        assert result.is_anomaly is False

    def test_detects_drop_below_threshold(self) -> None:
        result = check_deviation(
            metric_name="mrr",
            current_value=Decimal("700"),
            historical_values=[Decimal("1000"), Decimal("1000"), Decimal("1000")],
            threshold_pct=Decimal("20"),
            direction="drop",
        )
        assert result.is_anomaly is True
        assert result.deviation_pct == Decimal("30.00")
        assert result.direction == "drop"

    def test_no_anomaly_within_threshold(self) -> None:
        result = check_deviation(
            metric_name="mrr",
            current_value=Decimal("900"),
            historical_values=[Decimal("1000"), Decimal("1000"), Decimal("1000")],
            threshold_pct=Decimal("20"),
            direction="drop",
        )
        assert result.is_anomaly is False
        assert result.deviation_pct == Decimal("10.00")

    def test_detects_spike_above_threshold(self) -> None:
        result = check_deviation(
            metric_name="usage",
            current_value=Decimal("2000"),
            historical_values=[Decimal("1000"), Decimal("1000"), Decimal("1000")],
            threshold_pct=Decimal("50"),
            direction="spike",
        )
        assert result.is_anomaly is True
        assert result.deviation_pct == Decimal("100.00")

    def test_drop_direction_ignores_spikes(self) -> None:
        result = check_deviation(
            metric_name="mrr",
            current_value=Decimal("2000"),
            historical_values=[Decimal("1000"), Decimal("1000"), Decimal("1000")],
            threshold_pct=Decimal("20"),
            direction="drop",
        )
        assert result.is_anomaly is False

    def test_spike_direction_ignores_drops(self) -> None:
        result = check_deviation(
            metric_name="usage",
            current_value=Decimal("500"),
            historical_values=[Decimal("1000"), Decimal("1000"), Decimal("1000")],
            threshold_pct=Decimal("20"),
            direction="spike",
        )
        assert result.is_anomaly is False

    def test_both_direction_detects_drop_and_spike(self) -> None:
        # Drop
        result = check_deviation(
            metric_name="metric",
            current_value=Decimal("500"),
            historical_values=[Decimal("1000")],
            threshold_pct=Decimal("20"),
            direction="both",
        )
        assert result.is_anomaly is True

        # Spike
        result = check_deviation(
            metric_name="metric",
            current_value=Decimal("1500"),
            historical_values=[Decimal("1000")],
            threshold_pct=Decimal("20"),
            direction="both",
        )
        assert result.is_anomaly is True

    def test_zero_historical_average(self) -> None:
        result = check_deviation(
            metric_name="new_metric",
            current_value=Decimal("100"),
            historical_values=[Decimal("0"), Decimal("0")],
            threshold_pct=Decimal("20"),
            direction="spike",
        )
        assert result.is_anomaly is True
        assert result.deviation_pct == Decimal("100.00")

    def test_expected_value_is_average(self) -> None:
        result = check_deviation(
            metric_name="mrr",
            current_value=Decimal("1000"),
            historical_values=[Decimal("800"), Decimal("1000"), Decimal("1200")],
            threshold_pct=Decimal("50"),
            direction="drop",
        )
        assert result.expected_value == Decimal("1000.0000")
