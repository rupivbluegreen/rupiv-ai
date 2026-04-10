"""Analytics endpoints — MRR, ARR, churn, payment costs, outcomes, cohorts, routing."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Query
from rupiv.api.middleware.auth import get_current_api_key
from rupiv.models.api_key import ApiKey
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.analytics.cohort import CohortEntry, calculate_cohorts
from rupiv.analytics.mrr_arr import MRRResult, calculate_churn_rate, calculate_mrr
from rupiv.analytics.outcome_metrics import calculate_outcome_metrics
from rupiv.analytics.payment_costs import calculate_payment_costs, get_cost_comparison
from rupiv.analytics.routing_optimizer import get_recommendations
from rupiv.db import get_db

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/analytics", tags=["analytics"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class MRRResponse(BaseModel):
    """Monthly Recurring Revenue breakdown."""

    model_config = ConfigDict(from_attributes=True)

    total_mrr: Decimal
    new_mrr: Decimal
    expansion_mrr: Decimal
    contraction_mrr: Decimal
    churned_mrr: Decimal
    net_new_mrr: Decimal
    customer_count: int
    period: str


class ARRResponse(BaseModel):
    """Annual Recurring Revenue."""

    arr: Decimal
    based_on_mrr: Decimal
    period: str


class ChurnResponse(BaseModel):
    """Customer churn rate for a period."""

    churn_rate: Decimal
    period_start: date
    period_end: date


class MethodCostResponse(BaseModel):
    """Cost breakdown for a single payment method."""

    model_config = ConfigDict(from_attributes=True)

    method: str
    count: int
    volume: Decimal
    fees: Decimal
    unit_fee: Decimal | None
    rate_pct: Decimal | None


class PaymentCostResponse(BaseModel):
    """Aggregated payment cost summary for a PSP."""

    psp: str
    period: str
    transaction_count: int
    total_volume: Decimal
    total_fees: Decimal
    blended_rate: Decimal
    by_method: dict[str, MethodCostResponse]


class OutcomeMetricsResponse(BaseModel):
    """Outcome billing metrics."""

    metrics: list[dict[str, Any]]


class CohortResponse(BaseModel):
    """Customer cohort retention data."""

    cohorts: list[dict[str, Any]]


class RoutingRecommendationResponse(BaseModel):
    """Payment routing recommendations with estimated savings."""

    recommendations: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/mrr", response_model=MRRResponse, summary="Get MRR breakdown")
async def get_mrr(
    as_of_date: date | None = Query(
        default=None, description="Date within the target month (default: today)",
    ),
    db: AsyncSession = Depends(get_db),
    _api_key: ApiKey = Depends(get_current_api_key),
) -> MRRResponse:
    """Return Monthly Recurring Revenue breakdown for the month containing *as_of_date*."""
    target_date = as_of_date or date.today()
    logger.info("analytics.get_mrr", as_of_date=target_date.isoformat())

    result: MRRResult = await calculate_mrr(db, target_date)
    return MRRResponse(
        total_mrr=result.total_mrr,
        new_mrr=result.new_mrr,
        expansion_mrr=result.expansion_mrr,
        contraction_mrr=result.contraction_mrr,
        churned_mrr=result.churned_mrr,
        net_new_mrr=result.net_new_mrr,
        customer_count=result.customer_count,
        period=result.period,
    )


@router.get("/arr", response_model=ARRResponse, summary="Get ARR")
async def get_arr(
    as_of_date: date | None = Query(
        default=None, description="Date within the target month (default: today)",
    ),
    db: AsyncSession = Depends(get_db),
    _api_key: ApiKey = Depends(get_current_api_key),
) -> ARRResponse:
    """Return Annual Recurring Revenue (MRR * 12)."""
    target_date = as_of_date or date.today()
    logger.info("analytics.get_arr", as_of_date=target_date.isoformat())

    mrr_result: MRRResult = await calculate_mrr(db, target_date)
    arr = mrr_result.total_mrr * Decimal("12")

    return ARRResponse(
        arr=arr,
        based_on_mrr=mrr_result.total_mrr,
        period=mrr_result.period,
    )


@router.get("/churn", response_model=ChurnResponse, summary="Get churn rate")
async def get_churn(
    period_start: date = Query(..., description="Start of the measurement period"),
    period_end: date = Query(..., description="End of the measurement period"),
    db: AsyncSession = Depends(get_db),
    _api_key: ApiKey = Depends(get_current_api_key),
) -> ChurnResponse:
    """Return customer churn rate for the given period."""
    logger.info(
        "analytics.get_churn",
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
    )

    rate = await calculate_churn_rate(db, period_start, period_end)

    return ChurnResponse(
        churn_rate=rate,
        period_start=period_start,
        period_end=period_end,
    )


@router.get(
    "/payment-costs", response_model=list[PaymentCostResponse], summary="Get payment costs",
)
async def get_payment_costs(
    period_start: date = Query(..., description="Start of the measurement period"),
    period_end: date = Query(..., description="End of the measurement period"),
    psp: str | None = Query(default=None, description="Filter by PSP name (omit for all PSPs)"),
    db: AsyncSession = Depends(get_db),
    _api_key: ApiKey = Depends(get_current_api_key),
) -> list[PaymentCostResponse]:
    """Return aggregated payment cost summaries, optionally filtered by PSP."""
    logger.info(
        "analytics.get_payment_costs",
        psp=psp,
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
    )

    if psp is not None:
        summaries = [await calculate_payment_costs(db, psp, period_start, period_end)]
    else:
        summaries = await get_cost_comparison(db, period_start, period_end)

    results: list[PaymentCostResponse] = []
    for summary in summaries:
        by_method = {
            method: MethodCostResponse.model_validate(mc)
            for method, mc in summary.by_method.items()
        }
        results.append(
            PaymentCostResponse(
                psp=summary.psp,
                period=summary.period,
                transaction_count=summary.transaction_count,
                total_volume=summary.total_volume,
                total_fees=summary.total_fees,
                blended_rate=summary.blended_rate,
                by_method=by_method,
            ),
        )

    return results


@router.get(
    "/payment-costs/recommendations",
    response_model=RoutingRecommendationResponse,
    summary="Get routing recommendations",
)
async def get_payment_cost_recommendations(
    period_start: date = Query(..., description="Start of the analysis period"),
    period_end: date = Query(..., description="End of the analysis period"),
    db: AsyncSession = Depends(get_db),
    _api_key: ApiKey = Depends(get_current_api_key),
) -> RoutingRecommendationResponse:
    """Analyze recent payments and suggest routing changes with estimated savings."""
    logger.info(
        "analytics.get_routing_recommendations",
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
    )

    recommendations = await get_recommendations(db, period_start, period_end)

    # Serialize Decimal values to float-friendly dicts for JSON response
    serialized: list[dict[str, Any]] = []
    for rec in recommendations:
        serialized.append({k: float(v) if isinstance(v, Decimal) else v for k, v in rec.items()})

    return RoutingRecommendationResponse(recommendations=serialized)


@router.get("/outcomes", response_model=OutcomeMetricsResponse, summary="Get outcome metrics")
async def get_outcomes(
    period_start: date = Query(..., description="Start of the measurement period"),
    period_end: date = Query(..., description="End of the measurement period"),
    customer_id: uuid.UUID | None = Query(default=None, description="Filter by customer"),
    metric: str | None = Query(default=None, description="Filter by metric name"),
    db: AsyncSession = Depends(get_db),
    _api_key: ApiKey = Depends(get_current_api_key),
) -> OutcomeMetricsResponse:
    """Return outcome billing metrics grouped by metric name."""
    logger.info(
        "analytics.get_outcomes",
        customer_id=str(customer_id) if customer_id else None,
        metric=metric,
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
    )

    results = await calculate_outcome_metrics(db, customer_id, metric, period_start, period_end)

    return OutcomeMetricsResponse(
        metrics=[asdict(m) for m in results],
    )


@router.get("/cohorts", response_model=CohortResponse, summary="Get cohort retention")
async def get_cohorts(
    start_month: str = Query(..., description="First cohort month (YYYY-MM format)"),
    num_months: int = Query(default=12, ge=1, le=60, description="Number of months to analyze"),
    db: AsyncSession = Depends(get_db),
    _api_key: ApiKey = Depends(get_current_api_key),
) -> CohortResponse:
    """Return customer cohort retention data."""
    logger.info(
        "analytics.get_cohorts",
        start_month=start_month,
        num_months=num_months,
    )

    entries: list[CohortEntry] = await calculate_cohorts(db, start_month, num_months)

    return CohortResponse(
        cohorts=[asdict(e) for e in entries],
    )
