"""Pure deduplication, normalization, and validation of telemetry rows.

The input rows are dictionaries shaped like the persisted
``public.telemetry_events`` rows the extraction task returns. No database,
network, or Prefect imports live in this module.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .constants import (
    ALLOWED_EVENT_TYPES,
    CURRENCIES,
    INVENTORY_SERVICE,
    OFFICE_CURRENCY,
    OFFICES,
    ORDER_EVENT_TYPES,
    SCHEMA_VERSION,
    UNIT_COST_EVENT_TYPES,
    week_start_for,
)

_EVENT_TYPE_FALLBACK = "unknown"


@dataclass(frozen=True)
class Rejection:
    event_id: str | None
    event_type: str
    reason: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "reason": self.reason,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class NormalizedEvent:
    event_id: str
    event_type: str
    office: str
    programme_id: str
    currency: str
    quantity: int | None
    unit_cost: Decimal | None
    timestamp: datetime
    order_id: str | None
    dedup_key: str

    def as_dict(self) -> dict[str, Any]:
        """JSON-safe representation consumed by the KPI tasks."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "office": self.office,
            "programme_id": self.programme_id,
            "currency": self.currency,
            "quantity": self.quantity,
            "unit_cost": str(self.unit_cost) if self.unit_cost is not None else None,
            "timestamp": self.timestamp.isoformat(),
            "order_id": self.order_id,
        }


@dataclass
class DedupResult:
    rows: list[dict[str, Any]]
    records_extracted: int
    duplicate_count: int
    duplicate_payload_conflict_count: int


@dataclass
class NormalizationResult:
    events: list[NormalizedEvent]
    rejections: list[Rejection]
    order_identity_anomaly_count: int
    order_identity_missing_count: int


class _RowRejected(Exception):
    def __init__(self, reason: str, **details: Any) -> None:
        super().__init__(reason)
        self.reason = reason
        self.details = details


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    raise _RowRejected("row_not_an_object")


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as error:
            raise _RowRejected("timestamp_invalid") from error
    else:
        raise _RowRejected("timestamp_invalid")

    if parsed.tzinfo is None:
        raise _RowRejected("timestamp_missing_timezone")
    return parsed.astimezone(timezone.utc)


def _parse_quantity(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        raise _RowRejected("quantity_invalid", field="quantity")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise _RowRejected("quantity_not_integer", field="quantity")
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        raise _RowRejected("quantity_not_integer", field="quantity")
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text)
        except ValueError as error:
            raise _RowRejected("quantity_not_integer", field="quantity") from error
    raise _RowRejected("quantity_invalid", field="quantity")


def _parse_unit_cost(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise _RowRejected("unit_cost_invalid", field="unit_cost")
    try:
        cost = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError) as error:
        raise _RowRejected("unit_cost_invalid", field="unit_cost") from error
    if not cost.is_finite():
        raise _RowRejected("unit_cost_not_finite", field="unit_cost")
    if cost <= 0:
        raise _RowRejected("unit_cost_not_positive", field="unit_cost")
    return cost


def _event_type_label(value: Any) -> str:
    label = _clean_text(value)
    return label if label else _EVENT_TYPE_FALLBACK


def _dedup_key(row: Mapping[str, Any], index: int) -> str:
    tags = row.get("tags") if isinstance(row.get("tags"), Mapping) else {}
    meta = tags.get("_meta") if isinstance(tags.get("_meta"), Mapping) else {}
    event_id = _clean_text(meta.get("eventId"))
    if event_id:
        return event_id
    row_id = _clean_text(row.get("id"))
    if row_id:
        return row_id
    return f"missing:{index}"


def _sort_key(row: Mapping[str, Any], index: int) -> tuple[datetime, str, int]:
    try:
        timestamp = _parse_timestamp(row.get("timestamp"))
    except _RowRejected:
        timestamp = datetime.max.replace(tzinfo=timezone.utc)
    return timestamp, str(row.get("id") or ""), index


def _business_payload(row: Mapping[str, Any]) -> str:
    tags = row.get("tags") if isinstance(row.get("tags"), Mapping) else {}
    payload = {key: value for key, value in tags.items() if key != "_meta"}
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


def deduplicate_rows(rows: list[Mapping[str, Any]]) -> DedupResult:
    """Keep the earliest row per ``tags._meta.eventId`` (row id fallback).

    Ties are broken by the smallest source row id, then by input order. Duplicate
    rows with different business payloads are counted as conflicts instead of
    being silently discarded.
    """
    buckets: dict[str, list[tuple[datetime, str, int, Mapping[str, Any]]]] = defaultdict(list)
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            # Malformed entries still need a deterministic standalone bucket so
            # normalization can reject them without collapsing them together.
            buckets[f"invalid:{index}"].append(
                (datetime.max.replace(tzinfo=timezone.utc), "", index, {"__invalid__": True})
            )
            continue
        buckets[_dedup_key(row, index)].append((*_sort_key(row, index), row))

    canonical: list[Mapping[str, Any]] = []
    conflicts = 0
    for bucket in buckets.values():
        bucket.sort(key=lambda item: (item[0], item[1], item[2]))
        canonical.append(bucket[0][3])
        payloads = {
            _business_payload(item[3])
            for item in bucket
            if isinstance(item[3], Mapping) and "__invalid__" not in item[3]
        }
        if len(payloads) > 1:
            conflicts += 1

    canonical.sort(
        key=lambda row: (
            _sort_key(row, 0)[0]
            if isinstance(row, Mapping)
            else datetime.max.replace(tzinfo=timezone.utc),
            str(row.get("id") or "") if isinstance(row, Mapping) else "",
        )
    )
    return DedupResult(
        rows=list(canonical),
        records_extracted=len(rows),
        duplicate_count=len(rows) - len(canonical),
        duplicate_payload_conflict_count=conflicts,
    )


