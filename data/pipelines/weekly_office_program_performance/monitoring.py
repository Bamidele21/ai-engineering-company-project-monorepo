"""Freshness, silence, and baseline health checks for the weekly pipeline.

The health checks run independently of the ETL: they only read
``reporting.pipeline_runs`` and never modify committed data. Alert delivery is
the optional ``alert_weekly_performance_flow`` subflow, which is non-critical
and cannot undo published rows.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from prefect import flow
from prefect.logging import get_run_logger

from data.process.weekly_performance.constants import OFFICES, PIPELINE_NAME

from . import db, run_log

MISSED_RUN_DAYS = 8
STALE_MINUTES = 15
BASELINE_RUNS = 8
MINIMUM_BASELINE_RUNS = 2


def _completed_runs(engine, pipeline_name: str, limit: int = 100) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from .schema import pipeline_runs

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
            .limit(limit)
        ).mappings().all()
    return [dict(row) for row in rows]


def _active_runs(engine, pipeline_name: str) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from .schema import pipeline_runs

    with engine.connect() as connection:
        rows = connection.execute(
            select(pipeline_runs)
            .where(
                pipeline_runs.c.pipeline_name == pipeline_name,
                pipeline_runs.c.status.in_(run_log.ACTIVE_STATUSES),
            )
        ).mappings().all()
    return [dict(row) for row in rows]


def _office_activity(source_event_counts: dict[str, Any], office: str) -> int:
    return int(source_event_counts.get(office, 0) or 0)


def run_health_checks(
    engine,
    *,
    pipeline_name: str = PIPELINE_NAME,
    missed_run_days: int = MISSED_RUN_DAYS,
    stale_minutes: int = STALE_MINUTES,
    baseline_runs: int = BASELINE_RUNS,
) -> dict[str, Any]:
    """Return alerts plus an eight-week baseline with an explicit status.

    Alerts are dictionaries with an ``alert`` code and a sanitized message.
    ``baseline_status`` is ``insufficient_baseline`` when fewer than two prior
    completed runs exist; it is a label, not an alert.
    """
    now = datetime.now(timezone.utc)
    alerts: list[dict[str, Any]] = []

    completed = _completed_runs(engine, pipeline_name)
    active = _active_runs(engine, pipeline_name)
    latest = run_log.latest_run(engine, pipeline_name=pipeline_name)

    for run in active:
        heartbeat = run.get("heartbeat_at") or run.get("started_at") or run.get("created_at")
        if heartbeat is None:
            continue
        if heartbeat.tzinfo is None:
            heartbeat = heartbeat.replace(tzinfo=timezone.utc)
        if now - heartbeat.astimezone(timezone.utc) > timedelta(minutes=stale_minutes):
            alerts.append(
                {
                    "alert": "stale_run",
                    "run_id": str(run["run_id"]),
                    "message": "A queued or running run has a stale heartbeat",
                }
            )

    if latest is not None and latest["status"] == "failed":
        alerts.append(
            {
                "alert": "weekly_run_failed",
                "run_id": str(latest["run_id"]),
                "message": f"The latest pipeline run failed ({latest.get('error_code') or 'unknown'})",
            }
        )

    if not completed:
        alerts.append(
            {
                "alert": "weekly_run_missing",
                "message": "No completed pipeline run exists yet",
            }
        )
    else:
        newest = completed[0]
        finished_at = newest.get("finished_at")
        if finished_at is not None:
            if finished_at.tzinfo is None:
                finished_at = finished_at.replace(tzinfo=timezone.utc)
            if now - finished_at.astimezone(timezone.utc) > timedelta(days=missed_run_days):
                alerts.append(
                    {
                        "alert": "weekly_run_missing",
                        "message": (
                            f"No completed run in the last {missed_run_days} days"
                        ),
                    }
                )

        if int(newest.get("records_rejected") or 0) > 0:
            alerts.append(
                {
                    "alert": "rejected_events",
                    "run_id": str(newest["run_id"]),
                    "message": "The latest completed run quarantined rejected events",
                }
            )

        reconciliation = run_log.decode_json(newest.get("reconciliation"), {})
        warnings = reconciliation.get("warnings") if isinstance(reconciliation, dict) else None
        if warnings:
            alerts.append(
                {
                    "alert": "reconciliation_warning",
                    "run_id": str(newest["run_id"]),
                    "message": f"The latest completed run recorded warnings: {warnings}",
                }
            )

        extracted = int(newest.get("records_extracted") or 0)
        office_counts = run_log.decode_json(newest.get("office_counts"), {})
        prior = completed[1 : baseline_runs + 1]

        if extracted == 0:
            if any(
                sum(
                    int(
                        run_log.decode_json(run.get("office_counts"), {}).get(
                            office, 0
                        )
                        or 0
                    )
                    > 0
                    for office in OFFICES
                )
                for run in prior
            ):
                alerts.append(
                    {
                        "alert": "unexpected_silence",
                        "run_id": str(newest["run_id"]),
                        "message": (
                            "The latest completed run extracted no events while "
                            "previous weeks had activity"
                        ),
                    }
                )
        else:
            for office in OFFICES:
                office_total = sum(
                    int(
                        run_log.decode_json(run.get("office_counts"), {}).get(
                            office, 0
                        )
                        or 0
                    )
                    for run in prior
                )
                if int(office_counts.get(office, 0) or 0) == 0 and office_total > 0:
                    alerts.append(
                        {
                            "alert": "office_silence",
                            "office": office,
                            "run_id": str(newest["run_id"]),
                            "message": (
                                f"Office {office!r} recorded no events in the "
                                "latest completed run while previous weeks had activity"
                            ),
                        }
                    )

    baseline = {
        "baseline_runs": baseline_runs,
        "prior_completed_runs": len(prior) if completed else 0,
        "insufficient_baseline": (len(prior) if completed else 0) < MINIMUM_BASELINE_RUNS,
        "latest_run_id": str(completed[0]["run_id"]) if completed else None,
    }
    return {
        "checked_at": now.isoformat(),
        "pipeline_name": pipeline_name,
        "baseline_status": (
            "insufficient_baseline" if baseline["insufficient_baseline"] else "available"
        ),
        "alerts": alerts,
        "baseline": baseline,
    }


@flow(name="alert_weekly_performance_flow", log_prints=True)
def alert_weekly_performance_flow(payload: dict[str, Any]) -> str:
    """Optional alert delivery; non-critical and read-only.

    Sends the sanitized alert payload to ``REPORTING_ALERTS_WEBHOOK`` when it is
    configured, and does nothing otherwise. This subflow can never undo
    committed data, so the main flow and the health flow invoke it with
    ``return_state=True``.
    """
    webhook = os.getenv("REPORTING_ALERTS_WEBHOOK")
    if not webhook:
        return "skipped:no_webhook"
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                webhook,
                json={
                    "pipeline_name": payload.get("pipeline_name", PIPELINE_NAME),
                    "run_id": payload.get("run_id"),
                    "status": payload.get("status"),
                    "warnings": payload.get("warnings", []),
                    "error": payload.get("error"),
                    "alerts": payload.get("alerts", []),
                },
            )
        return f"delivered:{response.status_code}"
    except httpx.HTTPError:
        return "delivery_failed"


@flow(name="weekly_performance_health_flow", log_prints=True)
def weekly_performance_health_flow() -> dict[str, Any]:
    """Run the freshness/silence/baseline checks independently of the ETL."""
    logger = get_run_logger()
    checks = run_health_checks(db.get_engine())
    for alert in checks["alerts"]:
        logger.warning("weekly performance alert: %s", alert)
    logger.info(
        "weekly performance health: %s alerts, baseline %s",
        len(checks["alerts"]),
        checks["baseline_status"],
    )
    if checks["alerts"]:
        alert_weekly_performance_flow(
            {
                "pipeline_name": PIPELINE_NAME,
                "status": "health_check",
                "alerts": checks["alerts"],
            },
            return_state=True,
        )
    return checks
