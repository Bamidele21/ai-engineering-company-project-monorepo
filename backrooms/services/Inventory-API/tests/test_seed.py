"""Tests for the Nexova inventory seed script."""

from sqlmodel import Session, select

import database
import seed
from models import Asset, AssetEntry, AssetExit


def _counts(engine):
	with Session(engine) as session:
		return (
			len(session.exec(select(Asset)).all()),
			len(session.exec(select(AssetEntry)).all()),
			len(session.exec(select(AssetExit)).all()),
		)


def _net_stock(session, asset_id):
	inbound = sum(
		entry.quantity
		for entry in session.exec(
			select(AssetEntry).where(AssetEntry.asset_id == asset_id)
		).all()
	)
	outbound = sum(
		exit_record.quantity
		for exit_record in session.exec(
			select(AssetExit).where(AssetExit.asset_id == asset_id)
		).all()
	)
	return inbound - outbound


def test_seed_creates_records_with_expected_net_stock(sqlite_engine, monkeypatch, db):
	monkeypatch.setattr(database, "engine", sqlite_engine)
	seed.main()

	with Session(sqlite_engine) as session:
		assets = {asset.sku: asset for asset in session.exec(select(Asset)).all()}
		assert len(assets) == len(seed.ASSETS_SEED)
		assert len(session.exec(select(AssetEntry)).all()) == len(seed.ENTRIES_SEED)
		assert len(session.exec(select(AssetExit)).all()) == len(seed.EXITS_SEED)

		# net = entries - exits, matching the telemetry seed quantities.
		assert _net_stock(session, assets["NXV-CRT-001"].id) == 15 - 3
		assert _net_stock(session, assets["NXV-TRN-002"].id) == 15 - 5
		assert _net_stock(session, assets["NXV-OFF-001"].id) == 40 - 12
		assert _net_stock(session, assets["NXV-OFF-002"].id) == 12 - 2
		assert _net_stock(session, assets["NXV-TRN-001"].id) == 20
		assert _net_stock(session, assets["NXV-CRT-002"].id) == 0


def test_seed_is_idempotent(sqlite_engine, monkeypatch, db):
	monkeypatch.setattr(database, "engine", sqlite_engine)
	seed.main()
	first = _counts(sqlite_engine)

	seed.main()
	second = _counts(sqlite_engine)

	assert first == second


def test_seed_skips_when_assets_already_exist(sqlite_engine, monkeypatch, db):
	monkeypatch.setattr(database, "engine", sqlite_engine)
	with Session(sqlite_engine) as session:
		session.add(
			Asset(
				name="Manual asset",
				sku="NXV-MAN-001",
				category="onboarding_equipment",
				office="Miami",
			)
		)
		session.commit()

	seed.main()

	with Session(sqlite_engine) as session:
		assets = session.exec(select(Asset)).all()
		assert [asset.sku for asset in assets] == ["NXV-MAN-001"]
