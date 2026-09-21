from pathlib import Path

from tinydb import TinyDB


SUPPLIERS_TABLE = "suppliers"
USERS_TABLE = "users"
PROFILES_TABLE = "profiles"
PASSWORD_RESETS_TABLE = "password_resets"
DB_PATH = Path(__file__).resolve().parent / "suppliers_db.json"
PASSWORD_RESETS_DB_PATH = Path(__file__).resolve().parent / "password_resets_db.json"


def get_db() -> TinyDB:
	return TinyDB(DB_PATH)


def get_password_resets_db() -> TinyDB:
	return TinyDB(PASSWORD_RESETS_DB_PATH)


def get_password_resets_table(db: TinyDB):
	return db.table(PASSWORD_RESETS_TABLE)


def get_suppliers_table(db: TinyDB):
	return db.table(SUPPLIERS_TABLE)


def get_users_table(db: TinyDB):
	return db.table(USERS_TABLE)


def get_profiles_table(db: TinyDB):
	return db.table(PROFILES_TABLE)
