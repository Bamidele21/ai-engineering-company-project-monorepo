"""Dual-database wiring for the Nexova Inventory API.

Two databases run side by side in this service:

1. TinyDB (existing) — users and authentication. The Inventory API reuses the
   ``get_current_user`` dependency from ``services.Supply_directory_API`` so the
   authenticated manager's UUID travels with every order.
2. Supabase PostgreSQL (new) — assets and their entry/exit order history, via a
   per-request SQLModel ``Session``.

The folder name ``Inventory-API`` contains a hyphen, so this service is executed
as a standalone app root rather than an importable package. Internal modules are
imported by their bare names (``models``, ``routers.inventory``).
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

# ``backrooms`` is the directory that makes ``services.Supply_directory_API.*``
# importable, which is how the TinyDB auth layer is reused.
SERVICES_ROOT = Path(__file__).resolve().parent.parent
BACKROOMS_ROOT = SERVICES_ROOT.parent
for candidate in (SERVICES_ROOT, BACKROOMS_ROOT):
	if str(candidate) not in sys.path:
		sys.path.insert(0, str(candidate))

load_dotenv(Path(__file__).resolve().parent / ".env")

# CONTEXT-required name is DATABASE_URL; SUPABASE_URL is accepted as a fallback
# for the connecting string already present in local development.
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_URL")
if not DATABASE_URL:
	raise RuntimeError(
		"DATABASE_URL must be configured (Supabase transaction pooler URI)."
	)

# SQLAlchemy 2.1 resolves a bare ``postgresql://`` URL to the psycopg (v3)
# driver, but this project ships psycopg2-binary. Pin the driver explicitly so
# the Supabase URI can be pasted verbatim from the dashboard.
if DATABASE_URL.startswith("postgresql://"):
	DATABASE_URL = DATABASE_URL.replace(
		"postgresql://", "postgresql+psycopg2://", 1
	)
elif DATABASE_URL.startswith("postgres://"):
	DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def get_sql_session():
	"""Yield a SQLModel session per request. No global session is shared."""
	with Session(engine) as session:
		yield session


DEFAULT_PROGRAMMES = (
	("b2b-sales", "B2B Sales Certification"),
	("basic-leadership", "Basic Leadership"),
	("new-hire-onboarding", "New Hire Onboarding"),
)

PROGRAMME_BY_CATEGORY = {
	"onboarding_equipment": "new-hire-onboarding",
	"training_kit": "basic-leadership",
	"certification": "b2b-sales",
}


def _columns(connection, table_name: str) -> set[str]:
	inspector = inspect(connection)
	return {column["name"] for column in inspector.get_columns(table_name)}


def _ensure_default_programmes(connection) -> None:
	for slug, name in DEFAULT_PROGRAMMES:
		exists = connection.execute(
			text("SELECT id FROM programmes WHERE slug = :slug"), {"slug": slug}
		).first()
		if exists is None:
			connection.execute(
				text("INSERT INTO programmes (slug, name) VALUES (:slug, :name)"),
				{"slug": slug, "name": name},
			)


def upgrade_inventory_schema(target_engine) -> None:
	"""Bring a pre-telemetry inventory schema up to the Sprint 1 contract.

	``SQLModel.metadata.create_all`` creates missing tables but never alters
	existing columns, so the legacy Supabase tables need explicit, idempotent
	upgrades. Production should replace this bootstrap with Alembic.
	"""
	import models  # noqa: F401  (register tables on SQLModel.metadata)

	SQLModel.metadata.create_all(target_engine)

	with target_engine.begin() as connection:
		asset_columns = _columns(connection, "assets")
		entry_columns = _columns(connection, "asset_entries")
		legacy_programme_link = "programme_id" not in asset_columns
		legacy_currency = "currency" not in entry_columns

		if "min_stock" not in asset_columns:
			connection.execute(
				text(
					"ALTER TABLE assets ADD COLUMN min_stock INTEGER NOT NULL DEFAULT 10"
				)
			)
		if legacy_programme_link:
			connection.execute(
				text(
					"ALTER TABLE assets ADD COLUMN programme_id INTEGER "
					"REFERENCES programmes(id)"
				)
			)
		if "unit_cost" not in entry_columns:
			connection.execute(
				text(
					"ALTER TABLE asset_entries ADD COLUMN unit_cost FLOAT "
					"NOT NULL DEFAULT 0"
				)
			)
		if "currency" not in entry_columns:
			connection.execute(
				text(
					"ALTER TABLE asset_entries ADD COLUMN currency VARCHAR(3) "
					"NOT NULL DEFAULT 'EUR'"
				)
			)

		connection.execute(
			text(
				"UPDATE assets SET category = 'onboarding_equipment' "
				"WHERE category IN ('hardware', 'peripherals', 'office_supplies')"
			)
		)
		connection.execute(
			text(
				"UPDATE assets SET category = 'training_kit' "
				"WHERE category = 'training_materials'"
			)
		)
		connection.execute(
			text("UPDATE assets SET min_stock = 10 WHERE min_stock IS NULL")
		)

		if legacy_programme_link:
			_ensure_default_programmes(connection)
			for category, slug in PROGRAMME_BY_CATEGORY.items():
				connection.execute(
					text(
						"UPDATE assets SET programme_id = "
						"(SELECT id FROM programmes WHERE slug = :slug) "
						"WHERE programme_id IS NULL AND category = :category"
					),
					{"slug": slug, "category": category},
				)
			connection.execute(
				text(
					"UPDATE assets SET programme_id = "
					"(SELECT id FROM programmes WHERE slug = 'new-hire-onboarding') "
					"WHERE programme_id IS NULL"
				)
			)

		currency_filter = "" if legacy_currency else "WHERE currency IS NULL OR currency = ''"
		connection.execute(
			text(
				"UPDATE asset_entries SET currency = CASE "
				"WHEN lower(office) = 'miami' THEN 'USD' ELSE 'EUR' END "
				f"{currency_filter}"
			)
		)


def init_inventory_schema() -> None:
	"""Create or upgrade the inventory schema on startup."""
	upgrade_inventory_schema(engine)
