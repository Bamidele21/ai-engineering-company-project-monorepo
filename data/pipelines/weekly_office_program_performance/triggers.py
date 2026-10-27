"""Manual trigger validation and Prefect deployment dispatch."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from data.process.weekly_performance.constants import (
    FLOW_NAME,
    PIPELINE_NAME,
    most_recent_complete_week,
    week_bounds,
)
from data.process.weekly_performance.errors import (
    ActiveRunExistsError,
    DispatchError,
    InvalidRangeError,
    InvalidWeekError,
)

from . import config
from .schema import pipeline_runs

logger = logging.getLogger("nexova.reporting.triggers")


def _validate_request(
    week_start: date | None, weeks: int
) -> tuple[date, list[date]]:
    if isinstance(weeks, bool) or not isinstance(weeks, int) or not 1 <= weeks <= 52:
        raise InvalidRangeError("weeks must be an integer between 1 and 52")

    latest_complete = most_recent_complete_week()
    if week_start is None:
        start = latest_complete - timedelta(weeks=weeks - 1)
    else:
        if not isinstance(week_start, date):
            raise InvalidWeekError("week_start must be an ISO date")
        if week_start.weekday() != 0:
            raise InvalidWeekError("week_start must be a Monday")
        start = week_start

    targets = [start + timedelta(weeks=offset) for offset in range(weeks)]
    if targets[-1] > latest_complete:
        raise InvalidRangeError("the requested range includes an incomplete week")
    return start, targets


def _find_deployment(client: httpx.Client, api_url: str) -> str:
    path = (
        f"{api_url}/deployments/name/"
        f"{config.FLOW_NAME}/{config.prefect_deployment_name()}"
    )
    response = client.get(path)
    if response.status_code == 200:
        return str(response.json()["id"])
    if response.status_code not in (404, 422):
        raise DispatchError(
            f"Prefect deployment lookup failed with status {response.status_code}"
        )

    # Older or renamed deployments: fall back to a bounded list query.
    listing = client.get(f"{api_url}/deployments", params={"limit": 200})
    if listing.status_code != 200:
        raise DispatchError(
            f"Prefect deployment listing failed with status {listing.status_code}"
        )
    for deployment in listing.json():
        if deployment.get("name") == config.prefect_deployment_name():
            return str(deployment["id"])
    raise DispatchError("The reporting deployment is not registered in Prefect")


def dispatch_flow_run(
    *,
    run_id: str,
    week_start: date,
    weeks: int,
    trigger_type: str,
    requested_by: str | None,
) -> str:
    """Submit the flow run to the Prefect API and return the flow run id."""
    api_url = config.prefect_api_url()
    try:
        with httpx.Client(timeout=15.0) as client:
            deployment_id = _find_deployment(client, api_url)
            response = client.post(
                f"{api_url}/deployments/{deployment_id}/create_flow_run",
                json={
                    "parameters": {
                        "week_start": week_start.isoformat(),
                        "weeks": weeks,
                        "trigger_type": trigger_type,
                        "requested_by": requested_by,
                        "run_id": run_id,
                    },
                    "state": {"type": "SCHEDULED"},
                },
            )
    except httpx.HTTPError as error:
        raise DispatchError(
            "The Prefect API could not be reached for dispatch"
        ) from error

    if response.status_code not in (200, 201):
        raise DispatchError(
            f"The Prefect API rejected dispatch with status {response.status_code}"
        )
    return str(response.json().get("id") or "")


def trigger_manual_run(
    session: Any,
    *,
    week_start: date | None = None,
    weeks: int = 1,
    requested_by: str | None = None,
) -> dict[str, Any]:
    """Validate, create a queued run row, then dispatch it to Prefect."""
    start, targets = _validate_request(week_start, weeks)
    engine = session.get_bind()

    from . import run_log

    run_log.recover_stale_runs(
        engine,
        pipeline_name=PIPELINE_NAME,
        stale_minutes=config.stale_run_minutes(),
    )
    if run_log.get_active_run(engine, pipeline_name=PIPELINE_NAME) is not None:
        raise ActiveRunExistsError("Another pipeline run is already active")

    run_id = uuid.uuid4()
    first_start, _ = week_bounds(targets[0])
    _, last_end = week_bounds(targets[-1])
    now = datetime.now(timezone.utc)
    try:
        session.execute(
            insert(pipeline_runs).values(
                run_id=run_id,
                status="queued",
                pipeline_name=PIPELINE_NAME,
                trigger_type="manual",
                triggered_by=requested_by,
                target_weeks=[week.isoformat() for week in targets],
                source_window_start=first_start,
                source_window_end=last_end,
                created_at=now,
            )
        )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise ActiveRunExistsError("Another pipeline run is already active") from error
    except SQLAlchemyError:
        session.rollback()
        raise

    try:
        dispatch_flow_run(
            run_id=str(run_id),
            week_start=start,
            weeks=weeks,
            trigger_type="manual",
            requested_by=requested_by,
        )
    except Exception as error:
        try:
            run_log.update_run(
                engine,
                run_id,
                status="failed",
                finished_at=datetime.now(timezone.utc),
                error_code="dispatch_failed",
                error_message="The flow run could not be dispatched to Prefect",
            )
        except SQLAlchemyError:
            logger.error("dispatch failure could not be recorded")
        if isinstance(error, DispatchError):
            raise
        raise DispatchError("The flow run could not be dispatched to Prefect") from error

    return {
        "run_id": str(run_id),
        "status": "queued",
        "target_weeks": [week.isoformat() for week in targets],
    }
