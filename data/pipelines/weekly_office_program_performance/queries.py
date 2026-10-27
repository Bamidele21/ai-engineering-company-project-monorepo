"""Read-only report queries used by the reporting API."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from data.process.weekly_performance.constants import most_recent_complete_week
from data.process.weekly_performance.errors import (
    InvalidWeekError,
    NoReportFoundError,
)

from .schema import weekly_office_program_performance


def validate_requested_week(week_start: date) -> None:
    if not isinstance(week_start, date):
        raise InvalidWeekError("week_start must be an ISO date")
    if week_start.weekday() != 0:
        raise InvalidWeekError("week_start must be a Monday")
    if week_start > most_recent_complete_week():
        raise InvalidWeekError("week_start must be a completed ISO week")


def _entry(row: dict[str, Any]) -> dict[str, Any]:
    cost = row["total_material_cost"]
    if not isinstance(cost, Decimal):
        cost = Decimal(str(cost))
    return {
        "office": row["office"],
        "programme_id": row["programme_id"],
        "total_material_cost": cost.quantize(Decimal("0.01")),
        "kits_delivered_count": int(row["kits_delivered_count"]),
        "shortage_events_count": int(row["shortage_events_count"]),
        "cost_variance_events_count": int(row["cost_variance_events_count"]),
        "currency": row["currency"],
    }


def get_weekly_report(session: Any, week_start: date | None = None) -> dict[str, Any]:
    """Return every office/programme row for a completed week.

    When ``week_start`` is omitted, the greatest published ``week_start`` is
    used. Recomputing an older week therefore never moves the default report
    backwards.
    """
    if week_start is None:
        week_start = session.execute(
            select(func.max(weekly_office_program_performance.c.week_start))
        ).scalar_one_or_none()
        if week_start is None:
            raise NoReportFoundError("No weekly report has been computed yet")
    else:
        validate_requested_week(week_start)

    rows = (
        session.execute(
            select(weekly_office_program_performance)
            .where(weekly_office_program_performance.c.week_start == week_start)
            .order_by(
                weekly_office_program_performance.c.office,
                weekly_office_program_performance.c.programme_id,
            )
        )
        .mappings()
        .all()
    )
    if not rows:
        raise NoReportFoundError(
            f"No weekly report has been computed for {week_start.isoformat()}"
        )

    return {
        "week_start": week_start.isoformat(),
        "entries": [_entry(dict(row)) for row in rows],
    }


def get_computed_weeks(session: Any, limit: int = 52) -> list[date]:
    rows = session.execute(
        select(weekly_office_program_performance.c.week_start)
        .distinct()
        .order_by(weekly_office_program_performance.c.week_start.desc())
        .limit(limit)
    ).scalars()
    return [row for row in rows]


def decode_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value
