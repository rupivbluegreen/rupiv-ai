"""Analytics module — MRR/ARR, payment costs, routing, cohorts, outcomes."""

from rupiv.analytics.cohort import CohortEntry, calculate_cohorts
from rupiv.analytics.mrr_arr import MRRResult, calculate_arr, calculate_churn_rate, calculate_mrr
from rupiv.analytics.outcome_metrics import OutcomeMetrics, calculate_outcome_metrics
from rupiv.analytics.payment_costs import (
    MethodCost,
    PaymentCostSummary,
    calculate_payment_costs,
    get_cost_comparison,
)
from rupiv.analytics.routing_optimizer import PSPRoute, find_cheapest_route, get_recommendations

__all__ = [
    # MRR / ARR
    "MRRResult",
    "calculate_arr",
    "calculate_churn_rate",
    "calculate_mrr",
    # Payment costs
    "MethodCost",
    "PaymentCostSummary",
    "calculate_payment_costs",
    "get_cost_comparison",
    # Routing
    "PSPRoute",
    "find_cheapest_route",
    "get_recommendations",
    # Outcomes
    "OutcomeMetrics",
    "calculate_outcome_metrics",
    # Cohorts
    "CohortEntry",
    "calculate_cohorts",
]
