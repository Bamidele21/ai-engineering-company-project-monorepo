"""Main Prefect flow for the weekly office and programme performance report."""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

from prefect import flow
from prefect.logging import get_run_logger

from data.process.weekly_performance.constants import (
    FLOW_NAME,
    OFFICE_CURRENCY,
    PIPELINE_NAME,
    most_recent_complete_week,
    week_bounds,
)
from data.process.weekly_performance.errors import (
    ActiveRunExistsError,
    InvalidRangeError,
    InvalidWeekError,
    PublicationBlockedError,
)

from . import config, db, run_log
from .schema import ensure_reporting_schema
from .tasks import (
    extract_weekly_telemetry,
    load_weekly_performance,
    record_pipeline_run,
    transform_weekly_performance,
    write_eval_snapshot,
)

_ALLOWED_TRIGGER_TYPES = {"scheduled", "manual", "backfill", "recompute"}


def _resolve_target_weeks(
    week_start: date | None, weeks: int
) -> tuple[list[date], datetime, datetime]:
    if isinstance(weeks, bool) or not isinstance(weeks, int) or not 1 <= weeks <= 52:
        raise InvalidRangeError("weeks must be an integer between 1 and 52")
    latest_complete = most_recent_complete_week()

    if isinstance(week_start, str):
        week_start = date.fromisoformat(week_start)
    if week_start is None:
        start = latest_complete - timedelta(weeks=weeks - 1)
    else:
        if week_start.weekday() != 0:
            raise InvalidWeekError("week_start must be a Monday")
        start = week_start

    targets = [start + timedelta(weeks=offset) for offset in range(weeks)]
    if targets[-1] > latest_complete:
        raise InvalidRangeError("the requested range includes an incomplete week")
    window_start, _ = week_bounds(targets[0])
    _, window_end = week_bounds(targets[-1])
    return targets, window_start, window_end


def _current_flow_run_id() -> str | None:
    try:
        from prefect.context import get_run_context

        return str(get_run_context().flow_run.id)
    except Exception:  # noqa: BLE001 - direct CLI calls have no flow context
        return None


def _merge_counts(target: Counter[str], incoming: dict[str, Any]) -> None:
    for key, value in incoming.items():
        target[str(key)] += int(value)


