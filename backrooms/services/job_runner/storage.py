"""Table definition and idempotent bootstrap for ``reporting.job_runs``.

The SQL migration in ``job_runner/migrations`` is authoritative for
PostgreSQL. This metadata object mirrors it so SQLite-backed tests can create
the same table without a PostgreSQL server.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Index,
    MetaData,
    Table,
    Text,
    Uuid,
    text,
)
from sqlalchemy.engine import Engine

MIGRATION_PATH = Path(__file__).resolve().parent / "migrations" / "001_job_runs.sql"

job_runs_metadata = MetaData(schema="reporting")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


job_runs = Table(
    "job_runs",
    job_runs_metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("job_name", Text, nullable=False),
    Column("target_date", Date, nullable=False),
    Column("status", Text, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("error_message", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, default=_utcnow),
    CheckConstraint(
        "status in ('pending', 'processing', 'completed', 'failed')",
        name="ck_job_runs_status",
    ),
)
Index(
    "ix_job_runs_job_target",
    job_runs.c.job_name,
    job_runs.c.target_date,
)
Index(
    "ux_job_runs_one_processing",
    job_runs.c.job_name,
    unique=True,
    postgresql_where=text("status = 'processing'"),
    sqlite_where=text("status = 'processing'"),
)


def ensure_job_runs_table(engine: Engine) -> None:
    """Idempotently make ``reporting.job_runs`` available; safe on every start.

    PostgreSQL applies the authoritative migration. SQLite test engines get an
    attached in-memory ``reporting`` database plus the mirrored metadata.
    """
    if engine.dialect.name == "postgresql":
        sql = MIGRATION_PATH.read_text(encoding="utf-8")
        with engine.begin() as connection:
            connection.exec_driver_sql(sql)
        return
    with engine.connect() as connection:
        try:
            connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS reporting")
            connection.commit()
        except Exception:  # noqa: BLE001 - already attached is fine
            pass
    job_runs_metadata.create_all(engine)


__all__ = [
    "MIGRATION_PATH",
    "ensure_job_runs_table",
    "job_runs",
    "job_runs_metadata",
]
