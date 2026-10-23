"""Report endpoint period, cache, and failure-contract tests."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

import services.cache as cache_module
import services.telemetry.router as telemetry_routes
from services.telemetry.storage import telemetry_events_table

UTC = timezone.utc


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


def _insert(sqlite_engine, rows: list[dict]) -> None:
	with Session(sqlite_engine) as session:
		session.execute(telemetry_events_table.insert(), rows)
		session.commit()


def _get(client, params: dict | None = None):
	return client.get("/telemetry/report", params=params or {})


def test_report_returns_all_three_metrics_for_an_explicit_window(
	inventory_client, sqlite_engine
):
	_insert(
		sqlite_engine,
		[
			_row(
				"page_view",
				datetime(2026, 10, 21, 10, tzinfo=UTC),
				tags={
					"page_path": "/inventory/products",
					"load_duration_ms": 500,
				},
				value=500,
			),
			_row(
				"inbound_order_created",
				datetime(2026, 10, 21, 11, tzinfo=UTC),
			),
			_row(
				"frontend_error_captured",
				datetime(2026, 10, 21, 12, tzinfo=UTC),
				level="error",
			),
		],
	)

	response = _get(
		inventory_client,
		{"start_date": "2026-10-21", "end_date": "2026-10-22"},
	)

	assert response.status_code == 200
	payload = response.json()
	assert payload["period"] == {
		"from": "2026-10-21T00:00:00Z",
		"to": "2026-10-22T00:00:00Z",
	}
	assert payload["metrics"]["events_per_day"] == [
		{
			"date": "2026-10-21",
			"event_type": "frontend_error_captured",
			"count": 1,
		},
		{
			"date": "2026-10-21",
			"event_type": "inbound_order_created",
			"count": 1,
		},
		{"date": "2026-10-21", "event_type": "page_view", "count": 1},
	]
	error_rows = {
		record["event_type"]: record
		for record in payload["metrics"]["error_rate_by_type"]
	}
	assert error_rows["frontend_error_captured"]["error_count"] == 1
	assert error_rows["frontend_error_captured"]["daily_total"] == 3
	assert error_rows["frontend_error_captured"]["error_rate"] == pytest.approx(
		1 / 3
	)
	assert payload["metrics"]["page_load_latency_by_day"] == [
		{
			"date": "2026-10-21",
			"page_path": "/inventory/products",
			"average_load_duration_ms": 500.0,
			"sample_count": 1,
		}
	]


def test_report_defaults_to_a_cached_seven_day_window(
	inventory_client, sqlite_engine, monkeypatch
):
	_insert(
		sqlite_engine,
		[
			_row(
				"page_view",
				datetime.now(UTC) - timedelta(days=1),
				tags={"page_path": "/inventory/products", "load_duration_ms": 400},
			)
		],
	)

	calls = []
	real = telemetry_routes.analysis.events_per_day

	def counting(engine, start, end):
		calls.append((start, end))
		return real(engine, start, end)

	monkeypatch.setattr(
		telemetry_routes.analysis, "events_per_day", counting
	)

	first = _get(inventory_client)
	second = _get(inventory_client)

	assert first.status_code == 200
	assert second.status_code == 200
	assert first.json()["period"] == second.json()["period"]
	assert len(calls) == 1

	start = datetime.fromisoformat(
		first.json()["period"]["from"].replace("Z", "+00:00")
	)
	end = datetime.fromisoformat(
		first.json()["period"]["to"].replace("Z", "+00:00")
	)
	assert end - start == timedelta(days=7)


def test_report_single_bound_anchors_a_seven_day_window(inventory_client):
	start_only = _get(inventory_client, {"start_date": "2026-10-10"})
	end_only = _get(inventory_client, {"end_date": "2026-10-10"})

	assert start_only.status_code == 200
	assert start_only.json()["period"] == {
		"from": "2026-10-10T00:00:00Z",
		"to": "2026-10-17T00:00:00Z",
	}
	assert end_only.status_code == 200
	assert end_only.json()["period"] == {
		"from": "2026-10-03T00:00:00Z",
		"to": "2026-10-10T00:00:00Z",
	}


def test_report_normalises_offsets_and_groups_by_utc_day(
	inventory_client, sqlite_engine
):
	_insert(
		sqlite_engine,
		[
			_row(
				"page_view",
				datetime(2026, 10, 21, 23, 30, tzinfo=UTC),
				tags={"page_path": "/login", "load_duration_ms": 400},
			)
		],
	)

	response = _get(
		inventory_client,
		{
			"start_date": "2026-10-22T00:00:00+02:00",
			"end_date": "2026-10-22T02:00:00+02:00",
		},
	)

	assert response.status_code == 200
	assert response.json()["period"] == {
		"from": "2026-10-21T22:00:00Z",
		"to": "2026-10-22T00:00:00Z",
	}
	assert response.json()["metrics"]["events_per_day"] == [
		{"date": "2026-10-21", "event_type": "page_view", "count": 1}
	]


def test_report_uses_inclusive_start_and_exclusive_end(
	inventory_client, sqlite_engine
):
	_insert(
		sqlite_engine,
		[
			_row(
				"page_view",
				datetime(2026, 10, 21, 0, tzinfo=UTC),
				tags={"page_path": "/start", "load_duration_ms": 100},
			),
			_row(
				"page_view",
				datetime(2026, 10, 22, 0, tzinfo=UTC),
				tags={"page_path": "/end", "load_duration_ms": 200},
			),
		],
	)

	response = _get(
		inventory_client,
		{"start_date": "2026-10-21", "end_date": "2026-10-22"},
	)

	assert response.status_code == 200
	assert response.json()["metrics"]["events_per_day"] == [
		{"date": "2026-10-21", "event_type": "page_view", "count": 1}
	]
	assert response.json()["metrics"]["page_load_latency_by_day"] == [
		{
			"date": "2026-10-21",
			"page_path": "/start",
			"average_load_duration_ms": 100.0,
			"sample_count": 1,
		}
	]


def test_report_empty_window_returns_empty_arrays(inventory_client):
	response = _get(
		inventory_client,
		{"start_date": "2020-01-01", "end_date": "2020-01-02"},
	)

	assert response.status_code == 200
	assert response.json()["metrics"] == {
		"events_per_day": [],
		"error_rate_by_type": [],
		"page_load_latency_by_day": [],
	}


@pytest.mark.parametrize(
	"params",
	[
		{"start_date": "not-a-date"},
		{"start_date": "2026-10-22", "end_date": "2026-10-21"},
		{"start_date": "2026-10-21", "end_date": "2026-10-21"},
	],
)
def test_report_rejects_invalid_or_empty_ranges(inventory_client, params):
	response = _get(inventory_client, params)
	assert response.status_code == 422


def test_report_cache_hits_expire_and_do_not_share_windows(
	inventory_client, sqlite_engine, monkeypatch
):
	clock = {"now": 1_000.0}
	monkeypatch.setattr(
		cache_module,
		"time",
		SimpleNamespace(monotonic=lambda: clock["now"]),
	)

	calls = []
	real = telemetry_routes.analysis.events_per_day

	def counting(engine, start, end):
		calls.append((start, end))
		return real(engine, start, end)

	monkeypatch.setattr(
		telemetry_routes.analysis, "events_per_day", counting
	)

	window_a = {"start_date": "2026-10-21", "end_date": "2026-10-22"}
	window_b = {"start_date": "2026-10-22", "end_date": "2026-10-23"}

	_get(inventory_client, window_a)
	_get(inventory_client, window_a)
	assert len(calls) == 1

	clock["now"] += 61
	_get(inventory_client, window_a)
	_get(inventory_client, window_b)
	assert len(calls) == 3


def test_report_database_failure_returns_503_and_is_not_cached(
	inventory_client, sqlite_engine, monkeypatch
):
	_insert(
		sqlite_engine,
		[
			_row(
				"page_view",
				datetime(2026, 10, 21, 10, tzinfo=UTC),
				tags={"page_path": "/inventory/products", "load_duration_ms": 500},
			)
		],
	)

	calls = {"count": 0}
	real = telemetry_routes.analysis.events_per_day

	def flaky(engine, start, end):
		calls["count"] += 1
		if calls["count"] == 1:
			raise SQLAlchemyError("database unavailable")
		return real(engine, start, end)

	monkeypatch.setattr(telemetry_routes.analysis, "events_per_day", flaky)

	params = {"start_date": "2026-10-21", "end_date": "2026-10-22"}
	failed = _get(inventory_client, params)
	succeeded = _get(inventory_client, params)

	assert failed.status_code == 503
	assert succeeded.status_code == 200
	assert calls["count"] == 2
