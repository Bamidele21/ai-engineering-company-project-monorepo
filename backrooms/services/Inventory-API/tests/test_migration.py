"""Legacy-schema upgrade tests for the Sprint 1 inventory contract."""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, select

import database
from models import Asset, AssetEntry, Programme


LEGACY_ASSETS = """
CREATE TABLE assets (
    id INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL,
    sku VARCHAR NOT NULL UNIQUE,
    category VARCHAR NOT NULL,
    office VARCHAR NOT NULL
)
"""

LEGACY_ENTRIES = """
CREATE TABLE asset_entries (
    id INTEGER PRIMARY KEY,
    asset_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    supplier VARCHAR NOT NULL,
    office VARCHAR NOT NULL,
    created_at DATETIME,
    user_uuid VARCHAR NOT NULL
)
"""

LEGACY_EXITS = """
CREATE TABLE asset_exits (
    id INTEGER PRIMARY KEY,
    asset_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    exit_type VARCHAR NOT NULL,
    assigned_to VARCHAR,
    office VARCHAR NOT NULL,
    created_at DATETIME,
    user_uuid VARCHAR NOT NULL
)
"""


def _legacy_engine():
	return create_engine(
		"sqlite://",
		connect_args={"check_same_thread": False},
		poolclass=StaticPool,
	)


def _prepare_legacy(engine):
	with engine.begin() as connection:
		connection.execute(text(LEGACY_ASSETS))
		connection.execute(text(LEGACY_ENTRIES))
		connection.execute(text(LEGACY_EXITS))
		connection.execute(
			text(
				"INSERT INTO assets (id, name, sku, category, office) VALUES "
				"(1, 'Laptop', 'NXV-IT-001', 'hardware', 'Valencia'), "
				"(2, 'Leadership workbook', 'NXV-TRN-001', "
				"'training_materials', 'Miami')"
			)
		)
		connection.execute(
			text(
				"INSERT INTO asset_entries "
				"(id, asset_id, quantity, supplier, office, user_uuid) VALUES "
				"(1, 1, 10, 'TechDistrib', 'Valencia', 'uuid-1'), "
				"(2, 2, 5, 'Miami Print', 'Miami', 'uuid-1')"
			)
		)


def test_legacy_schema_is_upgraded_and_backfilled():
	engine = _legacy_engine()
	_prepare_legacy(engine)

	database.upgrade_inventory_schema(engine)

	inspector = inspect(engine)
	assert "programme_id" in {column["name"] for column in inspector.get_columns("assets")}
	assert "min_stock" in {column["name"] for column in inspector.get_columns("assets")}
	assert "unit_cost" in {
		column["name"] for column in inspector.get_columns("asset_entries")
	}
	assert "currency" in {
		column["name"] for column in inspector.get_columns("asset_entries")
	}

	with Session(engine) as session:
		assets = {asset.id: asset for asset in session.exec(select(Asset)).all()}
		programmes = {
			programme.slug: programme for programme in session.exec(select(Programme)).all()
		}
		entries = {entry.id: entry for entry in session.exec(select(AssetEntry)).all()}

		assert assets[1].category == "onboarding_equipment"
		assert assets[1].min_stock == 10
		assert assets[1].programme_id == programmes["new-hire-onboarding"].id
		assert assets[2].category == "training_kit"
		assert assets[2].programme_id == programmes["basic-leadership"].id
		assert entries[1].currency == "EUR"
		assert entries[2].currency == "USD"
		assert entries[1].unit_cost == 0


def test_upgrade_is_idempotent():
	engine = _legacy_engine()
	_prepare_legacy(engine)

	database.upgrade_inventory_schema(engine)
	with Session(engine) as session:
		first_programmes = len(session.exec(select(Programme)).all())
		first_assets = [
			(asset.id, asset.category, asset.programme_id, asset.min_stock)
			for asset in session.exec(select(Asset).order_by(Asset.id)).all()
		]

	database.upgrade_inventory_schema(engine)

	with Session(engine) as session:
		assert len(session.exec(select(Programme)).all()) == first_programmes
		second_assets = [
			(asset.id, asset.category, asset.programme_id, asset.min_stock)
			for asset in session.exec(select(Asset).order_by(Asset.id)).all()
		]
		assert second_assets == first_assets
