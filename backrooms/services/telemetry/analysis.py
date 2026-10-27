"""Pandas analysis pipeline for the Nexova technical telemetry report.

Each metric follows the same order: load only the relevant rows in SQL, refine
and type-convert in Pandas, group/aggregate, then return JSON-safe records.
Functions are side-effect free and share no mutable calculation state.
"""

import json
from datetime import datetime
from typing import Any, Iterable

import pandas as pd
from sqlalchemy.engine import Engine
from sqlalchemy.sql import select

from .catalog import EVENT_SPECS
from .storage import telemetry_events_table

CATALOGUE_EVENT_TYPES = tuple(EVENT_SPECS)
ERROR_LEVEL = "error"
PAGE_VIEW_EVENT = "page_view"


def _read_frame(
	engine: Engine,
	columns: Iterable[Any],
	event_types: Iterable[str],
	start_date: datetime,
	end_date: datetime,
) -> pd.DataFrame:
	"""Load only the events and columns a metric needs, filtered in SQL."""
	query = select(*columns).where(
		telemetry_events_table.c.timestamp >= start_date,
		telemetry_events_table.c.timestamp < end_date,
		telemetry_events_table.c.event_type.in_(tuple(event_types)),
	)
	with engine.connect() as connection:
		return pd.read_sql(query, connection)


def _with_utc_day(frame: pd.DataFrame) -> pd.DataFrame:
	"""Convert stored timestamps and derive the UTC grouping day."""
	frame = frame.copy()
	frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
	frame["date"] = frame["timestamp"].dt.strftime("%Y-%m-%d")
	return frame


def _normalise_tags(values: pd.Series) -> pd.DataFrame:
	"""Turn a JSON/JSONB tags column into flat columns for Pandas."""

	def _as_mapping(value: Any) -> dict[str, Any]:
		if isinstance(value, str):
			try:
				decoded = json.loads(value)
			except json.JSONDecodeError:
				return {}
			return decoded if isinstance(decoded, dict) else {}
		return value if isinstance(value, dict) else {}

	return pd.json_normalize(values.map(_as_mapping))


def events_per_day(
	engine: Engine,
	start_date: datetime,
	end_date: datetime,
) -> list[dict[str, Any]]:
	"""Count captured catalogue events by UTC day and event type."""
	frame = _read_frame(
		engine,
		(telemetry_events_table.c.timestamp, telemetry_events_table.c.event_type),
		CATALOGUE_EVENT_TYPES,
		start_date,
		end_date,
	)
	if frame.empty:
		return []

	frame = _with_utc_day(frame)
	grouped = (
		frame.groupby(["date", "event_type"])
		.size()
		.reset_index(name="count")
		.sort_values(["date", "event_type"])
	)
	return grouped.to_dict(orient="records")


def error_rate_by_type(
	engine: Engine,
	start_date: datetime,
	end_date: datetime,
) -> list[dict[str, Any]]:
	"""Report error-level events as a share of each UTC day's captured activity.

	The denominator is the whole declared captured-event population for that
	day, loaded in the same SQL query as the numerator. `level` is the stored
	severity classification, so warn-level business rejections are not counted
	as errors here.
	"""
	frame = _read_frame(
		engine,
		(
			telemetry_events_table.c.timestamp,
			telemetry_events_table.c.event_type,
			telemetry_events_table.c.level,
		),
		CATALOGUE_EVENT_TYPES,
		start_date,
		end_date,
	)
	if frame.empty:
		return []

	frame = _with_utc_day(frame)
	totals = (
		frame.groupby(["date", "event_type"])
		.size()
		.reset_index(name="total_count")
	)
	errors = (
		frame[frame["level"].eq(ERROR_LEVEL)]
		.groupby(["date", "event_type"])
		.size()
		.reset_index(name="error_count")
	)
	daily_totals = frame.groupby("date").size().reset_index(name="daily_total")

	grouped = (
		totals.merge(errors, on=["date", "event_type"], how="left")
		.merge(daily_totals, on="date", how="left")
		.sort_values(["date", "event_type"])
	)
	grouped["error_count"] = grouped["error_count"].fillna(0).astype(int)
	grouped["daily_total"] = grouped["daily_total"].astype(int)
	grouped["error_rate"] = (
		grouped["error_count"] / grouped["daily_total"]
	).fillna(0.0)
	return grouped.to_dict(orient="records")


def page_load_latency_by_day(
	engine: Engine,
	start_date: datetime,
	end_date: datetime,
) -> list[dict[str, Any]]:
	"""Average observed document-load duration by UTC day and route."""
	frame = _read_frame(
		engine,
		(telemetry_events_table.c.timestamp, telemetry_events_table.c.tags),
		(PAGE_VIEW_EVENT,),
		start_date,
		end_date,
	)
	if frame.empty:
		return []

	with_day = _with_utc_day(frame.drop(columns=["tags"]))
	tags = _normalise_tags(frame["tags"])
	frame = pd.concat(
		[with_day.reset_index(drop=True), tags.reset_index(drop=True)],
		axis=1,
	)

	if "page_path" not in frame.columns or "load_duration_ms" not in frame.columns:
		return []

	frame["page_path"] = frame["page_path"].astype("string")
	frame["load_duration_ms"] = pd.to_numeric(
		frame["load_duration_ms"], errors="coerce"
	)
	frame = frame.dropna(subset=["page_path", "load_duration_ms"])
	frame = frame[frame["page_path"].str.len().gt(0)]
	frame = frame[frame["load_duration_ms"].ge(0)]
	if frame.empty:
		return []

	grouped = (
		frame.groupby(["date", "page_path"])
		.agg(
			average_load_duration_ms=("load_duration_ms", "mean"),
			sample_count=("load_duration_ms", "size"),
		)
		.reset_index()
		.sort_values(["date", "page_path"])
	)
	grouped["average_load_duration_ms"] = grouped[
		"average_load_duration_ms"
	].round(2)
	return grouped.to_dict(orient="records")
