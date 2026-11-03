"""State machine for the nightly orchestration ``reporting.job_runs`` log.

Every function takes an ``Engine`` so the service stays usable from a
standalone process (the nightly script) and from tests. The ``processing``
status is the distributed lock: at most one processing row per job, enforced
by the ``ux_job_runs_one_processing`` partial unique index.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import Engine

from .storage import _utcnow, job_runs

logger = logging.getLogger("nexova.job_runner")

JOB_NAME = "nightly_export"
STALE_PROCESSING_MINUTES = 360
PROCESSING_STATUS = "processing"
TERMINAL_STATUSES = ("completed", "failed")

_ERROR_MESSAGE_LIMIT = 300


def create_run(
    engine: Engine, *, job_name: str, target_date: date
) -> uuid.UUID:
    """Insert a fresh ``pending`` run and return its id."""
    run_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            job_runs.insert().values(
                id=run_id,
                job_name=job_name,
                target_date=target_date,
                status="pending",
                created_at=_utcnow(),
            )
        )
    return run_id


def claim_run(engine: Engine, run_id: uuid.UUID) -> bool:
    """Transition ``pending`` to ``processing``; False when already claimed.

    Raises ``IntegrityError`` when another row holds the processing lock for
    the same job, so the caller can abort silently after losing a claim race.
    """
    with engine.begin() as connection:
        result = connection.execute(
            update(job_runs)
            .where(job_runs.c.id == run_id, job_runs.c.status == "pending")
            .values(status=PROCESSING_STATUS, started_at=_utcnow())
        )
    return bool(result.rowcount)


def delete_run(engine: Engine, run_id: uuid.UUID) -> None:
    """Best-effort cleanup of a pending row after a lost claim race."""
    with engine.begin() as connection:
        connection.execute(
            delete(job_runs).where(
                job_runs.c.id == run_id, job_runs.c.status == "pending"
            )
        )


def has_processing_lock(engine: Engine, *, job_name: str) -> bool:
    with engine.connect() as connection:
        row = connection.execute(
            select(job_runs.c.id)
            .where(
                job_runs.c.job_name == job_name,
                job_runs.c.status == PROCESSING_STATUS,
            )
            .limit(1)
        ).first()
    return row is not None


def has_completed_for_date(
    engine: Engine, *, job_name: str, target_date: date
) -> bool:
    with engine.connect() as connection:
        row = connection.execute(
            select(job_runs.c.id)
            .where(
                job_runs.c.job_name == job_name,
                job_runs.c.target_date == target_date,
                job_runs.c.status == "completed",
            )
            .limit(1)
        ).first()
    return row is not None


def finalize_run(
    engine: Engine,
    run_id: uuid.UUID,
    *,
    status: Literal["completed", "failed"],
    error_message: str | None = None,
) -> None:
    if status not in TERMINAL_STATUSES:
        raise ValueError(f"Unsupported terminal status: {status}")
    with engine.begin() as connection:
        connection.execute(
            update(job_runs)
            .where(job_runs.c.id == run_id)
            .values(
                status=status,
                finished_at=_utcnow(),
                error_message=error_message,
            )
        )


def recover_stale_runs(
    engine: Engine,
    *,
    job_name: str = JOB_NAME,
    stale_minutes: int = STALE_PROCESSING_MINUTES,
) -> int:
    """Mark abandoned processing rows failed so they stop blocking the job.

    A hard crash (kill -9, OOM) cannot run the failure handler, so the next
    execution reclaims any processing row older than ``stale_minutes``.
    """
    now = _utcnow()
    cutoff = now - timedelta(minutes=stale_minutes)
    with engine.begin() as connection:
        result = connection.execute(
            update(job_runs)
            .where(
                job_runs.c.job_name == job_name,
                job_runs.c.status == PROCESSING_STATUS,
                func.coalesce(job_runs.c.started_at, job_runs.c.created_at)
                < cutoff,
            )
            .values(
                status="failed",
                finished_at=now,
                error_message="marked failed: stale processing lock",
            )
        )
    return int(result.rowcount or 0)


def get_run(engine: Engine, run_id: uuid.UUID) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = connection.execute(
            select(job_runs).where(job_runs.c.id == run_id)
        ).mappings().first()
    return dict(row) if row else None


def sanitize_error(error: BaseException) -> str:
    """Return a short message with no payload or secrets."""
    message = str(error).strip() or type(error).__name__
    return message[:_ERROR_MESSAGE_LIMIT]


__all__ = [
    "JOB_NAME",
    "STALE_PROCESSING_MINUTES",
    "claim_run",
    "create_run",
    "delete_run",
    "finalize_run",
    "get_run",
    "has_completed_for_date",
    "has_processing_lock",
    "recover_stale_runs",
    "sanitize_error",
]
