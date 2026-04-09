"""Quote acceptance — accept, reject, and expire quotes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.models.contract import Contract, ContractRenewalType, ContractStatus
from rupiv.models.quote import Quote, QuoteStatus
from rupiv.models.subscription import Subscription, SubscriptionStatus

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


def _ensure_tz_aware(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware (assume UTC if naive)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


async def accept_quote(
    session: AsyncSession,
    quote_id: uuid.UUID,
) -> tuple[Subscription, Contract]:
    """Accept a quote, creating a subscription and contract.

    Args:
        session: Async database session.
        quote_id: The quote to accept.

    Returns:
        A tuple of (Subscription, Contract) created from the quote.

    Raises:
        ValueError: If quote is not found, not in an acceptable state,
                    or has expired.
    """
    result = await session.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if quote is None:
        raise ValueError(f"Quote {quote_id} not found")

    if quote.status not in (QuoteStatus.DRAFT, QuoteStatus.SENT):
        raise ValueError(f"Cannot accept quote in status {quote.status.value}")

    now = datetime.now(tz=UTC)
    expires_at = _ensure_tz_aware(quote.expires_at)
    if expires_at <= now:
        raise ValueError("Quote has expired")

    # Update quote status
    quote.status = QuoteStatus.ACCEPTED
    quote.accepted_at = now

    # Create subscription
    subscription = Subscription(
        customer_id=quote.customer_id,
        plan_id=quote.plan_id,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    session.add(subscription)
    await session.flush()

    # Create contract
    start_date = now.date()
    end_date = start_date + relativedelta(months=quote.term_months)
    contract = Contract(
        quote_id=quote.id,
        subscription_id=subscription.id,
        start_date=start_date,
        end_date=end_date,
        term_months=quote.term_months,
        renewal_type=ContractRenewalType.AUTO,
        status=ContractStatus.ACTIVE,
    )
    session.add(contract)
    await session.flush()

    await session.refresh(subscription)
    await session.refresh(contract)

    logger.info(
        "quote_accepted",
        quote_id=str(quote.id),
        subscription_id=str(subscription.id),
        contract_id=str(contract.id),
    )

    return subscription, contract


async def reject_quote(
    session: AsyncSession,
    quote_id: uuid.UUID,
    reason: str,
) -> Quote:
    """Reject a quote with a reason.

    Args:
        session: Async database session.
        quote_id: The quote to reject.
        reason: Reason for rejection.

    Returns:
        The updated Quote.

    Raises:
        ValueError: If quote is not found or not in a rejectable state.
    """
    result = await session.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()
    if quote is None:
        raise ValueError(f"Quote {quote_id} not found")

    if quote.status not in (QuoteStatus.DRAFT, QuoteStatus.SENT):
        raise ValueError(f"Cannot reject quote in status {quote.status.value}")

    quote.status = QuoteStatus.REJECTED
    quote.notes = reason

    await session.flush()
    await session.refresh(quote)

    logger.info(
        "quote_rejected",
        quote_id=str(quote.id),
        reason=reason,
    )

    return quote


async def expire_stale_quotes(session: AsyncSession) -> int:
    """Find all quotes past their expiration date and mark as expired.

    Args:
        session: Async database session.

    Returns:
        Number of quotes expired.
    """
    now = datetime.now(tz=UTC)

    # Use select + iterate to avoid SQLAlchemy evaluator timezone
    # comparison issues across database backends.
    stmt = select(Quote).where(
        Quote.status.in_([QuoteStatus.DRAFT.value, QuoteStatus.SENT.value]),
        Quote.expires_at <= now,
    )
    result = await session.execute(stmt)
    stale_quotes = result.scalars().all()

    for q in stale_quotes:
        q.status = QuoteStatus.EXPIRED

    count = len(stale_quotes)
    await session.flush()

    logger.info("stale_quotes_expired", count=count)

    return count
