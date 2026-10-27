"""Read-only extraction of telemetry rows and the office/programme scaffold."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from data.process.weekly_performance.constants import (
    ALLOWED_EVENT_TYPES,
    INVENTORY_SERVICE,
    week_bounds,
)
from data.process.weekly_performance.normalize import raw_source_counts

_EVENT_TYPES_SQL = ", ".join(f"'{event}'" for event in sorted(ALLOWED_EVENT_TYPES))


@dataclass
class ExtractResult:
    week_start: date
    window_start: datetime
    window_end: datetime
    raw_rows: list[dict[str, Any]]
    dimension_pairs: list[tuple[str, str]]
    known_programmes: list[str]
    source_event_counts: dict[str, int]
    office_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_start": self.week_start.isoformat(),
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "raw_rows": [
                {
                    **row,
                    "timestamp": row["timestamp"].isoformat()
                    if isinstance(row["timestamp"], datetime)
                    else str(row["timestamp"]),
                }
                for row in self.raw_rows
            ],
            "dimension_pairs": [list(pair) for pair in self.dimension_pairs],
            "known_programmes": list(self.known_programmes),
            "source_event_counts": dict(self.source_event_counts),
            "office_counts": dict(self.office_counts),
        }


def _coerce_tags(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {}
        except ValueError:
            return {}
    return {}


def extract_week(engine: Engine, week_start: date) -> ExtractResult:
    """Read the four allowlisted event types for one UTC week, read-only."""
    window_start, window_end = week_bounds(week_start)
    rows_sql = text(
        f"""
        SELECT
            CAST(id AS TEXT) AS id,
            timestamp,
            service,
            event_type,
            tags
        FROM public.telemetry_events
        WHERE service = :service
          AND event_type IN ({_EVENT_TYPES_SQL})
          AND timestamp >= :window_start
          AND timestamp < :window_end
        ORDER BY timestamp ASC, CAST(id AS TEXT) ASC
        """
    )
    with engine.connect() as connection:
        raw = connection.execute(
            rows_sql,
            {
                "service": INVENTORY_SERVICE,
                "window_start": window_start,
                "window_end": window_end,
            },
        ).mappings().all()

    raw_rows = [
        {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "service": row["service"],
            "event_type": row["event_type"],
            "tags": _coerce_tags(row["tags"]),
        }
        for row in raw
    ]

    dimension_sql = text(
        """
        SELECT
            lower(trim(a.office)) AS office,
            trim(p.slug) AS programme_id
        FROM public.assets AS a
        JOIN public.programmes AS p ON p.id = a.programme_id
        WHERE a.office IS NOT NULL AND p.slug IS NOT NULL
        GROUP BY 1, 2
        """
    )
    known_sql = text(
        """
        SELECT trim(slug) AS slug
        FROM public.programmes
        WHERE slug IS NOT NULL AND trim(slug) <> ''
        """
    )
    with engine.connect() as connection:
        dimension_rows = connection.execute(dimension_sql).mappings().all()
        known_rows = connection.execute(known_sql).mappings().all()

    dimension_pairs = sorted(
        {
            (str(row["office"]).strip().lower(), str(row["programme_id"]).strip())
            for row in dimension_rows
            if row["office"] and row["programme_id"]
        }
    )
    known_programmes = sorted(
        {str(row["slug"]).strip() for row in known_rows if row["slug"]}
    )
    source_event_counts, office_counts = raw_source_counts(raw_rows)
    return ExtractResult(
        week_start=week_start,
        window_start=window_start,
        window_end=window_end,
        raw_rows=raw_rows,
        dimension_pairs=dimension_pairs,
        known_programmes=known_programmes,
        source_event_counts=source_event_counts,
        office_counts=office_counts,
    )
