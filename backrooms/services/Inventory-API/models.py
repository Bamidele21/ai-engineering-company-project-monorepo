"""SQLModel ORM models for the Nexova inventory domain.

Nexova terminology (per milestone CONTEXT):

1. ``Asset``      -> README ``Product``. Never stores stock directly.
2. ``AssetEntry`` -> README ``InboundOrder`` (purchase or supplier delivery).
3. ``AssetExit``  -> README ``OutboundOrder`` (allocation or consumption).

There is deliberately no User model: ``user_uuid`` references TinyDB users, so no
user table is replicated in Supabase.
"""

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
	return datetime.now(timezone.utc)


class Programme(SQLModel, table=True):
	__tablename__ = "programmes"

	id: int | None = Field(default=None, primary_key=True)
	slug: str = Field(unique=True, index=True)
	name: str


class Asset(SQLModel, table=True):
	__tablename__ = "assets"

	id: int | None = Field(default=None, primary_key=True)
	name: str
	sku: str = Field(unique=True, index=True)
	category: str
	office: str
	programme_id: int | None = Field(
		default=None, foreign_key="programmes.id", index=True
	)
	min_stock: int = Field(default=10, ge=0)


class AssetEntry(SQLModel, table=True):
	__tablename__ = "asset_entries"

	id: int | None = Field(default=None, primary_key=True)
	asset_id: int = Field(foreign_key="assets.id", index=True)
	quantity: int
	supplier: str
	office: str
	unit_cost: float = Field(default=0.0, ge=0)
	currency: str = Field(default="EUR")
	created_at: datetime = Field(default_factory=_utcnow)
	user_uuid: str = Field(index=True)


class AssetExit(SQLModel, table=True):
	__tablename__ = "asset_exits"

	id: int | None = Field(default=None, primary_key=True)
	asset_id: int = Field(foreign_key="assets.id", index=True)
	quantity: int
	exit_type: str
	assigned_to: str | None = Field(default=None)
	office: str
	created_at: datetime = Field(default_factory=_utcnow)
	user_uuid: str = Field(index=True)
