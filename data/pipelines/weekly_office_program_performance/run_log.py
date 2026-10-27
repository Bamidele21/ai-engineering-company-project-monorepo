"""Execution-log repository for ``reporting.pipeline_runs``."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.engine import Engine

from data.process.weekly_performance.constants import PIPELINE_NAME
from data.process.weekly_performance.errors import ActiveRunExistsError, NoRunFoundError

from .schema import pipeline_runs

logger = logging.getLogger("nexova.reporting.run_log")

ACTIVE_STATUSES = ("queued", "running")
TERMINAL_STATUSES = ("completed", "completed_with_warnings", "failed", "skipped_locked")

_ALLOWED_UPDATE_FIELDS = {
    "flow_run_id",
    "status",
    "triggered_by",
    "target_weeks",
    "source_window_start",
    "source_window_end",
    "started_at",
    "finished_at",
    "heartbeat_at",
    "checkpoint_stage",
    "checkpoint_week",
    "records_extracted",
    "records_deduplicated",
    "records_rejected",
    "records_loaded",
    "source_event_counts",
    "office_counts",
    "reconciliation",
    "supersedes_run_id",
    "error_code",
    "error_message",
    "retry_count",
}


def _as_uuid(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def sanitize_error(error: BaseException) -> tuple[str, str]:
    """Return a stable code and a short message with no payload or secrets."""
    from data.process.weekly_performance.errors import PipelineError

    if isinstance(error, PipelineError):
        return error.code, str(error)[:300]
    if isinstance(error, IntegrityError):
        return "constraint_violation", "A reporting constraint rejected the write"
    if isinstance(error, SQLAlchemyError):
        return "database_unavailable", type(error).__name__
    message = str(error).strip() or type(error).__name__
    return "unexpected_error", message[:300]


def recover_stale_runs(
    engine: Engine,
    *,
    pipeline_name: str = PIPELINE_NAME,
    stale_minutes: int = 15,
) -> int:
    """Mark abandoned queued/running rows failed so they stop blocking work."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=stale_minutes)
    with engine.begin() as connection:
        result = connection.execute(
            update(pipeline_runs)
            .where(
                pipeline_runs.c.pipeline_name == pipeline_name,
                pipeline_runs.c.status.in_(ACTIVE_STATUSES),
                _coalesce_heartbeat() < cutoff,
            )
            .values(
                status="failed",
                finished_at=now,
                error_code="stale_run",
                error_message="Run heartbeat expired before completion",
            )
        )
    return int(result.rowcount or 0)


def _coalesce_heartbeat():
    from sqlalchemy import func

    return func.coalesce(
        pipeline_runs.c.heartbeat_at,
        pipeline_runs.c.started_at,
        pipeline_runs.c.created_at,
    )


def get_active_run(
    engine: Engine, *, pipeline_name: str = PIPELINE_NAME
) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = connection.execute(
            select(pipeline_runs)
            .where(
                pipeline_runs.c.pipeline_name == pipeline_name,
                pipeline_runs.c.status.in_(ACTIVE_STATUSES),
            )
            .limit(1)
        ).mappings().first()
    return dict(row) if row else None


def create_or_adopt_run(
    engine: Engine,
    *,
    run_id: str | uuid.UUID | None = None,
    flow_run_id: str | None = None,
    trigger_type: str,
    triggered_by: str | None,
    target_weeks: list[date],
    source_window_start: datetime,
    source_window_end: datetime,
    pipeline_name: str = PIPELINE_NAME,
    supersedes_run_id: str | uuid.UUID | None = None,
) -> dict[str, Any]:
    """Create a run row, or adopt the queued row created by the API."""
    now = datetime.now(timezone.utc)
    run_uuid = _as_uuid(run_id) if run_id else uuid.uuid4()
    target_week_strings = [week.isoformat() for week in target_weeks]

    with engine.begin() as connection:
        existing = connection.execute(
            select(pipeline_runs).where(pipeline_runs.c.run_id == run_uuid)
        ).mappings().first()
        if existing is not None:
            if existing["status"] not in ACTIVE_STATUSES:
                raise ActiveRunExistsError(
                    "The supplied run id already belongs to a finished run"
                )
            connection.execute(
                update(pipeline_runs)
                .where(pipeline_runs.c.run_id == run_uuid)
                .values(
                    status="running",
                    flow_run_id=flow_run_id,
                    started_at=existing["started_at"] or now,
                    heartbeat_at=now,
                    checkpoint_stage="extract",
                )
            )
        else:
            try:
                connection.execute(
                    pipeline_runs.insert().values(
                        run_id=run_uuid,
                        flow_run_id=flow_run_id,
                        pipeline_name=pipeline_name,
                        trigger_type=trigger_type,
                        triggered_by=triggered_by,
                        status="running",
                        target_weeks=target_week_strings,
                        source_window_start=source_window_start,
                        source_window_end=source_window_end,
                        started_at=now,
                        heartbeat_at=now,
                        checkpoint_stage="extract",
                        created_at=now,
                        supersedes_run_id=(
                            _as_uuid(supersedes_run_id)
                            if supersedes_run_id
                            else None
                        ),
                    )
                )
            except IntegrityError as error:
                raise ActiveRunExistsError(
                    "Another pipeline run is already active"
                ) from error

    return get_run(engine, run_uuid) or {}


