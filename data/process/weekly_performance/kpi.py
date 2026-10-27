"""Pure per-KPI calculation functions for the weekly performance pipeline.

Each function consumes normalized event dictionaries (see
``NormalizedEvent.as_dict``) and returns a mapping from ``"office|programme"``
to the computed KPI value. They are wrapped one-to-one by Prefect tasks so the
isolated test suite can call ``task.fn`` directly with in-memory fixtures.

Malformed required fields raise ``ValueError`` explicitly; they never corrupt a
total. Empty input produces an empty mapping, which downstream assembly turns
into explicit zero rows.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Mapping

from .constants import (
    INBOUND_EVENT,
    MONEY_QUANTUM,
    OUTBOUND_EVENT,
    SHORTAGE_EVENT,
    VARIANCE_EVENT,
)

PAIR_SEPARATOR = "|"


def pair_key(office: str, programme_id: str) -> str:
    return f"{office}{PAIR_SEPARATOR}{programme_id}"


def split_pair(key: str) -> tuple[str, str]:
    office, programme_id = key.split(PAIR_SEPARATOR, 1)
    return office, programme_id


def _require(event: Mapping[str, Any], field: str) -> Any:
    value = event.get(field)
    if value is None:
        raise ValueError(f"event is missing required field {field!r}")
    return value


def compute_total_material_cost(
    events: list[Mapping[str, Any]],
) -> dict[str, str]:
    """Sum ``quantity * unit_cost`` for inbound events in decimal money.

    Variance events carry a ``unit_cost`` too, but they are signals, not
    purchases: they never add to material spend.
    """
    totals: dict[str, Decimal] = {}
    for event in events:
        event_type = _require(event, "event_type")
        if event_type != INBOUND_EVENT:
            continue
        office = _require(event, "office")
        programme_id = _require(event, "programme_id")
        quantity = _require(event, "quantity")
        unit_cost = _require(event, "unit_cost")

        if isinstance(quantity, bool) or not isinstance(quantity, int):
            raise ValueError(f"quantity must be an integer, got {quantity!r}")
        if quantity <= 0:
            raise ValueError(f"quantity must be positive, got {quantity}")

        if isinstance(unit_cost, Decimal):
            cost = unit_cost
        else:
            try:
                cost = Decimal(str(unit_cost).strip())
            except (InvalidOperation, ValueError, AttributeError) as error:
                raise ValueError(
                    f"unit_cost is not a valid number: {unit_cost!r}"
                ) from error
        if not cost.is_finite():
            raise ValueError(f"unit_cost must be finite, got {unit_cost!r}")
        if cost <= 0:
            raise ValueError(f"unit_cost must be positive, got {unit_cost!r}")

        key = pair_key(str(office), str(programme_id))
        totals[key] = totals.get(key, Decimal("0.00")) + Decimal(quantity) * cost

    return {
        key: str(value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP))
        for key, value in totals.items()
    }


def _count_events(
    events: list[Mapping[str, Any]],
    event_type: str,
) -> dict[str, int]:
    """Count events, never quantities, per office/programme pair."""
    counts: dict[str, int] = {}
    for event in events:
        if _require(event, "event_type") != event_type:
            continue
        office = _require(event, "office")
        programme_id = _require(event, "programme_id")
        key = pair_key(str(office), str(programme_id))
        counts[key] = counts.get(key, 0) + 1
    return counts


def count_kits_delivered(events: list[Mapping[str, Any]]) -> dict[str, int]:
    """Count ``outbound_order_created`` delivery events, not units."""
    return _count_events(events, OUTBOUND_EVENT)


def count_shortage_events(events: list[Mapping[str, Any]]) -> dict[str, int]:
    """Count captured ``stock_threshold_triggered`` events."""
    return _count_events(events, SHORTAGE_EVENT)


def count_cost_variance_events(
    events: list[Mapping[str, Any]],
) -> dict[str, int]:
    """Count captured ``kit_cost_variance_detected`` alerts."""
    return _count_events(events, VARIANCE_EVENT)
