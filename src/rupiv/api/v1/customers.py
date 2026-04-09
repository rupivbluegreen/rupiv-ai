"""Customer CRUD endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rupiv.db import get_db
from rupiv.models.customer import Customer

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

router = APIRouter(prefix="/customers", tags=["customers"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CustomerCreate(BaseModel):
    """Request body for creating a customer."""

    name: str
    email: str
    external_id: str
    country_code: str = "NL"
    currency: str = "EUR"
    is_business: bool = False
    billing_email: str | None = None
    vat_number: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class CustomerUpdate(BaseModel):
    """Request body for updating a customer."""

    name: str | None = None
    email: str | None = None
    external_id: str | None = None
    country_code: str | None = None
    currency: str | None = None
    is_business: bool | None = None
    billing_email: str | None = None
    vat_number: str | None = None
    metadata: dict[str, str] | None = None


class CustomerResponse(BaseModel):
    """Customer resource representation."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "e4f3c2a1-7b60-4d8e-9a15-2f0e8c3d71b4",
                "name": "WindmillAI BV",
                "email": "billing@windmill-ai.nl",
                "external_id": "wai-001",
                "country_code": "NL",
                "currency": "EUR",
                "is_business": True,
                "billing_email": "invoices@windmill-ai.nl",
                "vat_number": "NL862345679B01",
                "metadata": {"segment": "enterprise", "csm": "jan.devries"},
                "created_at": "2026-03-15T10:22:00Z",
                "updated_at": "2026-04-01T08:45:12Z",
            },
        },
    )

    id: uuid.UUID
    name: str
    email: str
    external_id: str
    country_code: str
    currency: str
    is_business: bool
    billing_email: str | None = None
    vat_number: str | None = None
    metadata: dict[str, str] | None = Field(default=None, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


class CustomerListResponse(BaseModel):
    """Paginated list of customers."""

    items: list[CustomerResponse]
    total: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=CustomerListResponse, summary="List customers")
async def list_customers(
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
) -> CustomerListResponse:
    """Return a paginated list of customers."""
    logger.info("list_customers", limit=limit, offset=offset)

    count_result = await session.execute(select(func.count(Customer.id)))
    total: int = count_result.scalar_one()

    result = await session.execute(
        select(Customer).order_by(Customer.created_at.desc()).limit(limit).offset(offset),
    )
    rows: list[Customer] = list(result.scalars().all())

    return CustomerListResponse(
        items=[CustomerResponse.model_validate(row) for row in rows],
        total=total,
    )


@router.get("/{customer_id}", response_model=CustomerResponse, summary="Get a customer")
async def get_customer(
    customer_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> CustomerResponse:
    """Return a single customer by ID."""
    logger.info("get_customer", customer_id=str(customer_id))

    result = await session.execute(select(Customer).where(Customer.id == customer_id))
    customer: Customer | None = result.scalar_one_or_none()

    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found",
        )

    return CustomerResponse.model_validate(customer)


@router.post(
    "",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a customer",
)
async def create_customer(
    payload: CustomerCreate,
    session: AsyncSession = Depends(get_db),
) -> CustomerResponse:
    """Create a new customer record."""
    logger.info("create_customer", name=payload.name, email=payload.email)

    customer = Customer(
        name=payload.name,
        email=payload.email,
        external_id=payload.external_id,
        country_code=payload.country_code,
        currency=payload.currency,
        is_business=payload.is_business,
        billing_email=payload.billing_email,
        vat_number=payload.vat_number,
        metadata_=payload.metadata or None,
    )
    session.add(customer)
    await session.flush()
    await session.refresh(customer)

    return CustomerResponse.model_validate(customer)


@router.patch("/{customer_id}", response_model=CustomerResponse, summary="Update a customer")
async def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    session: AsyncSession = Depends(get_db),
) -> CustomerResponse:
    """Partially update a customer."""
    logger.info("update_customer", customer_id=str(customer_id))

    result = await session.execute(select(Customer).where(Customer.id == customer_id))
    customer: Customer | None = result.scalar_one_or_none()

    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found",
        )

    # Map Pydantic field names to ORM attribute names
    field_mapping: dict[str, str] = {
        "metadata": "metadata_",
    }

    update_data: dict[str, object] = payload.model_dump(exclude_unset=True)
    for field_name, value in update_data.items():
        attr_name: str = field_mapping.get(field_name, field_name)
        setattr(customer, attr_name, value)

    await session.flush()
    await session.refresh(customer)

    return CustomerResponse.model_validate(customer)
