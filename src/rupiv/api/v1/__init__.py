"""V1 API router — aggregates all v1 sub-routers."""

from __future__ import annotations

from fastapi import APIRouter

from rupiv.api.v1.a2a import router as a2a_router
from rupiv.api.v1.analytics import router as analytics_router
from rupiv.api.v1.api_keys import router as api_keys_router
from rupiv.api.v1.credits import router as credits_router
from rupiv.api.v1.customers import router as customers_router
from rupiv.api.v1.entities import router as entities_router
from rupiv.api.v1.events import router as events_router
from rupiv.api.v1.invoices import router as invoices_router
from rupiv.api.v1.onboarding import router as onboarding_router
from rupiv.api.v1.plans import router as plans_router
from rupiv.api.v1.quotes import router as quotes_router
from rupiv.api.v1.revenue import router as revenue_router
from rupiv.api.v1.simulate import router as simulate_router
from rupiv.api.v1.stream import router as stream_router
from rupiv.api.v1.subscriptions import router as subscriptions_router
from rupiv.api.v1.webhooks import router as webhooks_router

v1_router = APIRouter(prefix="/v1")

v1_router.include_router(events_router)
v1_router.include_router(customers_router)
v1_router.include_router(entities_router)
v1_router.include_router(plans_router)
v1_router.include_router(subscriptions_router)
v1_router.include_router(invoices_router)
v1_router.include_router(quotes_router)
v1_router.include_router(webhooks_router)
v1_router.include_router(a2a_router)
v1_router.include_router(analytics_router)
v1_router.include_router(api_keys_router)
v1_router.include_router(credits_router)
v1_router.include_router(revenue_router)
v1_router.include_router(simulate_router)
v1_router.include_router(stream_router)
v1_router.include_router(onboarding_router)
