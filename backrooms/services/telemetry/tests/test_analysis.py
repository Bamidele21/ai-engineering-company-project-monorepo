"""Happy, edge, and failure coverage for the telemetry analysis pipeline."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session

import services.telemetry.analysis as analysis
from services.telemetry.storage import (
	telemetry_events_table,
	telemetry_metadata,
)

UTC = timezone.utc


@pytest.fixture()
def engine():
	engine = create_engine(
		"sqlite://",
		connect_args={"check_same_thread": False},
		poolclass=StaticPool,
	)
	telemetry_metadata.create_all(engine)
	try:
		yield engine
	finally:
		engine.dispose()


def _row(
	event_type: str,
	timestamp: datetime,
	level: str = "info",
	tags: dict | None = None,
	value: float | None = None,
) -> dict:
	return {
		"id": uuid4(),
		"timestamp": timestamp,
		"service": "backoffice",
		"event_type": event_type,
		"level": level,
		"value": value,
		"message": None,
		"tags": tags or {},
	}


def _insert(engine, rows: list[dict]) -> None:
	with Session(engine) as session:
		session.execute(telemetry_events_table.insert(), rows)
		session.commit()


def _window(start_day: int, end_day: int) -> tuple[datetime, datetime]:
	return (
		datetime(2026, 10, start_day, tzinfo=UTC),
		datetime(2026, 10, end_day, tzinfo=UTC),
	)


def test_events_per_day_counts_by_utc_day_and_type(engine):
	_insert(
		engine,
		[
			_row("page_view", datetime(2026, 10, 21, 10, tzinfo=UTC)),
			_row("page_view", datetime(2026, 10, 21, 11, tzinfo=UTC)),
			_row(
				"inbound_order_created",
				datetime(2026, 10, 22, 9, tzinfo=UTC),
			),
		],
	)

	records = analysis.events_per_day(engine, *_window(21, 23))

	assert records == [
		{"date": "2026-10-21", "event_type": "page_view", "count": 2},
		{
			"date": "2026-10-22",
			"event_type": "inbound_order_created",
			"count": 1,
		},
	]


def test_events_per_day_uses_inclusive_start_exclusive_end_and_catalogue(
	engine,
):
	_insert(
		engine,
		[
			_row("page_view", datetime(2026, 10, 21, 0, tzinfo=UTC)),
			_row("page_view", datetime(2026, 10, 22, 0, tzinfo=UTC)),
			_row("page_view", datetime(2026, 10, 20, 23, tzinfo=UTC)),
			_row("unknown_event", datetime(2026, 10, 21, 12, tzinfo=UTC)),
		],
	)

	records = analysis.events_per_day(engine, *_window(21, 22))

	assert records == [
		{"date": "2026-10-21", "event_type": "page_view", "count": 1}
	]


def test_events_per_day_empty_window_returns_empty_list(engine):
	assert analysis.events_per_day(engine, *_window(1, 2)) == []


def test_error_rate_uses_the_daily_total_as_denominator(engine):
	_insert(
		engine,
		[
			_row("page_view", datetime(2026, 10, 21, 9, tzinfo=UTC)),
			_row("page_view", datetime(2026, 10, 21, 10, tzinfo=UTC)),
			_row(
				"frontend_error_captured",
				datetime(2026, 10, 21, 11, tzinfo=UTC),
				level="error",
			),
			_row(
				"inbound_order_created",
				datetime(2026, 10, 21, 12, tzinfo=UTC),
			),
		],
	)

	records = analysis.error_rate_by_type(engine, *_window(21, 22))

	assert records == [
		{
			"date": "2026-10-21",
			"event_type": "frontend_error_captured",
			"total_count": 1,
			"error_count": 1,
			"daily_total": 4,
			"error_rate": 0.25,
		},
		{
			"date": "2026-10-21",
			"event_type": "inbound_order_created",
			"total_count": 1,
			"error_count": 0,
			"daily_total": 4,
			"error_rate": 0.0,
		},
		{
			"date": "2026-10-21",
			"event_type": "page_view",
			"total_count": 2,
			"error_count": 0,
			"daily_total": 4,
			"error_rate": 0.0,
		},
	]


def test_error_rate_with_no_errors_reports_zero(engine):
	_insert(
		engine,
		[
			_row("page_view", datetime(2026, 10, 21, 9, tzinfo=UTC)),
			_row("login_failed", datetime(2026, 10, 21, 10, tzinfo=UTC), "warn"),
		],
	)

	records = analysis.error_rate_by_type(engine, *_window(21, 22))

	assert {record["error_count"] for record in records} == {0}
	assert {record["error_rate"] for record in records} == {0.0}


def test_error_rate_empty_window_returns_empty_list(engine):
	assert analysis.error_rate_by_type(engine, *_window(1, 2)) == []


def test_page_load_latency_groups_route_and_utc_day(engine):
	_insert(
		engine,
		[
			_row(
				"page_view",
				datetime(2026, 10, 21, 10, tzinfo=UTC),
				tags={
					"page_path": "/inventory/products",
					"load_duration_ms": 700,
				},
			),
			_row(
				"page_view",
				datetime(2026, 10, 21, 11, tzinfo=UTC),
				tags={
					"page_path": "/inventory/products",
					"load_duration_ms": 900,
				},
			),
			_row(
				"page_view",
				datetime(2026, 10, 22, 8, tzinfo=UTC),
				tags={"page_path": "/login", "load_duration_ms": 300},
			),
		],
	)

	records = analysis.page_load_latency_by_day(engine, *_window(21, 23))

	assert records == [
		{
			"date": "2026-10-21",
			"page_path": "/inventory/products",
			"average_load_duration_ms": 800.0,
			"sample_count": 2,
		},
		{
			"date": "2026-10-22",
			"page_path": "/login",
			"average_load_duration_ms": 300.0,
			"sample_count": 1,
		},
	]


def test_page_load_latency_drops_missing_and_invalid_samples(engine):
	_insert(
		engine,
		[
			_row(
				"page_view",
				datetime(2026, 10, 21, 10, tzinfo=UTC),
				tags={"page_path": "/missing-duration"},
			),
			_row(
				"page_view",
				datetime(2026, 10, 21, 11, tzinfo=UTC),
				tags={"page_path": "/slow", "load_duration_ms": "slow"},
			),
			_row(
				"page_view",
				datetime(2026, 10, 21, 12, tzinfo=UTC),
				tags={"load_duration_ms": 100},
			),
			_row(
				"page_view",
				datetime(2026, 10, 21, 13, tzinfo=UTC),
				tags={"page_path": "/valid", "load_duration_ms": 500},
			),
		],
	)

	records = analysis.page_load_latency_by_day(engine, *_window(21, 22))

	assert records == [
		{
			"date": "2026-10-21",
			"page_path": "/valid",
			"average_load_duration_ms": 500.0,
			"sample_count": 1,
		}
	]


def test_page_load_latency_empty_window_returns_empty_list(engine):
	assert analysis.page_load_latency_by_day(engine, *_window(1, 2)) == []


def test_analysis_propagates_database_errors(engine, monkeypatch):
	def failing_read(*_args, **_kwargs):
		raise SQLAlchemyError("database unavailable")

	monkeypatch.setattr(analysis, "_read_frame", failing_read)

	with pytest.raises(SQLAlchemyError):
		analysis.events_per_day(engine, *_window(21, 22))
