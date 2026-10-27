"""Reporting endpoint tests: KPI query, latest run, and manual trigger."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

import services.reporting.service as reporting_service
from data.pipelines.weekly_office_program_performance.schema import (
    pipeline_runs,
    weekly_office_program_performance,
)
from data.process.weekly_performance.constants import (
    PIPELINE_NAME,
    most_recent_complete_week,
)
from data.process.weekly_performance.errors import DispatchError

UTC = timezone.utc


def _insert_kpi(
    engine,
    *,
    office: str,
    programme: str,
    week,
    cost: str,
    kits: int = 0,
    shortages: int = 0,
    variances: int = 0,
    currency: str | None = None,
) -> None:
    with Session(engine) as session:
        session.execute(
            weekly_office_program_performance.insert().values(
                id=uuid.uuid4(),
                office=office,
                programme_id=programme,
                week_start=week,
                total_material_cost=Decimal(cost),
                kits_delivered_count=kits,
                shortage_events_count=shortages,
                cost_variance_events_count=variances,
                currency=currency
                or ("EUR" if office == "valencia" else "USD"),
                computed_at=datetime.now(UTC),
            )
        )
        session.commit()


def _insert_run(
    engine,
    *,
    status: str = "completed",
    started_at: datetime | None | object = ...,
    finished_at: datetime | None = None,
    heartbeat_at: datetime | None = None,
    target_weeks: list[str] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> str:
    run_id = uuid.uuid4()
    now = datetime.now(UTC)
    started = now - timedelta(minutes=1) if started_at is ... else started_at
    with Session(engine) as session:
        session.execute(
            pipeline_runs.insert().values(
                run_id=run_id,
                flow_run_id=None,
                pipeline_name=PIPELINE_NAME,
                trigger_type="manual",
                triggered_by="user:1",
                status=status,
                target_weeks=target_weeks or ["2026-10-19"],
                source_window_start=now - timedelta(days=7),
                source_window_end=now,
                started_at=started,
                finished_at=finished_at,
                heartbeat_at=heartbeat_at,
                checkpoint_stage="complete" if status == "completed" else "extract",
                checkpoint_week=None,
                records_extracted=7,
                records_deduplicated=6,
                records_rejected=1,
                records_loaded=4,
                source_event_counts={"outbound_order_created": 3},
                office_counts={"valencia": 4, "miami": 3},
                reconciliation={"checks": {"currencies_match_offices": True}},
                error_code=error_code,
                error_message=error_message,
                created_at=now,
            )
        )
        session.commit()
    return str(run_id)


def test_get_report_returns_latest_computed_week_with_numeric_money(
    inventory_client, sqlite_engine, auth_headers
):
    latest = most_recent_complete_week()
    previous = latest - timedelta(weeks=1)
    _insert_kpi(
        sqlite_engine,
        office="valencia",
        programme="b2b-sales",
        week=previous,
        cost="1.00",
        kits=1,
    )
    _insert_kpi(
        sqlite_engine,
        office="valencia",
        programme="b2b-sales",
        week=latest,
        cost="48.00",
        kits=2,
        shortages=1,
    )
    _insert_kpi(
        sqlite_engine,
        office="miami",
        programme="b2b-sales",
        week=latest,
        cost="0.00",
    )
    _insert_kpi(
        sqlite_engine,
        office="valencia",
        programme="basic-leadership",
        week=latest,
        cost="12.50",
        variances=1,
    )

    response = inventory_client.get(
        "/reporting/weekly-office-program-performance", headers=auth_headers
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["week_start"] == latest.isoformat()
    assert [entry["office"] for entry in payload["entries"]] == [
        "miami",
        "valencia",
        "valencia",
    ]
    valencia = next(
        entry
        for entry in payload["entries"]
        if entry["office"] == "valencia"
        and entry["programme_id"] == "b2b-sales"
    )
    assert valencia["total_material_cost"] == 48.0
    assert valencia["kits_delivered_count"] == 2
    assert valencia["shortage_events_count"] == 1
    assert valencia["currency"] == "EUR"

    unauthenticated = inventory_client.get(
        "/reporting/weekly-office-program-performance"
    )
    assert unauthenticated.status_code == 401


def test_get_report_explicit_week_and_validation_errors(
    inventory_client, sqlite_engine, auth_headers
):
    latest = most_recent_complete_week()
    previous = latest - timedelta(weeks=1)
    _insert_kpi(
        sqlite_engine,
        office="valencia",
        programme="b2b-sales",
        week=previous,
        cost="5.00",
    )

    explicit = inventory_client.get(
        "/reporting/weekly-office-program-performance",
        params={"week_start": previous.isoformat()},
        headers=auth_headers,
    )
    assert explicit.status_code == 200
    assert explicit.json()["week_start"] == previous.isoformat()

    non_monday = inventory_client.get(
        "/reporting/weekly-office-program-performance",
        params={"week_start": (latest + timedelta(days=1)).isoformat()},
        headers=auth_headers,
    )
    assert non_monday.status_code == 422

    current_incomplete = inventory_client.get(
        "/reporting/weekly-office-program-performance",
        params={"week_start": (latest + timedelta(days=7)).isoformat()},
        headers=auth_headers,
    )
    assert current_incomplete.status_code == 422

    no_rows = inventory_client.get(
        "/reporting/weekly-office-program-performance",
        params={"week_start": (previous - timedelta(weeks=1)).isoformat()},
        headers=auth_headers,
    )
    assert no_rows.status_code == 404


def test_get_report_database_failure_returns_503(
    inventory_client, auth_headers, monkeypatch
):
    def broken(*_args, **_kwargs):
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(reporting_service.queries, "get_weekly_report", broken)

    response = inventory_client.get(
        "/reporting/weekly-office-program-performance", headers=auth_headers
    )

    assert response.status_code == 503


def test_latest_run_handles_queued_null_timestamps(
    inventory_client, sqlite_engine, auth_headers
):
    run_id = _insert_run(
        sqlite_engine,
        status="queued",
        started_at=None,
        target_weeks=["2026-10-19", "2026-10-12"],
    )

    response = inventory_client.get(
        "/reporting/pipeline-runs/latest", headers=auth_headers
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["run_id"] == run_id
    assert payload["status"] == "queued"
    assert payload["started_at"] is None
    assert payload["finished_at"] is None
    assert payload["target_weeks"] == ["2026-10-19", "2026-10-12"]
    assert payload["records_extracted"] == 7
    assert payload["source_event_counts"] == {"outbound_order_created": 3}
    assert payload["error"] is None


def test_latest_run_missing_returns_404(inventory_client, auth_headers):
    response = inventory_client.get(
        "/reporting/pipeline-runs/latest", headers=auth_headers
    )
    assert response.status_code == 404


def test_latest_run_database_failure_returns_503(
    inventory_client, auth_headers, monkeypatch
):
    def broken(*_args, **_kwargs):
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(reporting_service.status, "get_latest_run", broken)

    response = inventory_client.get(
        "/reporting/pipeline-runs/latest", headers=auth_headers
    )
    assert response.status_code == 503


def test_trigger_requires_manager_or_admin(
    inventory_client, sqlite_engine, auth_headers, manager_headers, monkeypatch
):
    dispatched: list[dict] = []

    def fake_dispatch(**kwargs):
        dispatched.append(kwargs)
        return "flow-run-id"

    monkeypatch.setattr(
        reporting_service.triggers, "dispatch_flow_run", fake_dispatch
    )

    forbidden = inventory_client.post(
        "/reporting/pipeline-runs", json={}, headers=auth_headers
    )
    assert forbidden.status_code == 403
    assert dispatched == []

    accepted = inventory_client.post(
        "/reporting/pipeline-runs", json={}, headers=manager_headers
    )
    assert accepted.status_code == 202, accepted.text
    payload = accepted.json()
    assert payload["status"] == "queued"
    assert payload["target_weeks"] == [most_recent_complete_week().isoformat()]
    assert dispatched and dispatched[0]["run_id"] == payload["run_id"]

    with Session(sqlite_engine) as session:
        row = session.execute(
            pipeline_runs.select().where(
                pipeline_runs.c.run_id == uuid.UUID(payload["run_id"])
            )
        ).mappings().one()
    assert row["status"] == "queued"
    assert row["trigger_type"] == "manual"
    assert row["triggered_by"].startswith("user:")


def test_trigger_active_run_conflict(
    inventory_client, sqlite_engine, manager_headers, monkeypatch
):
    _insert_run(
        sqlite_engine,
        status="running",
        started_at=datetime.now(UTC),
        heartbeat_at=datetime.now(UTC),
    )
    monkeypatch.setattr(
        reporting_service.triggers,
        "dispatch_flow_run",
        lambda **_kwargs: "flow-run-id",
    )

    response = inventory_client.post(
        "/reporting/pipeline-runs", json={}, headers=manager_headers
    )

    assert response.status_code == 409


def test_trigger_invalid_ranges(inventory_client, manager_headers, monkeypatch):
    monkeypatch.setattr(
        reporting_service.triggers,
        "dispatch_flow_run",
        lambda **_kwargs: "flow-run-id",
    )
    latest = most_recent_complete_week()

    non_monday = inventory_client.post(
        "/reporting/pipeline-runs",
        json={"week_start": (latest + timedelta(days=1)).isoformat()},
        headers=manager_headers,
    )
    assert non_monday.status_code == 422

    zero_weeks = inventory_client.post(
        "/reporting/pipeline-runs", json={"weeks": 0}, headers=manager_headers
    )
    assert zero_weeks.status_code == 422

    too_many_weeks = inventory_client.post(
        "/reporting/pipeline-runs", json={"weeks": 53}, headers=manager_headers
    )
    assert too_many_weeks.status_code == 422

    incomplete = inventory_client.post(
        "/reporting/pipeline-runs",
        json={"week_start": (latest + timedelta(days=7)).isoformat()},
        headers=manager_headers,
    )
    assert incomplete.status_code == 422


def test_trigger_recovers_stale_run_before_starting(
    inventory_client, sqlite_engine, manager_headers, monkeypatch
):
    stale_time = datetime.now(UTC) - timedelta(minutes=30)
    stale_id = _insert_run(
        sqlite_engine,
        status="running",
        started_at=stale_time,
        heartbeat_at=stale_time,
    )
    monkeypatch.setattr(
        reporting_service.triggers,
        "dispatch_flow_run",
        lambda **_kwargs: "flow-run-id",
    )

    response = inventory_client.post(
        "/reporting/pipeline-runs", json={}, headers=manager_headers
    )

    assert response.status_code == 202, response.text
    with Session(sqlite_engine) as session:
        stale = session.execute(
            pipeline_runs.select().where(
                pipeline_runs.c.run_id == uuid.UUID(stale_id)
            )
        ).mappings().one()
        newest = session.execute(
            pipeline_runs.select().order_by(pipeline_runs.c.created_at.desc())
        ).mappings().first()
    assert stale["status"] == "failed"
    assert stale["error_code"] == "stale_run"
    assert newest["status"] == "queued"
    assert str(newest["run_id"]) == response.json()["run_id"]


def test_trigger_dispatch_failure_marks_run_failed(
    inventory_client, sqlite_engine, manager_headers, monkeypatch
):
    def failed_dispatch(**_kwargs):
        raise DispatchError("Prefect unavailable")

    monkeypatch.setattr(
        reporting_service.triggers, "dispatch_flow_run", failed_dispatch
    )

    response = inventory_client.post(
        "/reporting/pipeline-runs", json={}, headers=manager_headers
    )

    assert response.status_code == 503
    with Session(sqlite_engine) as session:
        row = session.execute(
            pipeline_runs.select().order_by(pipeline_runs.c.created_at.desc())
        ).mappings().first()
    assert row["status"] == "failed"
    assert row["error_code"] == "dispatch_failed"


def test_trigger_unauthenticated(inventory_client):
    response = inventory_client.post("/reporting/pipeline-runs", json={})
    assert response.status_code == 401
