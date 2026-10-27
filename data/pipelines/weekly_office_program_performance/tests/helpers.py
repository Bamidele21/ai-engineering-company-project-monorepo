"""Shared table definitions and insert helpers for the SQLite flow tests."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import (  # noqa: E402
    JSON,
    Column,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    Table,
    Text,
    Uuid,
)

public_metadata = MetaData()

telemetry_events_table = Table(
    "telemetry_events",
    public_metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("timestamp", DateTime(timezone=True), nullable=False),
    Column("service", Text, nullable=False),
    Column("event_type", Text, nullable=False),
    Column("level", Text, nullable=False, default="info"),
    Column("value", Numeric, nullable=True),
    Column("message", Text, nullable=True),
    Column("tags", JSON, nullable=False, default=dict),
)

programmes_table = Table(
    "programmes",
    public_metadata,
    Column("id", Integer, primary_key=True),
    Column("slug", Text, nullable=False),
    Column("name", Text, nullable=False),
)

assets_table = Table(
    "assets",
    public_metadata,
    Column("id", Integer, primary_key=True),
    Column("office", Text, nullable=False),
    Column("programme_id", Integer, nullable=True),
)


def seed_dimensions(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            programmes_table.insert().values(
                [
                    {"id": 1, "slug": "b2b-sales", "name": "B2B Sales"},
                    {"id": 2, "slug": "basic-leadership", "name": "Basic Leadership"},
                ]
            )
        )
        connection.execute(
            assets_table.insert().values(
                [
                    {"id": 1, "office": "Valencia", "programme_id": 1},
                    {"id": 2, "office": "Miami", "programme_id": 1},
                    {"id": 3, "office": "Valencia", "programme_id": 2},
                ]
            )
        )


def insert_event(
    engine,
    event_type: str,
    *,
    event_id: str,
    office: str = "valencia",
    programme: str = "b2b-sales",
    quantity: int = 1,
    unit_cost=None,
    currency: str | None = None,
    timestamp=None,
    order_id: str | None = None,
) -> None:
    tags = {
        "office": office,
        "programme_id": programme,
        "quantity": quantity,
        "currency": currency or ("EUR" if office == "valencia" else "USD"),
        "product_id": 1,
        "product_category": "certification",
        "_meta": {"eventId": event_id, "schemaVersion": "1.0"},
    }
    if unit_cost is not None:
        tags["unit_cost"] = unit_cost
    if order_id is not None:
        tags["order_id"] = order_id
    with engine.begin() as connection:
        connection.execute(
            telemetry_events_table.insert().values(
                id=uuid4(),
                timestamp=timestamp
                or datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc),
                service="inventory-api",
                event_type=event_type,
                level="info",
                tags=tags,
            )
        )
