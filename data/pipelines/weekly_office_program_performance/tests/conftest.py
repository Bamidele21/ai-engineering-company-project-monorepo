"""SQLite fixtures for flow-level pipeline tests.

Creates the three ``public`` source tables plus the attached ``reporting``
schema so the main flow, subflows, and monitoring can run without a database
server. The engine is monkeypatched into ``db.get_engine`` by the
``pipeline_engine`` fixture.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from data.pipelines.weekly_office_program_performance import db  # noqa: E402
from data.pipelines.weekly_office_program_performance.schema import (  # noqa: E402
    ensure_reporting_schema,
)

from .helpers import public_metadata  # noqa: E402


@pytest.fixture()
def sqlite_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("ATTACH DATABASE ':memory:' AS reporting")
        cursor.close()

    public_metadata.create_all(engine)
    ensure_reporting_schema(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def pipeline_engine(sqlite_engine, monkeypatch):
    monkeypatch.setattr(db, "get_engine", lambda: sqlite_engine)
    monkeypatch.setattr(db, "dispose_engine", lambda: None)
    yield sqlite_engine


@pytest.fixture()
def snapshot_dir(tmp_path, monkeypatch):
    from data.pipelines.weekly_office_program_performance import config

    monkeypatch.setattr(config, "snapshot_directory", lambda: tmp_path)
    return tmp_path
