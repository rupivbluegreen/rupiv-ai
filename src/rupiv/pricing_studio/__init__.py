"""Pricing Studio — what-if simulations, A/B testing, and revenue forecasting."""

from rupiv.pricing_studio.ab_test import ABTest, assign_variant, evaluate_test
from rupiv.pricing_studio.revenue_forecast import ForecastResult, forecast_revenue
from rupiv.pricing_studio.simulator import SimulationResult, SimulationScenario, run_simulation
from rupiv.pricing_studio.templates import PricingTemplate, get_templates

__all__ = [
    "ABTest",
    "ForecastResult",
    "PricingTemplate",
    "SimulationResult",
    "SimulationScenario",
    "assign_variant",
    "evaluate_test",
    "forecast_revenue",
    "get_templates",
    "run_simulation",
]
