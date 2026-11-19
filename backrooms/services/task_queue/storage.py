"""Dead letter queue persistence for the async task queue.

When a Celery task exhausts its retries, the failure is recorded here with
``task_id``, task name, attempt number, error message, and timestamp. Follows
the ``job_runner`` storage pattern: the SQL migration under ``migrations/``
is authoritative for PostgreSQL, while the SQLAlchemy metadata below lets
SQLite-backed tests create the same table without a PostgreSQL server.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    Table,
    Text,
    Uuid,
    create_engine,
    select,
)
from sqlalchemy.engine import Engine

MIGRATION_PATH = Path(__file__).resolve().parent / "migrations" / "001_dead_letter_tasks.sql"

dead_letter_metadata = MetaData(schema="task_queue")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


dead_letter_tasks = Table(
    "dead_letter_tasks",
    dead_letter_metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("task_id", Text, nullable=False),
    Column("task_name", Text, nullable=False),
    Column("attempt", Integer, nullable=False),
    Column("error_message", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, default=_utcnow),
)

_engine: Engine | None = None


class DeadLetterStorageUnavailableError(RuntimeError):
    """Raised when no database connection is configured for the DLQ."""


def _database_url() -> str:
    url = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_URL")
    if not url:
        raise DeadLetterStorageUnavailableError(
            "DATABASE_URL must be configured to persist dead letter tasks"
        )
    # Pin the psycopg2 driver explicitly (mirrors Inventory-API/database.py)
    # so Supabase URIs can be pasted verbatim from the dashboard.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    return url


def get_engine() -> Engine:
    """Return the lazily-created engine for ``DATABASE_URL``."""
    global _engine
    if _engine is None:
        _engine = create_engine(_database_url(), pool_pre_ping=True)
    return _engine


def ensure_dead_letter_table(engine: Engine | None = None) -> None:
    """Idempotently make ``task_queue.dead_letter_tasks`` available.

    PostgreSQL applies the authoritative migration. SQLite test engines get
    an attached in-memory ``task_queue`` database plus the mirrored metadata.
    """
    target = engine or get_engine()
    if target.dialect.name == "postgresql":
        sql = MIGRATION_PATH.read_text(encoding="utf-8")
        with target.begin() as connection:
            connection.exec_driver_sql(sql)
        return
    with target.connect() as connection:
        try:
            connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS task_queue")
            connection.commit()
        except Exception:  # noqa: BLE001 - already attached is fine
            pass
    dead_letter_metadata.create_all(target)


def record_dead_letter(
    *,
    task_id: str,
    task_name: str,
    attempt: int,
    error: str,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Persist one exhausted task as a dead letter row."""
    target = engine or get_engine()
    now = _utcnow()
    with target.begin() as connection:
        connection.execute(
            dead_letter_tasks.insert().values(
                task_id=task_id,
                task_name=task_name,
                attempt=attempt,
                error_message=error,
                created_at=now,
            )
        )
    return {
        "task_id": task_id,
        "task_name": task_name,
        "attempt": attempt,
        "error_message": error,
        "created_at": now,
    }


def list_dead_letter(
    limit: int = 50, engine: Engine | None = None
) -> list[dict[str, Any]]:
    """Return the most recent dead letter rows, newest first."""
    target = engine or get_engine()
    with target.connect() as connection:
        rows = (
            connection.execute(
                select(dead_letter_tasks)
                .order_by(dead_letter_tasks.c.created_at.desc())
                .limit(limit)
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


__all__ = [
    "MIGRATION_PATH",
    "DeadLetterStorageUnavailableError",
    "dead_letter_metadata",
    "dead_letter_tasks",
    "ensure_dead_letter_table",
    "get_engine",
    "list_dead_letter",
    "record_dead_letter",
]
