"""Idempotent transactional load into the reporting schema."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine

from .schema import (
    pipeline_rejected_events,
    weekly_office_program_performance,
)

KPI_UPDATE_COLUMNS = (
    "total_material_cost",
    "kits_delivered_count",
    "shortage_events_count",
    "cost_variance_events_count",
    "currency",
    "computed_at",
)


@dataclass
class LoadResult:
    records_loaded: int
    quarantined: int

    def to_dict(self) -> dict[str, int]:
        return {
            "records_loaded": self.records_loaded,
            "quarantined": self.quarantined,
        }


def _prepare_kpi_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for row in rows:
        week_start = row["week_start"]
        if isinstance(week_start, str):
            week_start = date.fromisoformat(week_start)
        prepared.append(
            {
                "office": row["office"],
                "programme_id": row["programme_id"],
                "week_start": week_start,
                "total_material_cost": Decimal(str(row["total_material_cost"])),
                "kits_delivered_count": int(row["kits_delivered_count"]),
                "shortage_events_count": int(row["shortage_events_count"]),
                "cost_variance_events_count": int(row["cost_variance_events_count"]),
                "currency": row["currency"],
            }
        )
    return prepared


def _quarantine_identity(rejection: dict[str, Any]) -> str:
    event_id = rejection.get("event_id")
    if event_id:
        return str(event_id)
    digest = hashlib.sha256(
        json.dumps(rejection, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    return f"unidentified:{digest}"


def _prepare_rejections(
    rejections: list[dict[str, Any]], run_id: uuid.UUID
) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for rejection in rejections:
        prepared.append(
            {
                "run_id": run_id,
                "event_id": _quarantine_identity(rejection),
                "event_type": str(rejection.get("event_type") or "unknown"),
                "reason": str(rejection.get("reason") or "unknown"),
                "details": dict(rejection.get("details") or {}),
            }
        )
    return prepared


def load_week(
    engine: Engine,
    *,
    week_start: date,
    rows: list[dict[str, Any]],
    rejections: list[dict[str, Any]],
    run_id: str | uuid.UUID,
    computed_at: datetime | None = None,
) -> LoadResult:
    """Upsert one full week and its quarantine rows in one transaction.

    The KPI upsert omits ``id`` from the update set, so an existing row keeps
    its identity. Quarantine inserts are idempotent for the same run, source
    event, event type, and reason.
    """
    run_uuid = run_id if isinstance(run_id, uuid.UUID) else uuid.UUID(str(run_id))
    now = computed_at or datetime.now(timezone.utc)
    prepared_rows = _prepare_kpi_rows(rows)
    prepared_rejections = _prepare_rejections(rejections, run_uuid)

    with engine.begin() as connection:
        if prepared_rows:
            values = [{**row, "computed_at": now} for row in prepared_rows]
            if engine.dialect.name == "postgresql":
                statement = postgres_insert(weekly_office_program_performance).values(values)
                statement = statement.on_conflict_do_update(
                    index_elements=["office", "programme_id", "week_start"],
                    set_={
                        column: getattr(statement.excluded, column)
                        for column in KPI_UPDATE_COLUMNS
                    },
                )
            else:
                statement = sqlite_insert(weekly_office_program_performance).values(values)
                statement = statement.on_conflict_do_update(
                    index_elements=["office", "programme_id", "week_start"],
                    set_={
                        column: getattr(statement.excluded, column)
                        for column in KPI_UPDATE_COLUMNS
                    },
                )
            connection.execute(statement)

        if prepared_rejections:
            if engine.dialect.name == "postgresql":
                statement = postgres_insert(pipeline_rejected_events).values(
                    prepared_rejections
                )
            else:
                statement = sqlite_insert(pipeline_rejected_events).values(
                    prepared_rejections
                )
            statement = statement.on_conflict_do_nothing(
                index_elements=["run_id", "event_id", "event_type", "reason"]
            )
            connection.execute(statement)

    return LoadResult(
        records_loaded=len(prepared_rows),
        quarantined=len(prepared_rejections),
    )


def delete_week(engine: Engine, week_start: date, *, run_id: str | None = None) -> int:
    """Delete one week; used only by integration tests."""
    with engine.begin() as connection:
        result = connection.execute(
            delete(weekly_office_program_performance).where(
                weekly_office_program_performance.c.week_start == week_start
            )
        )
    return int(result.rowcount or 0)
