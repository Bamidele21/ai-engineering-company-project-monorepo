"""Pure KPI aggregation, dimension zero-fill, and reconciliation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable

from .constants import (
    INBOUND_EVENT,
    MONEY_QUANTUM,
    OFFICE_CURRENCY,
    OUTBOUND_EVENT,
    REJECTION_THRESHOLD,
    SHORTAGE_EVENT,
    VARIANCE_EVENT,
)
from .normalize import NormalizedEvent, Rejection


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _normalize_pairs(pairs: Iterable[tuple[str, str]]) -> set[tuple[str, str]]:
    normalized: set[tuple[str, str]] = set()
    for office, programme_id in pairs:
        if isinstance(office, str) and isinstance(programme_id, str):
            office_value = office.strip().lower()
            programme_value = programme_id.strip()
            if office_value in OFFICE_CURRENCY and programme_value:
                normalized.add((office_value, programme_value))
    return normalized


@dataclass
class AggregateResult:
    week_start: date
    rows: list[dict[str, Any]]
    reconciliation: dict[str, Any]
    publication_blocked: bool
    block_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_start": self.week_start.isoformat(),
            "rows": [
                {
                    **row,
                    "week_start": row["week_start"].isoformat(),
                    "total_material_cost": str(_money(row["total_material_cost"])),
                }
                for row in self.rows
            ],
            "reconciliation": dict(self.reconciliation),
            "publication_blocked": self.publication_blocked,
            "block_reasons": list(self.block_reasons),
        }


def build_week_fingerprint(
    events: Iterable[NormalizedEvent], rows: Iterable[dict[str, Any]]
) -> str:
    """Hash accepted event identities plus the published KPI values."""
    payload = {
        "event_ids": sorted(event.event_id for event in events),
        "rows": sorted(
            (
                {
                    "office": row["office"],
                    "programme_id": row["programme_id"],
                    "total_material_cost": str(_money(row["total_material_cost"])),
                    "kits_delivered_count": row["kits_delivered_count"],
                    "shortage_events_count": row["shortage_events_count"],
                    "cost_variance_events_count": row["cost_variance_events_count"],
                    "currency": row["currency"],
                }
                for row in rows
            ),
            key=lambda item: (item["office"], item["programme_id"]),
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def aggregate_events(
    events: list[NormalizedEvent],
    rejections: list[Rejection],
    *,
    week_start: date,
    dimension_pairs: Iterable[tuple[str, str]],
    known_programmes: Iterable[str],
    records_extracted: int,
    records_deduplicated: int,
    duplicate_payload_conflict_count: int = 0,
    order_identity_anomaly_count: int = 0,
    order_identity_missing_count: int = 0,
    rejection_threshold: Decimal = REJECTION_THRESHOLD,
) -> AggregateResult:
    """Aggregate normalized events into the fixed destination grain."""
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    event_totals = {
        INBOUND_EVENT: 0,
        OUTBOUND_EVENT: 0,
        SHORTAGE_EVENT: 0,
        VARIANCE_EVENT: 0,
    }

    for event in events:
        key = (event.office, event.programme_id)
        bucket = grouped.setdefault(
            key,
            {
                "total_material_cost": Decimal("0.00"),
                "kits_delivered_count": 0,
                "shortage_events_count": 0,
                "cost_variance_events_count": 0,
            },
        )
        event_totals[event.event_type] += 1
        if event.event_type == INBOUND_EVENT:
            assert event.quantity is not None and event.unit_cost is not None
            bucket["total_material_cost"] += Decimal(event.quantity) * event.unit_cost
        elif event.event_type == OUTBOUND_EVENT:
            bucket["kits_delivered_count"] += 1
        elif event.event_type == SHORTAGE_EVENT:
            bucket["shortage_events_count"] += 1
        elif event.event_type == VARIANCE_EVENT:
            bucket["cost_variance_events_count"] += 1

    known = {
        slug.strip()
        for slug in known_programmes
        if isinstance(slug, str) and slug.strip()
    }
    observed_pairs = set(grouped)
    dimension_pairs_set = _normalize_pairs(dimension_pairs)
    spine = dimension_pairs_set | observed_pairs

    rows: list[dict[str, Any]] = []
    zero_filled = 0
    for office, programme_id in sorted(spine, key=lambda item: (item[0], item[1])):
        bucket = grouped.get((office, programme_id))
        if bucket is None:
            zero_filled += 1
            bucket = {
                "total_material_cost": Decimal("0.00"),
                "kits_delivered_count": 0,
                "shortage_events_count": 0,
                "cost_variance_events_count": 0,
            }
        rows.append(
            {
                "office": office,
                "programme_id": programme_id,
                "week_start": week_start,
                "total_material_cost": _money(bucket["total_material_cost"]),
                "kits_delivered_count": bucket["kits_delivered_count"],
                "shortage_events_count": bucket["shortage_events_count"],
                "cost_variance_events_count": bucket["cost_variance_events_count"],
                "currency": OFFICE_CURRENCY[office],
            }
        )

    unknown_programmes = sorted(
        {
            programme_id
            for _, programme_id in observed_pairs
            if programme_id not in known
        }
    )

    kpi_totals = {
        "outbound_order_created": sum(row["kits_delivered_count"] for row in rows),
        "stock_threshold_triggered": sum(row["shortage_events_count"] for row in rows),
        "kit_cost_variance_detected": sum(
            row["cost_variance_events_count"] for row in rows
        ),
    }
    accepted_count = len(events)
    rejected_count = len(rejections)
    denominator = records_extracted
    rejection_rate = (
        Decimal(rejected_count) / Decimal(denominator)
        if denominator > 0
        else Decimal("0")
    )

    checks = {
        "records_deduplicated_equals_accepted_plus_rejected": (
            records_deduplicated == accepted_count + rejected_count
        ),
        "inbound_count_matches_accepted": event_totals[INBOUND_EVENT]
        == sum(1 for event in events if event.event_type == INBOUND_EVENT),
        "outbound_count_matches_kpi_total": event_totals[OUTBOUND_EVENT]
        == kpi_totals["outbound_order_created"],
        "shortage_count_matches_kpi_total": event_totals[SHORTAGE_EVENT]
        == kpi_totals["stock_threshold_triggered"],
        "variance_count_matches_kpi_total": event_totals[VARIANCE_EVENT]
        == kpi_totals["kit_cost_variance_detected"],
        "currencies_match_offices": all(
            row["currency"] == OFFICE_CURRENCY[row["office"]] for row in rows
        ),
        "week_start_is_monday": week_start.weekday() == 0,
    }

    block_reasons: list[str] = []
    if rejection_rate > rejection_threshold:
        block_reasons.append("rejection_threshold_exceeded")
    if not all(checks.values()):
        block_reasons.append("reconciliation_mismatch")
    if not rows:
        # An empty scaffold with no observed activity is a valid zero week only
        # when the catalogue itself is empty; callers treat missing dimensions
        # as an error before this function is reached.
        block_reasons.append("no_dimension_pairs")

    reconciliation = {
        "rejection_threshold": str(rejection_threshold),
        "rejection_rate": str(rejection_rate.quantize(Decimal("0.0001"))),
        "records_extracted": records_extracted,
        "records_deduplicated": records_deduplicated,
        "accepted_event_count": accepted_count,
        "rejected_event_count": rejected_count,
        "duplicate_count": records_extracted - records_deduplicated,
        "duplicate_payload_conflict_count": duplicate_payload_conflict_count,
        "order_identity_anomaly_count": order_identity_anomaly_count,
        "order_identity_missing_count": order_identity_missing_count,
        "accepted_event_counts": dict(event_totals),
        "kpi_totals": kpi_totals,
        "unknown_programme_ids": unknown_programmes,
        "dimension_pair_count": len(dimension_pairs_set),
        "destination_row_count": len(rows),
        "zero_filled_row_count": zero_filled,
        "checks": checks,
        "week_fingerprint": build_week_fingerprint(events, rows),
    }

    return AggregateResult(
        week_start=week_start,
        rows=rows,
        reconciliation=reconciliation,
        publication_blocked=bool(block_reasons),
        block_reasons=block_reasons,
    )
