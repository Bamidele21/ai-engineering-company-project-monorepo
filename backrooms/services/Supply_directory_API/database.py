from pathlib import Path

from tinydb import TinyDB


SUPPLIERS_TABLE = "suppliers"
USERS_TABLE = "users"
PROFILES_TABLE = "profiles"
DB_PATH = Path(__file__).resolve().parent / "suppliers_db.json"


def get_db() -> TinyDB:
	return TinyDB(DB_PATH)


def get_suppliers_table(db: TinyDB):
	return db.table(SUPPLIERS_TABLE)


def get_users_table(db: TinyDB):
	return db.table(USERS_TABLE)


def get_profiles_table(db: TinyDB):
	return db.table(PROFILES_TABLE)
