"""Idempotent reporting-schema initialization."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine import Engine

from data.pipelines.weekly_office_program_performance.schema import (
    ensure_reporting_schema,
    reporting_metadata,
)

MIGRATION_PATH = Path(__file__).resolve().parent / "migrations" / "001_reporting_schema.sql"


def init_reporting_schema(engine: Engine) -> None:
    """Create the reporting schema/tables; safe to call on every startup."""
    if engine.dialect.name == "postgresql":
        sql = MIGRATION_PATH.read_text(encoding="utf-8")
        with engine.begin() as connection:
            connection.exec_driver_sql(sql)
        return
    ensure_reporting_schema(engine)


__all__ = ["MIGRATION_PATH", "init_reporting_schema", "reporting_metadata"]
