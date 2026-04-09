"""GDPR data export and anonymization tooling."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.compliance.audit import log_action
from rupiv.models.customer import Customer

logger = structlog.get_logger(__name__)

_REDACTED = "[REDACTED]"


async def export_customer_data(
    session: AsyncSession,
    customer_id: uuid.UUID,
    *,
    actor_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """GDPR Article 20 — portable data export for a customer.

    Returns all PII and billing data associated with the customer as a
    JSON-serialisable dictionary.
    """
    stmt = select(Customer).where(Customer.id == customer_id)
    result = await session.execute(stmt)
    customer = result.scalar_one_or_none()

    if customer is None:
        raise ValueError(f"Customer {customer_id} not found")

    export: dict[str, Any] = {
        "export_generated_at": datetime.now(timezone.utc).isoformat(),
        "customer": {
            "id": str(customer.id),
            "external_id": customer.external_id,
            "name": customer.name,
            "email": customer.email,
            "billing_email": customer.billing_email,
            "country_code": customer.country_code,
            "vat_number": customer.vat_number,
            "is_business": customer.is_business,
            "currency": customer.currency,
            "metadata": customer.metadata_,
            "created_at": customer.created_at.isoformat(),
            "updated_at": customer.updated_at.isoformat(),
        },
    }

    # Log the export action
    if actor_id is not None:
        await log_action(
            session,
            actor_id=actor_id,
            actor_type="system",
            action="data_export",
            resource_type="customer",
            resource_id=customer_id,
            metadata={"reason": "gdpr_data_export"},
        )

    logger.info("compliance.data_exported", customer_id=str(customer_id))
    return export


async def anonymize_customer(
    session: AsyncSession,
    customer_id: uuid.UUID,
    *,
    actor_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """GDPR Article 17 — right to erasure via anonymization.

    Replaces all PII fields with ``[REDACTED]`` instead of deleting the row
    so that billing history and revenue recognition records remain intact.
    """
    stmt = select(Customer).where(Customer.id == customer_id)
    result = await session.execute(stmt)
    customer = result.scalar_one_or_none()

    if customer is None:
        raise ValueError(f"Customer {customer_id} not found")

    old_values = {
        "name": customer.name,
        "email": customer.email,
        "billing_email": customer.billing_email,
        "vat_number": customer.vat_number,
        "external_id": customer.external_id,
    }

    await session.execute(
        update(Customer)
        .where(Customer.id == customer_id)
        .values(
            name=_REDACTED,
            email=_REDACTED,
            billing_email=_REDACTED,
            vat_number=_REDACTED,
            external_id=f"anon-{customer_id}",
            metadata_=None,
        )
    )

    # Log the anonymization action
    if actor_id is not None:
        await log_action(
            session,
            actor_id=actor_id,
            actor_type="system",
            action="anonymize",
            resource_type="customer",
            resource_id=customer_id,
            changes={
                field: {"old": old, "new": _REDACTED}
                for field, old in old_values.items()
                if old is not None
            },
            metadata={"reason": "gdpr_right_to_erasure"},
        )

    logger.info("compliance.customer_anonymized", customer_id=str(customer_id))

    return {
        "customer_id": str(customer_id),
        "anonymized_fields": [k for k, v in old_values.items() if v is not None],
        "anonymized_at": datetime.now(timezone.utc).isoformat(),
    }


async def get_data_retention_report(
    session: AsyncSession,
) -> dict[str, Any]:
    """Generate a summary of data retention across customer records.

    Returns counts of active vs anonymized customers and the oldest record
    timestamp — useful for demonstrating GDPR compliance posture.
    """
    from sqlalchemy import func as sa_func

    total_q = select(sa_func.count()).select_from(Customer)
    total_result = await session.execute(total_q)
    total_customers: int = total_result.scalar() or 0

    anonymized_q = (
        select(sa_func.count())
        .select_from(Customer)
        .where(Customer.name == _REDACTED)
    )
    anonymized_result = await session.execute(anonymized_q)
    anonymized_count: int = anonymized_result.scalar() or 0

    oldest_q = select(sa_func.min(Customer.created_at)).select_from(Customer)
    oldest_result = await session.execute(oldest_q)
    oldest_record = oldest_result.scalar()

    return {
        "total_customers": total_customers,
        "active_customers": total_customers - anonymized_count,
        "anonymized_customers": anonymized_count,
        "oldest_record": oldest_record.isoformat() if oldest_record else None,
        "report_generated_at": datetime.now(timezone.utc).isoformat(),
    }
