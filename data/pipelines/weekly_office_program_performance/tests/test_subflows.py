"""Subflow, orchestration, race, resume, and late-event tests (SQLite).

These tests exercise the real Prefect subflows and the main flow against an
in-memory SQLite database. No external services are required.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from data.pipelines.weekly_office_program_performance import run_log, subflows
from data.pipelines.weekly_office_program_performance.flow import (
    weekly_office_program_performance_flow,
)
from data.pipelines.weekly_office_program_performance.schema import (
    pipeline_runs,
    weekly_office_program_performance,
)
from data.process.weekly_performance.errors import (
    ActiveRunExistsError,
    NoRunFoundError,
)

from .helpers import insert_event, seed_dimensions

WEEK = "2026-10-19"
WEEK_PREVIOUS = "2026-10-12"
UTC = timezone.utc


def _kpi_rows(pipeline_engine, week_start: str) -> list[dict]:
    with pipeline_engine.connect() as connection:
        rows = connection.execute(
            select(weekly_office_program_performance).where(
                weekly_office_program_performance.c.week_start
                == date.fromisoformat(week_start)
            )
        ).mappings().all()
    return [dict(row) for row in rows]


def _latest_run(pipeline_engine) -> dict:
    with pipeline_engine.connect() as connection:
        row = connection.execute(
            select(pipeline_runs).order_by(pipeline_runs.c.created_at.desc()).limit(1)
        ).mappings().first()
    assert row is not None
    return dict(row)


def _run_count(pipeline_engine) -> int:
    with pipeline_engine.connect() as connection:
        return connection.execute(
            select(pipeline_runs.c.run_id)
        ).all()


def test_extract_subflow_reads_week_and_dimension_scaffold(
    pipeline_engine, sqlite_engine
):
    seed_dimensions(sqlite_engine)
    insert_event(
        sqlite_engine,
        "inbound_order_created",
        event_id="e1",
        quantity=3,
        unit_cost="12.50",
    )
    insert_event(
        sqlite_engine,
        "outbound_order_created",
        event_id="e2",
        office="miami",
        currency="USD",
    )

    result = subflows.extract_weekly_office_program_telemetry_flow(WEEK)

    assert len(result["raw_rows"]) == 2
    assert result["source_event_counts"] == {
        "inbound_order_created": 1,
        "outbound_order_created": 1,
    }
    assert ["valencia", "b2b-sales"] in result["dimension_pairs"]
    assert ["miami", "b2b-sales"] in result["dimension_pairs"]
    assert ["valencia", "basic-leadership"] in result["dimension_pairs"]


def test_transform_subflow_computes_golden_kpis(pipeline_engine, sqlite_engine):
    seed_dimensions(sqlite_engine)
    insert_event(
        sqlite_engine, "inbound_order_created", event_id="a", quantity=3,
        unit_cost="12.50", order_id="1",
    )
    insert_event(
        sqlite_engine, "inbound_order_created", event_id="b", quantity=2,
        unit_cost="5.25", order_id="2",
    )
    insert_event(
        sqlite_engine, "outbound_order_created", event_id="c", quantity=10,
        order_id="3",
    )
    insert_event(
        sqlite_engine, "stock_threshold_triggered", event_id="d", quantity=0,
    )
    insert_event(
        sqlite_engine, "kit_cost_variance_detected", event_id="e", quantity=1,
        unit_cost="20.00", order_id="4",
    )

    extracted = subflows.extract_weekly_office_program_telemetry_flow(WEEK)
    result = subflows.transform_weekly_office_program_performance_flow(
        extracted["raw_rows"],
        extracted["dimension_pairs"],
        extracted["known_programmes"],
        WEEK,
    )

    valencia = next(
        row
        for row in result["rows"]
        if row["office"] == "valencia" and row["programme_id"] == "b2b-sales"
    )
    assert valencia["total_material_cost"] == "48.00"
    assert valencia["kits_delivered_count"] == 1
    assert valencia["shortage_events_count"] == 1
    assert valencia["cost_variance_events_count"] == 1
    assert result["publication_blocked"] is False
    assert result["reconciliation"]["week_fingerprint"]


def test_load_subflow_persists_and_is_idempotent(pipeline_engine):
    run_id = str(uuid.uuid4())
    run_log.create_or_adopt_run(
        pipeline_engine,
        run_id=run_id,
        trigger_type="manual",
        triggered_by="test",
        target_weeks=[date.fromisoformat(WEEK)],
        source_window_start=datetime(2026, 10, 19, tzinfo=UTC),
        source_window_end=datetime(2026, 10, 26, tzinfo=UTC),
    )
    rows = [
        {
            "office": "valencia",
            "programme_id": "b2b-sales",
            "week_start": WEEK,
            "total_material_cost": "48.00",
            "kits_delivered_count": 2,
            "shortage_events_count": 0,
            "cost_variance_events_count": 0,
            "currency": "EUR",
        }
    ]

    first = subflows.load_weekly_office_program_performance_flow(
        WEEK, rows, [], run_id
    )
    second = subflows.load_weekly_office_program_performance_flow(
        WEEK, rows, [], run_id
    )

    assert first["records_loaded"] == second["records_loaded"] == 1
    stored = _kpi_rows(pipeline_engine, WEEK)
    assert len(stored) == 1
    assert float(stored[0]["total_material_cost"]) == 48.0


def test_main_flow_publishes_report_and_records_run_metadata(
    pipeline_engine, sqlite_engine, snapshot_dir
):
    seed_dimensions(sqlite_engine)
    insert_event(
        sqlite_engine, "outbound_order_created", event_id="x1", quantity=2,
        order_id="1",
    )

    result = weekly_office_program_performance_flow(
        week_start=WEEK, weeks=1, trigger_type="manual", requested_by="test"
    )

    assert result["status"] == "completed"
    run = _latest_run(pipeline_engine)
    assert run["status"] == "completed"
    assert run["started_at"] is not None
    assert run["finished_at"] is not None
    assert run["records_extracted"] == 1
    assert run["records_loaded"] == 3  # valencia/miami b2b-sales + valencia leadership
    assert run["error_code"] is None
    assert run["reconciliation"]["weeks"][WEEK]["kpi_totals"] == {
        "outbound_order_created": 1,
        "stock_threshold_triggered": 0,
        "kit_cost_variance_detected": 0,
    }
    assert (snapshot_dir / f"run_{result['run_id']}.json").is_file()


def test_optional_snapshot_failure_does_not_fail_publication(
    pipeline_engine, sqlite_engine, snapshot_dir
):
    seed_dimensions(sqlite_engine)
    insert_event(
        sqlite_engine, "outbound_order_created", event_id="x1", quantity=2,
        order_id="1",
    )

    result = weekly_office_program_performance_flow(
        week_start=WEEK,
        weeks=1,
        trigger_type="manual",
        snapshot_failure_injection=True,
    )

    assert result["status"] == "completed_with_warnings"
    assert "eval_snapshot_failed" in result["warnings"]
    assert _latest_run(pipeline_engine)["status"] == "completed_with_warnings"
    assert len(_kpi_rows(pipeline_engine, WEEK)) == 3


def test_scheduled_run_skips_when_another_run_is_active(pipeline_engine):
    run_log.create_or_adopt_run(
        pipeline_engine,
        run_id=str(uuid.uuid4()),
        trigger_type="scheduled",
        triggered_by=None,
        target_weeks=[date.fromisoformat(WEEK)],
        source_window_start=datetime(2026, 10, 19, tzinfo=UTC),
        source_window_end=datetime(2026, 10, 26, tzinfo=UTC),
    )

    result = weekly_office_program_performance_flow(
        week_start=WEEK, weeks=1, trigger_type="scheduled"
    )

    assert result["status"] == "skipped_locked"
    assert _kpi_rows(pipeline_engine, WEEK) == []


def test_manual_run_conflicts_with_an_active_run(pipeline_engine):
    run_log.create_or_adopt_run(
        pipeline_engine,
        run_id=str(uuid.uuid4()),
        trigger_type="manual",
        triggered_by="test",
        target_weeks=[date.fromisoformat(WEEK)],
        source_window_start=datetime(2026, 10, 19, tzinfo=UTC),
        source_window_end=datetime(2026, 10, 26, tzinfo=UTC),
    )

    with pytest.raises(ActiveRunExistsError):
        weekly_office_program_performance_flow(
            week_start=WEEK, weeks=1, trigger_type="manual"
        )


def test_worker_adopts_the_api_queued_run(pipeline_engine, sqlite_engine, snapshot_dir):
    seed_dimensions(sqlite_engine)
    queued_id = str(uuid.uuid4())
    run_log.create_or_adopt_run(
        pipeline_engine,
        run_id=queued_id,
        trigger_type="manual",
        triggered_by="user:1",
        target_weeks=[date.fromisoformat(WEEK)],
        source_window_start=datetime(2026, 10, 19, tzinfo=UTC),
        source_window_end=datetime(2026, 10, 26, tzinfo=UTC),
    )
    run_log.update_run(pipeline_engine, queued_id, status="queued")

    result = weekly_office_program_performance_flow(
        week_start=WEEK, weeks=1, trigger_type="manual", run_id=queued_id
    )

    assert result["status"] == "completed"
    assert result["run_id"] == queued_id
    runs = _run_count(pipeline_engine)
    assert len(runs) == 1
    assert _latest_run(pipeline_engine)["triggered_by"] == "user:1"


def test_late_event_recompute_supersedes_previous_publication(
    pipeline_engine, sqlite_engine, snapshot_dir
):
    seed_dimensions(sqlite_engine)
    insert_event(
        sqlite_engine, "inbound_order_created", event_id="a", quantity=1,
        unit_cost="10.00", order_id="1",
    )

    first = weekly_office_program_performance_flow(
        week_start=WEEK, weeks=1, trigger_type="manual"
    )
    first_id = first["run_id"]
    first_row_ids = {
        (row["office"], row["programme_id"]): row["id"]
        for row in _kpi_rows(pipeline_engine, WEEK)
    }

    # A late event with a timestamp inside the already published week arrives.
    insert_event(
        sqlite_engine, "inbound_order_created", event_id="late", quantity=1,
        unit_cost="5.00", order_id="2",
    )

    second = weekly_office_program_performance_flow(
        week_start=WEEK, weeks=1, trigger_type="recompute"
    )

    assert second["supersedes_run_id"] == first_id
    assert second["recomputed_weeks"] == [WEEK]
    run = _latest_run(pipeline_engine)
    assert run["trigger_type"] == "recompute"
    assert run["supersedes_run_id"] == uuid.UUID(first_id)
    recomputed = run["reconciliation"]["recomputed_weeks"]
    assert set(recomputed[WEEK]) == {"previous_fingerprint", "new_fingerprint"}
    assert recomputed[WEEK]["new_fingerprint"] != recomputed[WEEK]["previous_fingerprint"]

    rows = { (row["office"], row["programme_id"]): row for row in _kpi_rows(pipeline_engine, WEEK) }
    assert float(rows[("valencia", "b2b-sales")]["total_material_cost"]) == 15.0
    assert rows[("valencia", "b2b-sales")]["id"] == first_row_ids[("valencia", "b2b-sales")]


def test_unchanged_recompute_does_not_supersede(
    pipeline_engine, sqlite_engine, snapshot_dir
):
    seed_dimensions(sqlite_engine)
    insert_event(
        sqlite_engine, "outbound_order_created", event_id="a", quantity=1,
        order_id="1",
    )

    first = weekly_office_program_performance_flow(
        week_start=WEEK, weeks=1, trigger_type="manual"
    )
    second = weekly_office_program_performance_flow(
        week_start=WEEK, weeks=1, trigger_type="recompute"
    )

    assert second["supersedes_run_id"] is None
    assert second["recomputed_weeks"] == []
    assert second["run_id"] != first["run_id"]


def test_resume_skips_committed_weeks_and_recomputes_the_failed_week(
    pipeline_engine, sqlite_engine, snapshot_dir, monkeypatch
):
    seed_dimensions(sqlite_engine)
    insert_event(
        sqlite_engine, "outbound_order_created", event_id="a", quantity=1,
        order_id="1",
    )

    real_load = subflows.load_weekly_performance

    def flaky_load(week_start, rows, rejections, run_id):
        if week_start == WEEK:
            raise ConnectionError("injected mid-run failure")
        return real_load(week_start, rows, rejections, run_id)

    monkeypatch.setattr(subflows, "load_weekly_performance", flaky_load)

    with pytest.raises(ConnectionError):
        weekly_office_program_performance_flow(
            week_start=WEEK_PREVIOUS, weeks=2, trigger_type="manual"
        )

    failed = _latest_run(pipeline_engine)
    assert failed["status"] == "failed"
    assert failed["checkpoint_stage"] == "load"
    assert failed["checkpoint_week"] == date.fromisoformat(WEEK)
    previous_week_rows = _kpi_rows(pipeline_engine, WEEK_PREVIOUS)
    assert len(previous_week_rows) == 3
    previous_ids = {
        (row["office"], row["programme_id"]): row["id"] for row in previous_week_rows
    }
    assert _kpi_rows(pipeline_engine, WEEK) == []

    monkeypatch.setattr(subflows, "load_weekly_performance", real_load)
    resumed = weekly_office_program_performance_flow(
        resume_from=str(failed["run_id"])
    )

    assert resumed["status"] == "completed"
    assert resumed["target_weeks"] == [WEEK]
    assert resumed["supersedes_run_id"] == str(failed["run_id"])
    assert len(_kpi_rows(pipeline_engine, WEEK)) == 3
    unchanged = _kpi_rows(pipeline_engine, WEEK_PREVIOUS)
    assert {
        (row["office"], row["programme_id"]): row["id"] for row in unchanged
    } == previous_ids


def test_resume_validation_errors(pipeline_engine):
    with pytest.raises(NoRunFoundError):
        weekly_office_program_performance_flow(resume_from=str(uuid.uuid4()))

    active_id = str(uuid.uuid4())
    run_log.create_or_adopt_run(
        pipeline_engine,
        run_id=active_id,
        trigger_type="manual",
        triggered_by="test",
        target_weeks=[date.fromisoformat(WEEK)],
        source_window_start=datetime(2026, 10, 19, tzinfo=UTC),
        source_window_end=datetime(2026, 10, 26, tzinfo=UTC),
    )
    with pytest.raises(ActiveRunExistsError):
        weekly_office_program_performance_flow(resume_from=active_id)


def test_stale_run_is_recovered_before_a_new_run(pipeline_engine, sqlite_engine, snapshot_dir):
    seed_dimensions(sqlite_engine)
    stale_id = str(uuid.uuid4())
    run_log.create_or_adopt_run(
        pipeline_engine,
        run_id=stale_id,
        trigger_type="manual",
        triggered_by="test",
        target_weeks=[date.fromisoformat(WEEK)],
        source_window_start=datetime(2026, 10, 19, tzinfo=UTC),
        source_window_end=datetime(2026, 10, 26, tzinfo=UTC),
    )
    stale_time = datetime.now(UTC) - timedelta(minutes=30)
    run_log.update_run(
        pipeline_engine, stale_id, heartbeat_at=stale_time, started_at=stale_time
    )

    result = weekly_office_program_performance_flow(
        week_start=WEEK, weeks=1, trigger_type="scheduled"
    )

    assert result["status"] == "completed"
    with pipeline_engine.connect() as connection:
        stale = connection.execute(
            select(pipeline_runs).where(
                pipeline_runs.c.run_id == uuid.UUID(stale_id)
            )
        ).mappings().one()
    assert stale["status"] == "failed"
    assert stale["error_code"] == "stale_run"
