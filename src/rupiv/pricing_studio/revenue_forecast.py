"""Monte Carlo revenue forecasting.

Projects MRR forward under random growth/churn variance and returns
percentile bands (P10, P50, P90).

ALL money arithmetic uses ``decimal.Decimal`` — never ``float``.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import structlog

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_TWO_PLACES = Decimal("0.01")


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ForecastResult:
    """Revenue forecast with percentile bands."""

    months: list[str]
    p10: list[Decimal]
    p50: list[Decimal]
    p90: list[Decimal]
    mean: list[Decimal]


def forecast_revenue(
    base_mrr: Decimal,
    growth_rate: Decimal,
    churn_rate: Decimal,
    months: int = 12,
    simulations: int = 1000,
    seed: int | None = None,
) -> ForecastResult:
    """Run a Monte Carlo simulation of MRR over *months* periods.

    For each simulation run, each month the MRR is projected as::

        mrr = mrr * (1 + growth_sample - churn_sample)

    where ``growth_sample`` and ``churn_sample`` are drawn from normal
    distributions centred on the provided rates with stddev = rate * 0.3.

    Args:
        base_mrr: Starting monthly recurring revenue.
        growth_rate: Expected monthly growth rate (e.g. ``0.05`` for 5%).
        churn_rate: Expected monthly churn rate (e.g. ``0.02`` for 2%).
        months: Number of months to forecast.
        simulations: Number of Monte Carlo iterations.
        seed: Optional random seed for reproducibility.

    Returns:
        A ``ForecastResult`` with month labels and P10/P50/P90/mean bands.
    """
    rng = random.Random(seed)

    # Pre-compute month labels
    today = date.today()
    month_labels: list[str] = []
    for i in range(months):
        # Advance by i months from today
        m = today.month + i
        y = today.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        month_labels.append(f"{y}-{m:02d}")

    # Run simulations — collect MRR for each month across all runs
    # all_runs[sim_index][month_index] = mrr value
    growth_float = float(growth_rate)
    churn_float = float(churn_rate)
    growth_std = growth_float * 0.3
    churn_std = churn_float * 0.3

    all_runs: list[list[Decimal]] = []

    for _ in range(simulations):
        mrr = base_mrr
        run: list[Decimal] = []
        for _m in range(months):
            g = rng.gauss(growth_float, growth_std)
            c = rng.gauss(churn_float, churn_std)
            # Clamp to prevent negative growth below -100%
            net = Decimal(str(max(1.0 + g - c, 0.0)))
            mrr = _round_money(mrr * net)
            run.append(mrr)
        all_runs.append(run)

    # Compute percentiles per month
    p10_values: list[Decimal] = []
    p50_values: list[Decimal] = []
    p90_values: list[Decimal] = []
    mean_values: list[Decimal] = []

    for month_idx in range(months):
        month_data = sorted(all_runs[s][month_idx] for s in range(simulations))

        p10_idx = max(0, int(simulations * 0.10) - 1)
        p50_idx = max(0, int(simulations * 0.50) - 1)
        p90_idx = max(0, int(simulations * 0.90) - 1)

        p10_values.append(month_data[p10_idx])
        p50_values.append(month_data[p50_idx])
        p90_values.append(month_data[p90_idx])

        total = sum(month_data, Decimal("0"))
        mean_values.append(_round_money(total / Decimal(simulations)))

    result = ForecastResult(
        months=month_labels,
        p10=p10_values,
        p50=p50_values,
        p90=p90_values,
        mean=mean_values,
    )

    log.info(
        "forecast.complete",
        base_mrr=str(base_mrr),
        growth_rate=str(growth_rate),
        churn_rate=str(churn_rate),
        months=months,
        simulations=simulations,
    )

    return result
