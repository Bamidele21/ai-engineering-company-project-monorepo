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
for candidate in (INVENTORY_ROOT, BACKROOMS_ROOT):
	if str(candidate) not in sys.path:
		sys.path.insert(0, str(candidate))

# Must be set before importing the database module, which reads it at import time.
os.environ.setdefault("DATABASE_URL", "sqlite://")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import SQLModel, create_engine  # noqa: E402

import database  # noqa: E402
import models  # noqa: E402,F401  (register tables)
import main as inventory_main  # noqa: E402


@pytest.fixture()
def sqlite_engine():
	"""A shared in-memory SQLite engine with FK enforcement enabled."""
	engine = create_engine(
		"sqlite://",
		connect_args={"check_same_thread": False},
		poolclass=StaticPool,
	)

	@event.listens_for(engine, "connect")
	def _enable_foreign_keys(dbapi_connection, _record):
		cursor = dbapi_connection.cursor()
		cursor.execute("PRAGMA foreign_keys=ON")
		cursor.close()

	SQLModel.metadata.create_all(engine)
	try:
		yield engine
	finally:
		engine.dispose()


@pytest.fixture()
def inventory_client(sqlite_engine, monkeypatch):
	"""A TestClient for the Inventory app bound to the isolated SQLite engine."""
	monkeypatch.setattr(database, "engine", sqlite_engine)
	with TestClient(inventory_main.app) as client:
		yield client


@pytest.fixture()
def make_asset(inventory_client, auth_headers):
	"""Create an asset through the API and return its response payload."""
	counter = {"n": 0}

	def _make(name="Laptop 14\" Business", category="hardware", office="Valencia", sku=None):
		counter["n"] += 1
		response = inventory_client.post(
			"/inventory/products",
			headers=auth_headers,
			json={
				"name": name,
				"sku": sku or f"NXV-TST-{counter['n']:03d}",
				"category": category,
				"office": office,
			},
		)
		assert response.status_code == 201, response.text
		return response.json()

	return _make
