"""Test bootstrap for the async task queue suite.

Puts ``backrooms`` (and the repo root, so ``scripts.CSV_analyzer`` is
importable) on ``sys.path``, runs the Celery app in eager mode so no Redis
broker is required, and provides an isolated in-memory SQLite engine with an
attached ``task_queue`` database for the dead letter table. Mirrors the
job-runner suite pattern (``ATTACH DATABASE ':memory:' AS task_queue``).
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

from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from services.task_queue.celery_app import celery_app  # noqa: E402
from services.task_queue.storage import ensure_dead_letter_table  # noqa: E402


@pytest.fixture(autouse=True)
def eager_celery():
    """Execute tasks inline so no Redis broker is required for the tests."""
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False
    celery_app.conf.task_eager_propagates = False


@pytest.fixture()
def engine():
    """A shared in-memory SQLite engine with the task_queue schema attached."""
    sqlite_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(sqlite_engine, "connect")
    def _configure_sqlite(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("ATTACH DATABASE ':memory:' AS task_queue")
        cursor.close()

    ensure_dead_letter_table(sqlite_engine)
    try:
        yield sqlite_engine
    finally:
        sqlite_engine.dispose()
