"""Domain subflows for the weekly performance pipeline.

Each subflow has explicit inputs and outputs and can be executed independently.
The main flow coordinates them; it does not contain their logic.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from prefect import flow

from data.process.weekly_performance.aggregate import assemble_week

from . import config
from .tasks import (
    compute_total_material_cost,
    count_cost_variance_events,
    count_kits_delivered,
    count_shortage_events,
    extract_weekly_telemetry,
    load_weekly_performance,
    transform_weekly_performance,
    write_eval_snapshot,
)


@flow(name="extract_weekly_office_program_telemetry_flow", log_prints=True)
def extract_weekly_office_program_telemetry_flow(week_start: str) -> dict[str, Any]:
    """Extract allowlisted telemetry rows and the dimension scaffold."""
    return extract_weekly_telemetry(week_start)


@flow(name="transform_weekly_office_program_performance_flow", log_prints=True)
def transform_weekly_office_program_performance_flow(
    raw_rows: list[dict[str, Any]],
    dimension_pairs: list[list[str]],
    known_programmes: list[str],
    week_start: str,
) -> dict[str, Any]:
    """Validate, then compute the four KPIs, assemble rows, and reconcile."""
    validated = transform_weekly_performance(
        raw_rows,
        dimension_pairs,
        known_programmes,
        week_start,
    )
    events = validated["events"]
    cost = compute_total_material_cost(events)
    kits = count_kits_delivered(events)
    shortages = count_shortage_events(events)
    variances = count_cost_variance_events(events)

    assembled = assemble_week(
        week_start=date.fromisoformat(week_start),
        events=events,
        rejections=validated["rejections"],
        cost_by_pair=cost,
        kits_by_pair=kits,
        shortages_by_pair=shortages,
        variances_by_pair=variances,
        dimension_pairs=[tuple(pair) for pair in dimension_pairs],
        known_programmes=known_programmes,
        records_extracted=validated["records_extracted"],
        records_deduplicated=validated["records_deduplicated"],
        duplicate_payload_conflict_count=validated[
            "duplicate_payload_conflict_count"
        ],
        order_identity_anomaly_count=validated["order_identity_anomaly_count"],
        order_identity_missing_count=validated["order_identity_missing_count"],
        rejection_threshold=config.rejection_threshold(),
    )

    return {
        "week_start": week_start,
        "rows": [
            {
                **row,
                "week_start": row["week_start"].isoformat(),
                "total_material_cost": str(row["total_material_cost"]),
            }
            for row in assembled.rows
        ],
        "rejections": validated["rejections"],
        "reconciliation": assembled.reconciliation,
        "publication_blocked": assembled.publication_blocked,
        "block_reasons": assembled.block_reasons,
        "records_extracted": validated["records_extracted"],
        "records_deduplicated": validated["records_deduplicated"],
        "records_rejected": len(validated["rejections"]),
        "source_event_counts": validated["source_event_counts"],
        "office_counts": validated["office_counts"],
    }


@flow(name="load_weekly_office_program_performance_flow", log_prints=True)
def load_weekly_office_program_performance_flow(
    week_start: str,
    rows: list[dict[str, Any]],
    rejections: list[dict[str, Any]],
    run_id: str,
) -> dict[str, Any]:
    """Upsert one full week transactionally."""
    return load_weekly_performance(week_start, rows, rejections, run_id)


@flow(name="publish_weekly_performance_snapshot_flow", log_prints=True)
def publish_weekly_performance_snapshot_flow(
    run_id: str,
    week_start: str,
    summary: dict[str, Any],
    fail: bool = False,
) -> dict[str, Any]:
    """Optional sanitized evidence snapshot.

    The main flow invokes this subflow with ``return_state=True`` so a snapshot
    failure never interrupts publication.
    """
    return write_eval_snapshot(
        run_id=run_id,
        week_start=week_start,
        summary=summary,
        fail=fail,
    )
