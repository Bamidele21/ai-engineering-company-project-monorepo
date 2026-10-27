"""SQLAlchemy Core definitions for the ``reporting`` schema.

The SQL migration in ``backrooms/services/reporting/migrations`` is authoritative
for PostgreSQL. These metadata objects mirror it so SQLite-backed API and
pipelines tests can create the same tables without a PostgreSQL server.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

reporting_metadata = MetaData(schema="reporting")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_type():
    return JSON().with_variant(JSONB(), "postgresql")


weekly_office_program_performance = Table(
    "weekly_office_program_performance",
    reporting_metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("office", Text, nullable=False),
    Column("programme_id", Text, nullable=False),
    Column("week_start", Date, nullable=False),
    Column("total_material_cost", Numeric(14, 2), nullable=False, default=0),
    Column("kits_delivered_count", Integer, nullable=False, default=0),
    Column("shortage_events_count", Integer, nullable=False, default=0),
    Column("cost_variance_events_count", Integer, nullable=False, default=0),
    Column("currency", Text, nullable=False),
    Column("computed_at", DateTime(timezone=True), nullable=False, default=_utcnow),
    UniqueConstraint(
        "office",
        "programme_id",
        "week_start",
        name="uq_weekly_performance_grain",
    ),
)
Index(
    "ix_weekly_performance_week_start",
    weekly_office_program_performance.c.week_start,
)

pipeline_runs = Table(
    "pipeline_runs",
    reporting_metadata,
    Column("run_id", Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("flow_run_id", Text, nullable=True),
    Column("pipeline_name", Text, nullable=False),
    Column("trigger_type", Text, nullable=False),
    Column("triggered_by", Text, nullable=True),
    Column("status", Text, nullable=False),
    Column("target_weeks", _json_type(), nullable=False, default=list),
    Column("source_window_start", DateTime(timezone=True), nullable=False),
    Column("source_window_end", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("heartbeat_at", DateTime(timezone=True), nullable=True),
    Column("checkpoint_stage", Text, nullable=True),
    Column("checkpoint_week", Date, nullable=True),
    Column("records_extracted", Integer, nullable=False, default=0),
    Column("records_deduplicated", Integer, nullable=False, default=0),
    Column("records_rejected", Integer, nullable=False, default=0),
    Column("records_loaded", Integer, nullable=False, default=0),
    Column("source_event_counts", _json_type(), nullable=False, default=dict),
    Column("office_counts", _json_type(), nullable=False, default=dict),
    Column("reconciliation", _json_type(), nullable=False, default=dict),
    Column(
        "supersedes_run_id",
        Uuid(as_uuid=True),
        ForeignKey("reporting.pipeline_runs.run_id"),
        nullable=True,
    ),
    Column("error_code", Text, nullable=True),
    Column("error_message", Text, nullable=True),
    Column("retry_count", Integer, nullable=False, default=0),
    Column("created_at", DateTime(timezone=True), nullable=False, default=_utcnow),
    CheckConstraint(
        "trigger_type in ('scheduled', 'manual', 'backfill', 'recompute')",
        name="ck_pipeline_runs_trigger_type",
    ),
    CheckConstraint(
        "status in ('queued', 'running', 'completed', 'completed_with_warnings', "
        "'failed', 'skipped_locked')",
        name="ck_pipeline_runs_status",
    ),
    CheckConstraint(
        "checkpoint_stage is null or checkpoint_stage in "
        "('extract', 'validate', 'transform', 'load', 'complete')",
        name="ck_pipeline_runs_checkpoint_stage",
    ),
)
Index(
    "ix_pipeline_runs_pipeline_started",
    pipeline_runs.c.pipeline_name,
    pipeline_runs.c.started_at.desc(),
)
Index(
    "ux_pipeline_runs_one_active",
    pipeline_runs.c.pipeline_name,
    unique=True,
    postgresql_where=text("status in ('queued', 'running')"),
    sqlite_where=text("status in ('queued', 'running')"),
)

pipeline_rejected_events = Table(
    "pipeline_rejected_events",
    reporting_metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column(
        "run_id",
        Uuid(as_uuid=True),
        ForeignKey("reporting.pipeline_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("event_id", Text, nullable=True),
    Column("event_type", Text, nullable=False),
    Column("reason", Text, nullable=False),
    Column("details", _json_type(), nullable=False, default=dict),
    Column("created_at", DateTime(timezone=True), nullable=False, default=_utcnow),
)
Index(
    "ix_rejected_events_run",
    pipeline_rejected_events.c.run_id,
)
Index(
    "ux_rejected_events_run_source_reason",
    pipeline_rejected_events.c.run_id,
    pipeline_rejected_events.c.event_id,
    pipeline_rejected_events.c.event_type,
    pipeline_rejected_events.c.reason,
    unique=True,
)

def ensure_reporting_schema(engine: Engine) -> None:
    """Idempotently make the reporting tables available to the pipeline.

    PostgreSQL deployments apply the authoritative migration in
    ``backrooms/services/reporting/migrations`` on API startup, which also adds
    RLS and revokes. This bootstrap keeps the CLI usable when the API has not
    started yet and mirrors the same table definitions for SQLite tests.
    """
    if engine.dialect.name == "sqlite":
        with engine.connect() as connection:
            try:
                connection.exec_driver_sql(
                    "ATTACH DATABASE ':memory:' AS reporting"
                )
                connection.commit()
            except Exception:  # noqa: BLE001 - already attached is fine
                pass
    else:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS reporting")
    reporting_metadata.create_all(engine)


__all__ = [
    "ensure_reporting_schema",
    "pipeline_rejected_events",
    "pipeline_runs",
    "reporting_metadata",
    "weekly_office_program_performance",
]
