"""Pure deduplication and validation boundary for the weekly transformation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from .normalize import (
    NormalizedEvent,
    Rejection,
    deduplicate_rows,
    normalize_rows,
    raw_source_counts,
)


@dataclass
class ValidatedInput:
    """The reusable validated/normalized input the KPI tasks consume."""

    week_start: date
    events: list[NormalizedEvent]
    rejections: list[Rejection]
    records_extracted: int
    records_deduplicated: int
    duplicate_payload_conflict_count: int
    order_identity_anomaly_count: int
    order_identity_missing_count: int
    source_event_counts: dict[str, int]
    office_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_start": self.week_start.isoformat(),
            "events": [event.as_dict() for event in self.events],
            "rejections": [rejection.to_dict() for rejection in self.rejections],
            "records_extracted": self.records_extracted,
            "records_deduplicated": self.records_deduplicated,
            "duplicate_payload_conflict_count": (
                self.duplicate_payload_conflict_count
            ),
            "order_identity_anomaly_count": self.order_identity_anomaly_count,
            "order_identity_missing_count": self.order_identity_missing_count,
            "source_event_counts": dict(self.source_event_counts),
            "office_counts": dict(self.office_counts),
        }


def validate_and_dedupe(
    raw_rows: list[Mapping[str, Any]],
    *,
    week_start: date,
) -> ValidatedInput:
    """Deduplicate, normalize, and validate raw rows for one week.

    This is the cached validation/normalization boundary: it returns reusable
    validated input. Aggregation happens afterwards in the transform subflow
    through the four domain KPI tasks and the pure assembler.
    """
    deduped = deduplicate_rows(raw_rows)
    normalization = normalize_rows(deduped.rows, target_week_start=week_start)
    source_event_counts, office_counts = raw_source_counts(raw_rows)
    return ValidatedInput(
        week_start=week_start,
        events=normalization.events,
        rejections=normalization.rejections,
        records_extracted=deduped.records_extracted,
        records_deduplicated=len(deduped.rows),
        duplicate_payload_conflict_count=deduped.duplicate_payload_conflict_count,
        order_identity_anomaly_count=normalization.order_identity_anomaly_count,
        order_identity_missing_count=normalization.order_identity_missing_count,
        source_event_counts=source_event_counts,
        office_counts=office_counts,
    )
