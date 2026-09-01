from pathlib import Path

from tinydb import TinyDB


SUPPLIERS_TABLE = "suppliers"
DB_PATH = Path(__file__).resolve().parent / "suppliers_db.json"


def get_db() -> TinyDB:
	return TinyDB(DB_PATH)


def get_suppliers_table(db: TinyDB):
	return db.table(SUPPLIERS_TABLE)
