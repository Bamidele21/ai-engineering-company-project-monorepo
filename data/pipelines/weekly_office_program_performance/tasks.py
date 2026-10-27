"""Prefect task definitions for the weekly performance pipeline."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from typing import Any

from prefect import task
from prefect.context import TaskRunContext
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from data.process.weekly_performance.errors import PipelineError
from data.process.weekly_performance.transform import transform_week

from . import config, db, extract, load, run_log


def _retry_on_transient(task: Any, task_run: Any, state: Any) -> bool:
    """Retry only infrastructure failures, never deterministic validation."""
    if not state.is_failed():
        return False
    try:
        state.result()
    except Exception as error:  # noqa: BLE001 - inspecting the task failure
        if isinstance(
            error,
            (PipelineError, IntegrityError, ProgrammingError, ValueError, TypeError),
        ):
            return False
        return isinstance(error, (DBAPIError, ConnectionError, TimeoutError, OSError))
    return False


@task(
    name="extract_weekly_telemetry",
    retries=config.RETRY_COUNT,
    retry_delay_seconds=config.RETRY_DELAYS_SECONDS,
    retry_condition_fn=_retry_on_transient,
    log_prints=True,
)
def extract_weekly_telemetry(week_start: str) -> dict[str, Any]:
    """Read one UTC week of allowlisted telemetry and the dimension scaffold."""
    result = extract.extract_week(db.get_engine(), date.fromisoformat(week_start))
    return result.to_dict()


def _transform_cache_key(context: TaskRunContext, parameters: dict[str, Any]) -> str:
    """Hash normalized inputs, target week, dimensions, and the transform version.

    ``run_id``, credentials, and connection objects are deliberately absent.
    Late events, changed costs, and dimension changes change the hash and force
    a cache miss; the payload is material for the full transformation.
    """
    payload = {
        "transformation_version": config.transformation_version(),
        "week_start": parameters.get("week_start"),
        "raw_rows": parameters.get("raw_rows"),
        "dimension_pairs": parameters.get("dimension_pairs"),
        "known_programmes": parameters.get("known_programmes"),
        "rejection_threshold": str(config.rejection_threshold()),
    }
    serialized = json.dumps(
        payload, sort_keys=True, default=str, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


@task(
    name="transform_weekly_performance",
    cache_key_fn=_transform_cache_key,
    cache_expiration=config.TRANSFORM_CACHE_EXPIRATION,
    persist_result=True,
    log_prints=True,
)
def transform_weekly_performance(
    raw_rows: list[dict[str, Any]],
    dimension_pairs: list[list[str]],
    known_programmes: list[str],
    week_start: str,
) -> dict[str, Any]:
    """Deduplicate, validate, aggregate, zero-fill, and reconcile one week."""
    result = transform_week(
        raw_rows,
        week_start=date.fromisoformat(week_start),
        dimension_pairs=[tuple(pair) for pair in dimension_pairs],
        known_programmes=known_programmes,
        rejection_threshold=config.rejection_threshold(),
    )
    return result.to_dict()


@task(
    name="load_weekly_performance",
    retries=config.RETRY_COUNT,
    retry_delay_seconds=config.RETRY_DELAYS_SECONDS,
    retry_condition_fn=_retry_on_transient,
    log_prints=True,
)
def load_weekly_performance(
    week_start: str,
    rows: list[dict[str, Any]],
    rejections: list[dict[str, Any]],
    run_id: str,
) -> dict[str, Any]:
    """Upsert one week and its quarantine rows in a single transaction."""
    result = load.load_week(
        db.get_engine(),
        week_start=date.fromisoformat(week_start),
        rows=rows,
        rejections=rejections,
        run_id=run_id,
    )
    return result.to_dict()


def _parse_create_fields(create: dict[str, Any]) -> dict[str, Any]:
    parsed = dict(create)
    parsed["target_weeks"] = [
        date.fromisoformat(value) for value in create.get("target_weeks", [])
    ]
    for key in ("source_window_start", "source_window_end"):
        value = create[key]
        parsed[key] = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    return parsed


@task(
    name="record_pipeline_run",
    retries=config.RETRY_COUNT,
    retry_delay_seconds=config.RETRY_DELAYS_SECONDS,
    retry_condition_fn=_retry_on_transient,
    log_prints=False,
)
def record_pipeline_run(
    run_id: str,
    stage: str,
    status: str,
    *,
    fields: dict[str, Any] | None = None,
    create: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create/adopt, heartbeat, checkpoint, or finalize the audit row."""
    engine = db.get_engine()
    if create is not None:
        run_log.create_or_adopt_run(
            engine,
            run_id=run_id,
            **_parse_create_fields(create),
        )
    elif status in run_log.TERMINAL_STATUSES:
        updates = dict(fields or {})
        checkpoint_week = updates.get("checkpoint_week")
        if isinstance(checkpoint_week, str):
            updates["checkpoint_week"] = date.fromisoformat(checkpoint_week)
        run_log.finalize_run(engine, run_id, status=status, **updates)
    else:
        updates = dict(fields or {})
        checkpoint_week = updates.get("checkpoint_week")
        if isinstance(checkpoint_week, str):
            updates["checkpoint_week"] = date.fromisoformat(checkpoint_week)
        run_log.update_run(
            engine,
            run_id,
            status=status,
            heartbeat_at=datetime.now().astimezone(),
            **updates,
        )
    return {"run_id": run_id, "stage": stage, "status": status}


@task(name="write_eval_snapshot")
def write_eval_snapshot(
    run_id: str,
    week_start: str,
    summary: dict[str, Any],
    fail: bool = False,
) -> dict[str, Any]:
    """Optional sanitized evidence snapshot; failure must not fail publication."""
    if fail:
        raise RuntimeError("Injected optional eval-snapshot failure")
    directory = config.snapshot_directory()
    path = directory / f"run_{run_id}.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)
    return {"path": str(path)}