def normalize_row(
    row: Mapping[str, Any],
    *,
    target_week_start: date,
    dedup_key: str,
) -> tuple[NormalizedEvent | None, Rejection | None]:
    """Validate and normalize one deduplicated source row."""
    raw_event_type = row.get("event_type") if isinstance(row, Mapping) else None
    labels: dict[str, str | None] = {
        "event_type": _event_type_label(raw_event_type),
        "event_id": None,
    }
    try:
        current = _as_mapping(row)

        tags_value = current.get("tags")
        if not isinstance(tags_value, Mapping):
            raise _RowRejected("tags_missing")
        tags = tags_value
        meta_value = tags.get("_meta")
        meta = meta_value if isinstance(meta_value, Mapping) else {}

        row_id = _clean_text(current.get("id"))
        meta_event_id = _clean_text(meta.get("eventId"))
        labels["event_id"] = meta_event_id or row_id
        if not labels["event_id"]:
            raise _RowRejected("event_id_missing")

        event_type = _clean_text(current.get("event_type"))
        labels["event_type"] = event_type or _EVENT_TYPE_FALLBACK
        if event_type not in ALLOWED_EVENT_TYPES:
            raise _RowRejected("event_type_not_allowed", field="event_type")

        if _clean_text(current.get("service")) != INVENTORY_SERVICE:
            raise _RowRejected("service_not_allowed", field="service")

        schema_version = _clean_text(meta.get("schemaVersion"))
        if schema_version != SCHEMA_VERSION:
            raise _RowRejected("schema_version_not_supported", field="schemaVersion")

        office = _clean_text(tags.get("office"))
        office = office.lower() if office else None
        if office not in OFFICES:
            raise _RowRejected("office_not_allowed", field="office")

        programme_id = _clean_text(tags.get("programme_id"))
        if not programme_id:
            raise _RowRejected("programme_id_missing", field="programme_id")

        currency = _clean_text(tags.get("currency"))
        currency = currency.upper() if currency else None
        if currency not in CURRENCIES:
            raise _RowRejected("currency_not_allowed", field="currency")
        if currency != OFFICE_CURRENCY[office]:
            raise _RowRejected("currency_office_mismatch", field="currency")

        timestamp = _parse_timestamp(current.get("timestamp"))
        if week_start_for(timestamp) != target_week_start:
            raise _RowRejected("week_out_of_range", field="timestamp")

        quantity = _parse_quantity(tags.get("quantity"))
        if event_type == "stock_threshold_triggered":
            if quantity < 0:
                raise _RowRejected("quantity_negative", field="quantity")
        elif quantity <= 0:
            raise _RowRejected("quantity_not_positive", field="quantity")

        unit_cost = None
        if event_type in UNIT_COST_EVENT_TYPES:
            unit_cost = _parse_unit_cost(tags.get("unit_cost"))

        order_id = _clean_text(tags.get("order_id"))

        return (
            NormalizedEvent(
                event_id=labels["event_id"],
                event_type=event_type,
                office=office,
                programme_id=programme_id,
                currency=currency,
                quantity=quantity,
                unit_cost=unit_cost,
                timestamp=timestamp,
                order_id=order_id,
                dedup_key=dedup_key,
            ),
            None,
        )
    except _RowRejected as rejection:
        details = {key: value for key, value in rejection.details.items() if value is not None}
        return (
            None,
            Rejection(
                event_id=labels["event_id"],
                event_type=labels["event_type"] or _EVENT_TYPE_FALLBACK,
                reason=rejection.reason,
                details=details,
            ),
        )


def normalize_rows(
    rows: list[Mapping[str, Any]],
    *,
    target_week_start: date,
) -> NormalizationResult:
    events: list[NormalizedEvent] = []
    rejections: list[Rejection] = []
    order_ids: dict[tuple[str, str], set[str]] = defaultdict(set)
    missing_order_identity = 0

    for index, row in enumerate(rows):
        key = _dedup_key(row, index) if isinstance(row, Mapping) else f"invalid:{index}"
        event, rejection = normalize_row(
            row, target_week_start=target_week_start, dedup_key=key
        )
        if rejection is not None:
            rejections.append(rejection)
            continue
        assert event is not None
        events.append(event)
        if event.event_type in ORDER_EVENT_TYPES:
            if event.order_id:
                order_ids[(event.event_type, event.order_id)].add(event.event_id)
            else:
                missing_order_identity += 1

    anomaly_groups = sum(1 for ids in order_ids.values() if len(ids) > 1)
    return NormalizationResult(
        events=events,
        rejections=rejections,
        order_identity_anomaly_count=anomaly_groups,
        order_identity_missing_count=missing_order_identity,
    )


def raw_source_counts(rows: list[Mapping[str, Any]]) -> tuple[dict[str, int], dict[str, int]]:
    """Return raw event-type and office counts before deduplication."""
    event_counts: Counter[str] = Counter()
    office_counts: Counter[str] = Counter()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        event_type = _clean_text(row.get("event_type")) or _EVENT_TYPE_FALLBACK
        event_counts[event_type] += 1
        tags = row.get("tags") if isinstance(row.get("tags"), Mapping) else {}
        office = _clean_text(tags.get("office"))
        if office:
            office_counts[office.lower()] += 1
    return dict(event_counts), dict(office_counts)
