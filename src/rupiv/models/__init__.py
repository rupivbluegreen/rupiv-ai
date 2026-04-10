"""SQLAlchemy models — import all models so Alembic can discover them."""

from rupiv.models.alert import Alert, AlertRule, AlertSeverity, AlertStatus, AlertType
from rupiv.models.api_key import ApiKey
from rupiv.models.audit_log import AuditLog
from rupiv.models.contract import Contract, ContractRenewalType, ContractStatus
from rupiv.models.credit import CreditBalance, CreditTransaction, TransactionType
from rupiv.models.customer import Customer
from rupiv.models.customer_user import CustomerUser, CustomerUserRole
from rupiv.models.entity import EntityType, LegalEntity
from rupiv.models.erp_connection import ERPConnection, ExportLog
from rupiv.models.event import Event, EventType, OutcomeStatus
from rupiv.models.invoice import Invoice, InvoiceLineItem, InvoiceStatus, TaxType
from rupiv.models.ledger import EntryType, LedgerEntry, LedgerStatus
from rupiv.models.payment_cost import PaymentCostRecord
from rupiv.models.payment_method import PaymentMethod as PaymentMethodModel
from rupiv.models.plan import BillingInterval, Plan, PricingModel, PricingRule
from rupiv.models.policy_rule import ApprovalRecord, PolicyRule
from rupiv.models.quote import Quote, QuoteLineItem, QuoteStatus
from rupiv.models.revenue_schedule import (
    EntryType as RevenueEntryType,
)
from rupiv.models.revenue_schedule import (
    RevenueEntry,
    RevenueSchedule,
    ScheduleStatus,
)
from rupiv.models.subscription import Subscription, SubscriptionStatus
from rupiv.models.transformation_rule import TransformationRule
from rupiv.models.webhook_endpoint import WebhookDelivery, WebhookEndpoint

__all__ = [
    # Models
    "Alert",
    "AlertRule",
    "ApiKey",
    "AuditLog",
    "ApprovalRecord",
    "CustomerUser",
    "Contract",
    "CreditBalance",
    "CreditTransaction",
    "Customer",
    "ERPConnection",
    "Event",
    "ExportLog",
    "Invoice",
    "InvoiceLineItem",
    "LedgerEntry",
    "LegalEntity",
    "PaymentCostRecord",
    "PaymentMethodModel",
    "Plan",
    "PolicyRule",
    "PricingRule",
    "Quote",
    "QuoteLineItem",
    "RevenueEntry",
    "RevenueSchedule",
    "Subscription",
    "TransformationRule",
    "WebhookDelivery",
    "WebhookEndpoint",
    # Enums
    "AlertSeverity",
    "AlertStatus",
    "AlertType",
    "BillingInterval",
    "ContractRenewalType",
    "ContractStatus",
    "CustomerUserRole",
    "EntityType",
    "EntryType",
    "EventType",
    "InvoiceStatus",
    "LedgerStatus",
    "OutcomeStatus",
    "PricingModel",
    "QuoteStatus",
    "RevenueEntryType",
    "ScheduleStatus",
    "SubscriptionStatus",
    "TaxType",
    "TransactionType",
]
