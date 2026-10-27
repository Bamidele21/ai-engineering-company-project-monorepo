"""Orchestration of the pure weekly performance transformation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping

from .aggregate import AggregateResult, aggregate_events
from .constants import REJECTION_THRESHOLD
from .normalize import Rejection, deduplicate_rows, normalize_rows, raw_source_counts


@dataclass
class TransformResult:
    week_start: date
    rows: list[dict[str, Any]]
    rejections: list[Rejection]
    reconciliation: dict[str, Any]
    publication_blocked: bool
    block_reasons: list[str]
    records_extracted: int
    records_deduplicated: int
    records_rejected: int
    source_event_counts: dict[str, int]
    office_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_start": self.week_start.isoformat(),
            "rows": [
                {
                    **row,
                    "week_start": row["week_start"].isoformat(),
                    "total_material_cost": str(row["total_material_cost"]),
                }
                for row in self.rows
            ],
            "rejections": [rejection.to_dict() for rejection in self.rejections],
            "reconciliation": dict(self.reconciliation),
            "publication_blocked": self.publication_blocked,
            "block_reasons": list(self.block_reasons),
            "records_extracted": self.records_extracted,
            "records_deduplicated": self.records_deduplicated,
            "records_rejected": self.records_rejected,
            "source_event_counts": dict(self.source_event_counts),
            "office_counts": dict(self.office_counts),
        }


def transform_week(
    raw_rows: list[Mapping[str, Any]],
    *,
    week_start: date,
    dimension_pairs: Iterable[tuple[str, str]],
    known_programmes: Iterable[str],
    rejection_threshold=REJECTION_THRESHOLD,
) -> TransformResult:
    """Deduplicate, validate, aggregate, zero-fill, and reconcile one week."""
    deduped = deduplicate_rows(raw_rows)
    normalization = normalize_rows(deduped.rows, target_week_start=week_start)
    aggregate: AggregateResult = aggregate_events(
        normalization.events,
        normalization.rejections,
        week_start=week_start,
        dimension_pairs=dimension_pairs,
        known_programmes=known_programmes,
        records_extracted=deduped.records_extracted,
        records_deduplicated=len(deduped.rows),
        duplicate_payload_conflict_count=deduped.duplicate_payload_conflict_count,
        order_identity_anomaly_count=normalization.order_identity_anomaly_count,
        order_identity_missing_count=normalization.order_identity_missing_count,
        rejection_threshold=rejection_threshold,
    )
    source_event_counts, office_counts = raw_source_counts(raw_rows)
    return TransformResult(
        week_start=week_start,
        rows=aggregate.rows,
        rejections=normalization.rejections,
        reconciliation=aggregate.reconciliation,
        publication_blocked=aggregate.publication_blocked,
        block_reasons=aggregate.block_reasons,
        records_extracted=deduped.records_extracted,
        records_deduplicated=len(deduped.rows),
        records_rejected=len(normalization.rejections),
        source_event_counts=source_event_counts,
        office_counts=office_counts,
    )
