"""Pricing Studio API endpoints — simulation, templates, and forecasting."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.db import get_db
from rupiv.pricing_studio.revenue_forecast import forecast_revenue
from rupiv.pricing_studio.simulator import SimulationScenario, run_simulation
from rupiv.pricing_studio.templates import get_templates

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(tags=["simulate"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class SimulateRequest(BaseModel):
    """Request body for POST /v1/simulate."""

    plan_id: uuid.UUID
    scenario: SimulationScenario


class SimulateResponse(BaseModel):
    """Response body for POST /v1/simulate."""

    model_config = ConfigDict(from_attributes=True)

    current_revenue: str
    simulated_revenue: str
    delta: str
    delta_pct: str
    billable_outcomes_current: int
    billable_outcomes_simulated: int
    affected_customers: int
    line_item_breakdown: list[dict[str, Any]]


class TemplateResponse(BaseModel):
    """Single pricing template in list response."""

    name: str
    description: str
    category: str
    pricing_rules: list[dict[str, Any]]


class ForecastRequest(BaseModel):
    """Request body for POST /v1/simulate/forecast."""

    base_mrr: str = Field(..., description="Starting MRR as a decimal string")
    growth_rate: str = Field(..., description="Monthly growth rate, e.g. '0.05' for 5%")
    churn_rate: str = Field(..., description="Monthly churn rate, e.g. '0.02' for 2%")
    months: int = Field(default=12, ge=1, le=60)
    simulations: int = Field(default=1000, ge=100, le=10000)


class ForecastResponse(BaseModel):
    """Response body for POST /v1/simulate/forecast."""

    months: list[str]
    p10: list[str]
    p50: list[str]
    p90: list[str]
    mean: list[str]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/simulate",
    response_model=SimulateResponse,
    status_code=status.HTTP_200_OK,
    summary="Run a what-if pricing simulation",
)
async def simulate_pricing(
    payload: SimulateRequest,
    db: AsyncSession = Depends(get_db),
) -> SimulateResponse:
    """Run a pricing simulation scenario against historical data.

    Compares current plan revenue with a proposed set of pricing rules
    over the specified date range.
    """
    try:
        result = await run_simulation(db, payload.scenario, payload.plan_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return SimulateResponse(
        current_revenue=str(result.current_revenue),
        simulated_revenue=str(result.simulated_revenue),
        delta=str(result.delta),
        delta_pct=str(result.delta_pct),
        billable_outcomes_current=result.billable_outcomes_current,
        billable_outcomes_simulated=result.billable_outcomes_simulated,
        affected_customers=result.affected_customers,
        line_item_breakdown=result.line_item_breakdown,
    )


@router.get(
    "/simulate/templates",
    response_model=list[TemplateResponse],
    status_code=status.HTTP_200_OK,
    summary="List available pricing templates",
)
async def list_templates() -> list[TemplateResponse]:
    """Return all pre-built pricing templates."""
    templates = get_templates()
    return [
        TemplateResponse(
            name=t.name,
            description=t.description,
            category=t.category,
            pricing_rules=t.pricing_rules,
        )
        for t in templates
    ]


@router.post(
    "/simulate/forecast",
    response_model=ForecastResponse,
    status_code=status.HTTP_200_OK,
    summary="Run a Monte Carlo revenue forecast",
)
async def run_forecast(
    payload: ForecastRequest,
) -> ForecastResponse:
    """Project MRR forward using Monte Carlo simulation.

    Returns P10, P50, P90, and mean revenue bands over the requested
    number of months.
    """
    result = forecast_revenue(
        base_mrr=Decimal(payload.base_mrr),
        growth_rate=Decimal(payload.growth_rate),
        churn_rate=Decimal(payload.churn_rate),
        months=payload.months,
        simulations=payload.simulations,
    )

    return ForecastResponse(
        months=result.months,
        p10=[str(v) for v in result.p10],
        p50=[str(v) for v in result.p50],
        p90=[str(v) for v in result.p90],
        mean=[str(v) for v in result.mean],
    )