@flow(name=FLOW_NAME, log_prints=True)
def weekly_office_program_performance_flow(
    week_start: date | None = None,
    weeks: int = 1,
    trigger_type: str = "scheduled",
    requested_by: str | None = None,
    run_id: str | None = None,
    snapshot_failure_injection: bool = False,
) -> dict[str, Any]:
    """Produce the weekly office/programme KPI report.

    CLI example (from the repository root)::

        python data/pipelines/pipeline.py --week-start 2026-10-19 --weeks 1
    """
    logger = get_run_logger()
    if trigger_type not in _ALLOWED_TRIGGER_TYPES:
        raise InvalidRangeError(
            "trigger_type must be scheduled, manual, backfill, or recompute"
        )

    targets, window_start, window_end = _resolve_target_weeks(week_start, weeks)
    run_id = run_id or str(uuid.uuid4())
    flow_run_id = _current_flow_run_id()
    ensure_reporting_schema(db.get_engine())

    totals = {
        "records_extracted": 0,
        "records_deduplicated": 0,
        "records_rejected": 0,
        "records_loaded": 0,
    }
    source_counts: Counter[str] = Counter()
    office_counts: Counter[str] = Counter()
    reconciliation: dict[str, Any] = {"weeks": {}, "warnings": []}
    warnings: list[str] = []
    stage = "extract"
    current_week = targets[0].isoformat()
    run_created = False

    with db.advisory_lock() as acquired:
        if not acquired:
            if trigger_type == "manual":
                raise ActiveRunExistsError("Another pipeline run holds the lock")
            logger.warning("scheduled run skipped because the advisory lock is held")
            return {
                "status": "skipped_locked",
                "run_id": run_id,
                "target_weeks": [week.isoformat() for week in targets],
            }

        try:
            run_log.recover_stale_runs(
                db.get_engine(), stale_minutes=config.stale_run_minutes()
            )
            create_payload = {
                "flow_run_id": flow_run_id,
                "trigger_type": trigger_type,
                "triggered_by": requested_by,
                "target_weeks": [week.isoformat() for week in targets],
                "source_window_start": window_start.isoformat(),
                "source_window_end": window_end.isoformat(),
            }
            try:
                record_pipeline_run(
                    run_id, "extract", "running", create=create_payload
                )
                run_created = True
            except ActiveRunExistsError:
                if trigger_type == "scheduled":
                    logger.warning(
                        "scheduled run skipped because another run is active"
                    )
                    return {
                        "status": "skipped_locked",
                        "run_id": run_id,
                        "target_weeks": [week.isoformat() for week in targets],
                    }
                raise

            for target in targets:
                current_week = target.isoformat()
                stage = "extract"
                record_pipeline_run(
                    run_id,
                    "extract",
                    "running",
                    fields={
                        "checkpoint_stage": "extract",
                        "checkpoint_week": current_week,
                    },
                )
                extracted = extract_weekly_telemetry(current_week)
                totals["records_extracted"] += len(extracted["raw_rows"])
                _merge_counts(source_counts, extracted["source_event_counts"])
                _merge_counts(office_counts, extracted["office_counts"])
                record_pipeline_run(
                    run_id,
                    "extract",
                    "running",
                    fields={
                        "checkpoint_stage": "extract",
                        "checkpoint_week": current_week,
                        "records_extracted": totals["records_extracted"],
                        "source_event_counts": dict(source_counts),
                        "office_counts": dict(office_counts),
                    },
                )

                stage = "transform"
                record_pipeline_run(
                    run_id,
                    "transform",
                    "running",
                    fields={
                        "checkpoint_stage": "transform",
                        "checkpoint_week": current_week,
                    },
                )
                transformed = transform_weekly_performance(
                    extracted["raw_rows"],
                    extracted["dimension_pairs"],
                    extracted["known_programmes"],
                    current_week,
                )
                totals["records_deduplicated"] += int(
                    transformed["records_deduplicated"]
                )
                totals["records_rejected"] += int(transformed["records_rejected"])
                week_reconciliation = dict(transformed["reconciliation"])
                reconciliation["weeks"][current_week] = week_reconciliation

                if transformed["records_rejected"]:
                    warnings.append("rejected_events")
                if week_reconciliation.get("duplicate_payload_conflict_count"):
                    warnings.append("duplicate_payload_conflict")
                if week_reconciliation.get("order_identity_anomaly_count"):
                    warnings.append("order_identity_anomaly")
                if week_reconciliation.get("unknown_programme_ids"):
                    warnings.append("unknown_programme_ids")

                record_pipeline_run(
                    run_id,
                    "transform",
                    "running",
                    fields={
                        "checkpoint_stage": "transform",
                        "checkpoint_week": current_week,
                        "records_deduplicated": totals["records_deduplicated"],
                        "records_rejected": totals["records_rejected"],
                        "reconciliation": {
                            "weeks": reconciliation["weeks"],
                            "warnings": sorted(set(warnings)),
                        },
                    },
                )

                if transformed["publication_blocked"]:
                    reason_text = ", ".join(transformed["block_reasons"])
                    blocked = PublicationBlockedError(
                        f"Publication blocked for {current_week}: {reason_text}"
                    )
                    record_pipeline_run(
                        run_id,
                        stage,
                        "failed",
                        fields={
                            "checkpoint_stage": stage,
                            "checkpoint_week": current_week,
                            "records_extracted": totals["records_extracted"],
                            "records_deduplicated": totals["records_deduplicated"],
                            "records_rejected": totals["records_rejected"],
                            "source_event_counts": dict(source_counts),
                            "office_counts": dict(office_counts),
                            "reconciliation": {
                                "weeks": reconciliation["weeks"],
                                "warnings": sorted(set(warnings)),
                                "block_reasons": transformed["block_reasons"],
                            },
                            "error_code": blocked.code,
                            "error_message": str(blocked),
                        },
                    )
                    raise blocked

                stage = "load"
                loaded = load_weekly_performance(
                    current_week,
                    transformed["rows"],
                    transformed["rejections"],
                    run_id,
                )
                totals["records_loaded"] += int(loaded["records_loaded"])
                record_pipeline_run(
                    run_id,
                    "load",
                    "running",
                    fields={
                        "checkpoint_stage": "load",
                        "checkpoint_week": current_week,
                        "records_loaded": totals["records_loaded"],
                    },
                )

            summary = {
                "run_id": run_id,
                "target_weeks": [week.isoformat() for week in targets],
                "records_loaded": totals["records_loaded"],
                "records_extracted": totals["records_extracted"],
                "records_deduplicated": totals["records_deduplicated"],
                "records_rejected": totals["records_rejected"],
                "warnings": sorted(set(warnings)),
            }
            snapshot_state = write_eval_snapshot(
                run_id=run_id,
                week_start=targets[-1].isoformat(),
                summary=summary,
                fail=snapshot_failure_injection,
                return_state=True,
            )
            if snapshot_state.is_failed():
                warnings.append("eval_snapshot_failed")
                logger.warning(
                    "optional eval snapshot failed; the published report remains valid"
                )

            status = (
                "completed_with_warnings"
                if warnings or totals["records_rejected"]
                else "completed"
            )
            reconciliation["warnings"] = sorted(set(warnings))
            reconciliation["target_weeks"] = [week.isoformat() for week in targets]
            reconciliation["week_fingerprints"] = {
                week: payload.get("week_fingerprint")
                for week, payload in reconciliation["weeks"].items()
            }
            reconciliation["currencies"] = dict(OFFICE_CURRENCY)
            record_pipeline_run(
                run_id,
                "complete",
                status,
                fields={
                    "checkpoint_stage": "complete",
                    "checkpoint_week": targets[-1].isoformat(),
                    "records_extracted": totals["records_extracted"],
                    "records_deduplicated": totals["records_deduplicated"],
                    "records_rejected": totals["records_rejected"],
                    "records_loaded": totals["records_loaded"],
                    "source_event_counts": dict(source_counts),
                    "office_counts": dict(office_counts),
                    "reconciliation": reconciliation,
                },
            )
            return {
                "status": status,
                "run_id": run_id,
                "target_weeks": [week.isoformat() for week in targets],
                "records_loaded": totals["records_loaded"],
                "warnings": sorted(set(warnings)),
                "pipeline_name": PIPELINE_NAME,
            }
        except Exception as error:
            if run_created:
                code, message = run_log.sanitize_error(error)
                try:
                    record_pipeline_run(
                        run_id,
                        stage,
                        "failed",
                        fields={
                            "checkpoint_stage": stage,
                            "checkpoint_week": current_week,
                            "records_extracted": totals["records_extracted"],
                            "records_deduplicated": totals["records_deduplicated"],
                            "records_rejected": totals["records_rejected"],
                            "records_loaded": totals["records_loaded"],
                            "source_event_counts": dict(source_counts),
                            "office_counts": dict(office_counts),
                            "reconciliation": {
                                "weeks": reconciliation["weeks"],
                                "warnings": sorted(set(warnings)),
                            },
                            "error_code": code,
                            "error_message": message,
                        },
                    )
                except Exception:  # noqa: BLE001 - never mask the original failure
                    logger.exception(
                        "pipeline failure could not be written to pipeline_runs"
                    )
            raise
