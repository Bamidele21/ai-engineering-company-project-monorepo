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


def init_inventory_schema() -> None:
	"""Create the inventory tables on startup from the registered ORM models."""
	import models  # noqa: F401  (import registers tables on SQLModel.metadata)

	SQLModel.metadata.create_all(engine)
