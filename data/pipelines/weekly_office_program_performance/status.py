"""Latest-run status query used by the reporting API."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select

from data.process.weekly_performance.constants import PIPELINE_NAME
from data.process.weekly_performance.errors import NoRunFoundError

from .schema import pipeline_runs


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return default
    return value


def serialize_run(row: dict[str, Any]) -> dict[str, Any]:
    target_weeks = _json_value(row.get("target_weeks"), [])
    checkpoint_week = row.get("checkpoint_week")
    return {
        "run_id": str(row["run_id"]),
        "flow_run_id": row.get("flow_run_id"),
        "pipeline_name": row["pipeline_name"],
        "status": row["status"],
        "trigger_type": row["trigger_type"],
        "triggered_by": row.get("triggered_by"),
        "target_weeks": target_weeks,
        "source_window_start": _iso(row.get("source_window_start")),
        "source_window_end": _iso(row.get("source_window_end")),
        "started_at": _iso(row.get("started_at")),
        "finished_at": _iso(row.get("finished_at")),
        "heartbeat_at": _iso(row.get("heartbeat_at")),
        "checkpoint_stage": row.get("checkpoint_stage"),
        "checkpoint_week": checkpoint_week.isoformat()
        if isinstance(checkpoint_week, date)
        else checkpoint_week,
        "records_extracted": int(row.get("records_extracted") or 0),
        "records_deduplicated": int(row.get("records_deduplicated") or 0),
        "records_rejected": int(row.get("records_rejected") or 0),
        "records_loaded": int(row.get("records_loaded") or 0),
        "source_event_counts": _json_value(row.get("source_event_counts"), {}),
        "office_counts": _json_value(row.get("office_counts"), {}),
        "reconciliation": _json_value(row.get("reconciliation"), {}),
        "supersedes_run_id": str(row["supersedes_run_id"])
        if row.get("supersedes_run_id")
        else None,
        "retry_count": int(row.get("retry_count") or 0),
        "created_at": _iso(row.get("created_at")),
        "error": {
            "code": row.get("error_code"),
            "message": row.get("error_message"),
        }
        if row.get("error_code")
        else None,
    }


def get_latest_run(session: Any) -> dict[str, Any]:
    row = (
        session.execute(
            select(pipeline_runs)
            .where(pipeline_runs.c.pipeline_name == PIPELINE_NAME)
            .order_by(pipeline_runs.c.created_at.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None:
        raise NoRunFoundError("No pipeline run has been recorded yet")
    return serialize_run(dict(row))
