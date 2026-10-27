"""Frozen contract constants for the Nexova weekly performance pipeline.

These values are intentionally duplicated from the telemetry catalogue so that
``data/`` does not import from ``backrooms/services/``. Contract tests compare
them with the telemetry constants to catch drift.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Final

PIPELINE_NAME: Final = "weekly-office-program-performance"
FLOW_NAME: Final = "weekly_office_program_performance_flow"
TRANSFORMATION_VERSION: Final = "1.0"
SCHEMA_VERSION: Final = "1.0"
INVENTORY_SERVICE: Final = "inventory-api"

INBOUND_EVENT: Final = "inbound_order_created"
OUTBOUND_EVENT: Final = "outbound_order_created"
SHORTAGE_EVENT: Final = "stock_threshold_triggered"
VARIANCE_EVENT: Final = "kit_cost_variance_detected"

ALLOWED_EVENT_TYPES: Final = frozenset(
    {INBOUND_EVENT, OUTBOUND_EVENT, SHORTAGE_EVENT, VARIANCE_EVENT}
)
ORDER_EVENT_TYPES: Final = frozenset({INBOUND_EVENT, OUTBOUND_EVENT, VARIANCE_EVENT})
UNIT_COST_EVENT_TYPES: Final = frozenset({INBOUND_EVENT, VARIANCE_EVENT})

OFFICES: Final = ("valencia", "miami")
OFFICE_CURRENCY: Final = {"valencia": "EUR", "miami": "USD"}
CURRENCIES: Final = frozenset(OFFICE_CURRENCY.values())

MONEY_QUANTUM: Final = Decimal("0.01")
REJECTION_THRESHOLD: Final = Decimal("0.05")
STALE_RUN_MINUTES: Final = 15

WEEK_DAYS: Final = 7


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def week_start_for(value: datetime) -> date:
    """Return the Monday (UTC) of the ISO week containing ``value``."""
    if value.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    utc_value = value.astimezone(timezone.utc)
    return utc_value.date() - timedelta(days=utc_value.weekday())


def most_recent_complete_week(today: date | None = None) -> date:
    """The most recent completed ISO week, as its Monday."""
    current = today or datetime.now(timezone.utc).date()
    current_monday = current - timedelta(days=current.weekday())
    return current_monday - timedelta(days=WEEK_DAYS)


def week_bounds(week_start: date) -> tuple[datetime, datetime]:
    start = datetime.combine(week_start, datetime.min.time(), tzinfo=timezone.utc)
    return start, start + timedelta(days=WEEK_DAYS)


def currency_for_office(office: str) -> str:
    return OFFICE_CURRENCY[office]