def get_run(engine: Engine, run_id: str | uuid.UUID) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = connection.execute(
            select(pipeline_runs).where(
                pipeline_runs.c.run_id == _as_uuid(run_id)
            )
        ).mappings().first()
    return dict(row) if row else None


def update_run(engine: Engine, run_id: str | uuid.UUID, **fields: Any) -> None:
    invalid = set(fields) - _ALLOWED_UPDATE_FIELDS
    if invalid:
        raise ValueError(f"Unsupported run-log fields: {sorted(invalid)}")
    if not fields:
        return
    if fields.get("supersedes_run_id") is not None:
        fields["supersedes_run_id"] = _as_uuid(fields["supersedes_run_id"])
    with engine.begin() as connection:
        connection.execute(
            update(pipeline_runs)
            .where(pipeline_runs.c.run_id == _as_uuid(run_id))
            .values(**fields)
        )


def heartbeat(engine: Engine, run_id: str | uuid.UUID) -> None:
    update_run(engine, run_id, heartbeat_at=datetime.now(timezone.utc))


def finalize_run(
    engine: Engine,
    run_id: str | uuid.UUID,
    *,
    status: str,
    **fields: Any,
) -> None:
    fields.setdefault("finished_at", datetime.now(timezone.utc))
    fields.setdefault("heartbeat_at", datetime.now(timezone.utc))
    update_run(
        engine,
        run_id,
        status=status,
        **fields,
    )


def latest_run(
    engine: Engine, *, pipeline_name: str = PIPELINE_NAME
) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = connection.execute(
            select(pipeline_runs)
            .where(pipeline_runs.c.pipeline_name == pipeline_name)
            .order_by(pipeline_runs.c.created_at.desc())
            .limit(1)
        ).mappings().first()
    return dict(row) if row else None


def decode_json(value: Any, default: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return default
    return value if value is not None else default


def decode_target_weeks(row: dict[str, Any]) -> list[date]:
    raw = decode_json(row.get("target_weeks"), [])
    weeks: list[date] = []
    for value in raw if isinstance(raw, list) else []:
        if isinstance(value, str):
            try:
                weeks.append(date.fromisoformat(value))
            except ValueError:
                continue
        elif isinstance(value, date):
            weeks.append(value)
    return sorted(weeks)


def previous_publication(
    engine: Engine,
    week_start: date,
    *,
    exclude_run_id: str | uuid.UUID | None = None,
    pipeline_name: str = PIPELINE_NAME,
) -> tuple[str, str] | None:
    """Return the latest completed run that published ``week_start``.

    Returns ``(run_id, week_fingerprint)`` or ``None``. The fingerprint comes
    from that run's own reconciliation payload, so recomputing a week can detect
    a changed publication and record the supersession.
    """
    excluded = str(exclude_run_id) if exclude_run_id else None
    with engine.connect() as connection:
        rows = connection.execute(
            select(pipeline_runs)
            .where(
                pipeline_runs.c.pipeline_name == pipeline_name,
                pipeline_runs.c.status.in_(
                    ("completed", "completed_with_warnings")
                ),
            )
            .order_by(pipeline_runs.c.created_at.desc())
            .limit(100)
        ).mappings().all()

    target = week_start.isoformat()
    target_date = date.fromisoformat(target)
    for row in rows:
        run_uuid = str(row["run_id"])
        if excluded and run_uuid == excluded:
            continue
        if target_date not in decode_target_weeks(dict(row)):
            continue
        reconciliation = decode_json(row.get("reconciliation"), {})
        weeks = reconciliation.get("weeks") if isinstance(reconciliation, dict) else {}
        fingerprint = (
            weeks.get(target, {}).get("week_fingerprint")
            if isinstance(weeks, dict)
            else None
        )
        if fingerprint:
            return run_uuid, str(fingerprint)
    return None


def plan_resume(
    engine: Engine,
    resume_run_id: str | uuid.UUID,
    *,
    pipeline_name: str = PIPELINE_NAME,
) -> dict[str, Any]:
    """Plan a resume of a failed run.

    Returns the remaining uncommitted weeks (the failed week onwards) together
    with the superseded run identity. Completed weeks are skipped because their
    transactions already committed; the failed week is recomputed in full.
    """
    run = get_run(engine, resume_run_id)
    if run is None:
        raise NoRunFoundError("The run to resume does not exist")
    if run["status"] in ACTIVE_STATUSES:
        raise ActiveRunExistsError("The run to resume is still active")
    if run["status"] in ("completed", "completed_with_warnings"):
        raise NoRunFoundError("The run to resume is already complete")

    weeks = decode_target_weeks(run)
    checkpoint = run.get("checkpoint_week")
    if isinstance(checkpoint, str):
        checkpoint = date.fromisoformat(checkpoint)
    remaining = [week for week in weeks if checkpoint is None or week >= checkpoint]
    return {
        "resume_run_id": str(run["run_id"]),
        "remaining_weeks": [week.isoformat() for week in remaining],
        "supersedes_run_id": str(run["run_id"]),
        "original_checkpoint_stage": run.get("checkpoint_stage"),
        "original_error_code": run.get("error_code"),
    }
