"""HTTP-facing validation and error mapping for reporting."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from data.pipelines.weekly_office_program_performance import queries, status, triggers
from data.process.weekly_performance.errors import (
    ActiveRunExistsError,
    DispatchError,
    InvalidRangeError,
    InvalidWeekError,
    NoReportFoundError,
    NoRunFoundError,
    PipelineError,
)

logger = logging.getLogger("nexova.reporting.api")


def _map_error(error: Exception) -> HTTPException:
    if isinstance(error, (InvalidWeekError, InvalidRangeError)):
        return HTTPException(status_code=422, detail=str(error))
    if isinstance(error, (NoReportFoundError, NoRunFoundError)):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, ActiveRunExistsError):
        return HTTPException(status_code=409, detail=str(error))
    if isinstance(error, (DispatchError, SQLAlchemyError)):
        logger.error("reporting dependency unavailable: %s", type(error).__name__)
        return HTTPException(
            status_code=503, detail="Reporting dependency is unavailable"
        )
    if isinstance(error, PipelineError):
        logger.error("reporting pipeline error: %s", error.code)
        return HTTPException(status_code=500, detail="Reporting pipeline error")
    logger.exception("unexpected reporting failure")
    return HTTPException(status_code=500, detail="Reporting request failed")


def get_report(session: Any, week_start: date | None) -> dict[str, Any]:
    try:
        return queries.get_weekly_report(session, week_start)
    except Exception as error:  # noqa: BLE001 - translated to a typed HTTP error
        raise _map_error(error) from error


def get_latest_run(session: Any) -> dict[str, Any]:
    try:
        return status.get_latest_run(session)
    except Exception as error:  # noqa: BLE001 - translated to a typed HTTP error
        raise _map_error(error) from error


def trigger_run(
    session: Any,
    *,
    week_start: date | None,
    weeks: int,
    requested_by: str | None,
) -> dict[str, Any]:
    try:
        return triggers.trigger_manual_run(
            session,
            week_start=week_start,
            weeks=weeks,
            requested_by=requested_by,
        )
    except Exception as error:  # noqa: BLE001 - translated to a typed HTTP error
        raise _map_error(error) from error
