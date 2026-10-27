"""Test bootstrap for the Nexova Inventory API suite.

The Inventory-API folder name contains a hyphen, so the service is a standalone
app root rather than an importable package. This conftest puts both the app root
and ``backrooms`` on ``sys.path`` and swaps the Supabase engine for an isolated
in-memory SQLite engine, so no test ever touches the remote database.

The shared ``client`` / ``auth_headers`` fixtures from ``backrooms/services/
conftest.py`` are reused to register and authenticate a TinyDB user.
"""

import os
import sys
from pathlib import Path

import pytest

INVENTORY_ROOT = Path(__file__).resolve().parent.parent
BACKROOMS_ROOT = INVENTORY_ROOT.parent.parent
REPO_ROOT = BACKROOMS_ROOT.parent
for candidate in (INVENTORY_ROOT, BACKROOMS_ROOT, REPO_ROOT):
	if str(candidate) not in sys.path:
		sys.path.insert(0, str(candidate))

# Must be set before importing the database module, which reads it at import time.
os.environ.setdefault("DATABASE_URL", "sqlite://")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

import database  # noqa: E402
import models  # noqa: E402,F401  (register tables)
import main as inventory_main  # noqa: E402
from models import Programme  # noqa: E402
from routers import inventory as inventory_routes  # noqa: E402
from services.telemetry import router as telemetry_routes  # noqa: E402
from data.pipelines.weekly_office_program_performance.schema import (  # noqa: E402
	reporting_metadata,
)


@pytest.fixture()
def clear_inventory_cache():
    """Drop module-level caches before each test."""
    inventory_routes._inventory_cache.clear()
    inventory_routes._telemetry_throttle.clear()
    telemetry_routes._report_cache.clear()
    telemetry_routes._default_period_cache.clear()


@pytest.fixture()
def sqlite_engine():
	"""A shared in-memory SQLite engine with FK enforcement enabled."""
	engine = create_engine(
		"sqlite://",
		connect_args={"check_same_thread": False},
		poolclass=StaticPool,
	)

	@event.listens_for(engine, "connect")
	def _configure_sqlite(dbapi_connection, _record):
		cursor = dbapi_connection.cursor()
		cursor.execute("PRAGMA foreign_keys=ON")
		cursor.execute("ATTACH DATABASE ':memory:' AS reporting")
		cursor.close()

	SQLModel.metadata.create_all(engine)
	reporting_metadata.create_all(engine)
	try:
		yield engine
	finally:
		engine.dispose()


@pytest.fixture()
def inventory_client(sqlite_engine, monkeypatch, clear_inventory_cache):
    """A TestClient for the Inventory app bound to the isolated SQLite engine."""
    monkeypatch.setattr(database, "engine", sqlite_engine)
    with TestClient(inventory_main.app) as client:
        yield client


@pytest.fixture()
def programme(sqlite_engine):
	"""Create an isolated programme row for inventory writes."""
	with Session(sqlite_engine) as session:
		record = Programme(slug="test-programme", name="Test Programme")
		session.add(record)
		session.commit()
		session.refresh(record)
		return record


@pytest.fixture()
def make_asset(inventory_client, auth_headers, programme):
	"""Create an asset through the API and return its response payload."""
	counter = {"n": 0}

	def _make(
		name="B2B sales certification kit",
		category="certification",
		office="Valencia",
		sku=None,
		programme_id=None,
		min_stock=10,
	):
		counter["n"] += 1
		response = inventory_client.post(
			"/inventory/products",
			headers=auth_headers,
			json={
				"name": name,
				"sku": sku or f"NXV-TST-{counter['n']:03d}",
				"category": category,
				"office": office,
				"programme_id": programme_id or programme.id,
				"min_stock": min_stock,
			},
		)
		assert response.status_code == 201, response.text
		return response.json()

	return _make
