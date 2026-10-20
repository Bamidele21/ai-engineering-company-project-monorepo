"""Seed the Supabase inventory tables with the Nexova milestone dataset.

Run from this folder:

    uv run python seed.py

Idempotent: if the ``assets`` table already contains rows the script exits
without writing, so re-running never duplicates the seed.
"""

from sqlmodel import Session, select

import database
from database import init_inventory_schema
from models import Asset, AssetEntry, AssetExit


# Order authors reference TinyDB users. If no TinyDB user can be resolved (for
# example a fresh environment), this documented placeholder is used instead.
SEED_FALLBACK_USER_UUID = "00000000-0000-0000-0000-000000000000"

ASSETS_SEED = [
	{"name": 'Laptop 14" Business', "sku": "NXV-IT-001", "category": "hardware", "office": "Valencia"},
	{"name": 'Laptop 14" Business', "sku": "NXV-IT-002", "category": "hardware", "office": "Miami"},
	{"name": "Ergonomic mouse", "sku": "NXV-PER-001", "category": "peripherals", "office": "Valencia"},
	{"name": "USB-C Hub", "sku": "NXV-PER-002", "category": "peripherals", "office": "Miami"},
	{"name": "A4 paper ream", "sku": "NXV-OFF-001", "category": "office_supplies", "office": "Valencia"},
	{"name": "Leadership training workbook", "sku": "NXV-TRN-001", "category": "training_materials", "office": "Valencia"},
]

# (sku, quantity, supplier, office)
ENTRIES_SEED = [
	("NXV-IT-001", 10, "TechDistrib Valencia S.L.", "Valencia"),
	("NXV-IT-001", 5, "TechDistrib Valencia S.L.", "Valencia"),
	("NXV-PER-001", 20, "TechDistrib Valencia S.L.", "Valencia"),
	("NXV-PER-002", 15, "Office Depot Miami", "Miami"),
	("NXV-OFF-001", 50, "Office Depot Valencia", "Valencia"),
]

# (sku, quantity, exit_type, assigned_to, office)
EXITS_SEED = [
	("NXV-IT-001", 3, "allocation", "Javier Almeida", "Valencia"),
	("NXV-PER-001", 5, "allocation", "Elena Vargas", "Valencia"),
	("NXV-OFF-001", 12, "consumption", None, "Valencia"),
]


def _seed_user_uuid() -> str:
	"""Return a TinyDB user UUID, backfilling legacy users on the way."""
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


def main() -> None:
	init_inventory_schema()
	user_uuid = _seed_user_uuid()

	with Session(database.engine) as session:
		if session.exec(select(Asset)).first() is not None:
			print("Seed skipped. Inventory assets already present.")
			return

		assets_by_sku: dict[str, Asset] = {}
		for raw_asset in ASSETS_SEED:
			asset = Asset(**raw_asset)
			session.add(asset)
			assets_by_sku[asset.sku] = asset
		session.commit()
		for asset in assets_by_sku.values():
			session.refresh(asset)

		for sku, quantity, supplier, office in ENTRIES_SEED:
			session.add(
				AssetEntry(
					asset_id=assets_by_sku[sku].id,
					quantity=quantity,
					supplier=supplier,
					office=office,
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
		f"Seed completed. Assets: {len(ASSETS_SEED)}, "
		f"entries: {len(ENTRIES_SEED)}, exits: {len(EXITS_SEED)}."
	)


if __name__ == "__main__":
	main()
