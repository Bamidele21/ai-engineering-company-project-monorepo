"""Test bootstrap for the job-runner suite.

Puts ``backrooms`` (and the repo root) on ``sys.path`` and provides an
isolated in-memory SQLite engine with an attached ``reporting`` database, so
no test ever touches the remote database. Mirrors the pipeline SQLite test
pattern (``ATTACH DATABASE ':memory:' AS reporting``).
"""

import os
import sys
from pathlib import Path

import pytest

TESTS_ROOT = Path(__file__).resolve().parent
BACKROOMS_ROOT = TESTS_ROOT.parents[2]
REPO_ROOT = BACKROOMS_ROOT.parent
for candidate in (REPO_ROOT, BACKROOMS_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

os.environ.setdefault("DATABASE_URL", "sqlite://")

from sqlalchemy import event  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

from services.job_runner.storage import ensure_job_runs_table  # noqa: E402
from services.telemetry.storage import telemetry_metadata  # noqa: E402


@pytest.fixture()
def engine():
    """A shared in-memory SQLite engine with the reporting schema attached."""
    sqlite_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(sqlite_engine, "connect")
    def _configure_sqlite(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("ATTACH DATABASE ':memory:' AS reporting")
        cursor.close()

    ensure_job_runs_table(sqlite_engine)
    telemetry_metadata.create_all(sqlite_engine)
    try:
        yield sqlite_engine
    finally:
        sqlite_engine.dispose()
