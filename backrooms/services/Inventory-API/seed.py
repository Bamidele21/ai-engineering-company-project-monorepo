"""Seed the Supabase inventory tables with the Nexova telemetry dataset.

Run from this folder:

    uv run python seed.py

Idempotent: programmes are created when missing, and if the ``assets`` table
already contains rows the script exits without duplicating the order history.
"""

from sqlmodel import Session, select

import database
from database import init_inventory_schema
from models import Asset, AssetEntry, AssetExit, Programme


SEED_FALLBACK_USER_UUID = "00000000-0000-0000-0000-000000000000"

PROGRAMMES_SEED = [
	{"slug": "b2b-sales", "name": "B2B Sales Certification"},
	{"slug": "basic-leadership", "name": "Basic Leadership"},
	{"slug": "new-hire-onboarding", "name": "New Hire Onboarding"},
]

ASSETS_SEED = [
	{
		"name": "B2B sales certification kit",
		"sku": "NXV-CRT-001",
		"category": "certification",
		"office": "Valencia",
		"programme": "b2b-sales",
		"min_stock": 12,
	},
	{
		"name": "B2B sales workbook",
		"sku": "NXV-TRN-001",
		"category": "training_kit",
		"office": "Miami",
		"programme": "b2b-sales",
		"min_stock": 10,
	},
	{
		"name": "Leadership training workbook",
		"sku": "NXV-TRN-002",
		"category": "training_kit",
		"office": "Valencia",
		"programme": "basic-leadership",
		"min_stock": 10,
	},
	{
		"name": "Leadership certification",
		"sku": "NXV-CRT-002",
		"category": "certification",
		"office": "Miami",
		"programme": "basic-leadership",
		"min_stock": 8,
	},
	{
		"name": "Onboarding manual",
		"sku": "NXV-OFF-001",
		"category": "onboarding_equipment",
		"office": "Valencia",
		"programme": "new-hire-onboarding",
		"min_stock": 15,
	},
	{
		"name": "Temporary assignment laptop",
		"sku": "NXV-OFF-002",
		"category": "onboarding_equipment",
		"office": "Miami",
		"programme": "new-hire-onboarding",
		"min_stock": 5,
	},
]

# (sku, quantity, supplier, office, unit_cost, currency)
ENTRIES_SEED = [
	("NXV-CRT-001", 10, "PrintWorks Valencia S.L.", "Valencia", 12.5, "EUR"),
	("NXV-CRT-001", 5, "PrintWorks Valencia S.L.", "Valencia", 12.5, "EUR"),
	("NXV-TRN-001", 20, "Miami Print Co.", "Miami", 8.0, "USD"),
	("NXV-TRN-002", 15, "PrintWorks Valencia S.L.", "Valencia", 7.5, "EUR"),
	("NXV-OFF-001", 40, "Onboarding Supplies Valencia", "Valencia", 4.25, "EUR"),
	("NXV-OFF-002", 12, "Miami Device Partners", "Miami", 650.0, "USD"),
]

# (sku, quantity, exit_type, assigned_to, office)
EXITS_SEED = [
	("NXV-CRT-001", 3, "allocation", "Elena Vargas", "Valencia"),
	("NXV-TRN-002", 5, "allocation", "Elena Vargas", "Valencia"),
	("NXV-OFF-001", 12, "consumption", None, "Valencia"),
	("NXV-OFF-002", 2, "allocation", "Roberto Díaz", "Miami"),
]


def _seed_user_uuid() -> str:
	try:
		from services.Supply_directory_API.auth.services import get_user_by_id
		from services.Supply_directory_API.database import (
			get_db,
			get_users_table,
		)
	except Exception:
		return SEED_FALLBACK_USER_UUID

	with get_db() as db:
		for document in get_users_table(db).all():
			user = get_user_by_id(db, document.doc_id)
			if user is not None and user.uuid:
				return user.uuid
	return SEED_FALLBACK_USER_UUID


def _ensure_programmes(session: Session) -> dict[str, Programme]:
	programmes: dict[str, Programme] = {}
	for raw_programme in PROGRAMMES_SEED:
		programme = session.exec(
			select(Programme).where(Programme.slug == raw_programme["slug"])
		).first()
		if programme is None:
			programme = Programme(**raw_programme)
			session.add(programme)
		programmes[raw_programme["slug"]] = programme
	session.commit()
	for programme in programmes.values():
		session.refresh(programme)
	return programmes


def main() -> None:
	init_inventory_schema()
	user_uuid = _seed_user_uuid()

	with Session(database.engine) as session:
		programmes = _ensure_programmes(session)

		if session.exec(select(Asset)).first() is not None:
			print("Seed skipped. Inventory assets already present.")
			return

		assets_by_sku: dict[str, Asset] = {}
		for raw_asset in ASSETS_SEED:
			payload = dict(raw_asset)
			programme_slug = payload.pop("programme")
			asset = Asset(
				**payload,
				programme_id=programmes[programme_slug].id,
			)
			session.add(asset)
			assets_by_sku[asset.sku] = asset
		session.commit()
		for asset in assets_by_sku.values():
			session.refresh(asset)

		for sku, quantity, supplier, office, unit_cost, currency in ENTRIES_SEED:
			session.add(
				AssetEntry(
					asset_id=assets_by_sku[sku].id,
					quantity=quantity,
					supplier=supplier,
					office=office,
					unit_cost=unit_cost,
					currency=currency,
					user_uuid=user_uuid,
				)
			)

		for sku, quantity, exit_type, assigned_to, office in EXITS_SEED:
			session.add(
				AssetExit(
					asset_id=assets_by_sku[sku].id,
					quantity=quantity,
					exit_type=exit_type,
					assigned_to=assigned_to,
					office=office,
					user_uuid=user_uuid,
				)
			)
		session.commit()

	print(
		f"Seed completed. Programmes: {len(PROGRAMMES_SEED)}, "
		f"assets: {len(ASSETS_SEED)}, entries: {len(ENTRIES_SEED)}, "
		f"exits: {len(EXITS_SEED)}."
	)


if __name__ == "__main__":
	main()
