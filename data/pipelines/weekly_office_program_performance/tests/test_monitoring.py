"""Health-check rule tests for freshness, silence, and baseline diagnostics."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from data.pipelines.weekly_office_program_performance import run_log
from data.pipelines.weekly_office_program_performance.monitoring import (
    run_health_checks,
)

UTC = timezone.utc
WEEK = date(2026, 10, 19)


def _alert_codes(checks: dict) -> set[str]:
    return {alert["alert"] for alert in checks["alerts"]}


def _completed_run(engine, *, finished_at, records_extracted=0, office_counts=None,
                   records_rejected=0, reconciliation=None) -> str:
    run_id = str(uuid.uuid4())
    run_log.create_or_adopt_run(
        engine,
        run_id=run_id,
        trigger_type="scheduled",
        triggered_by=None,
        target_weeks=[WEEK],
        source_window_start=datetime(2026, 10, 19, tzinfo=UTC),
        source_window_end=datetime(2026, 10, 26, tzinfo=UTC),
    )
    run_log.finalize_run(
        engine,
        run_id,
        status="completed",
        finished_at=finished_at,
        records_extracted=records_extracted,
        records_rejected=records_rejected,
        office_counts=office_counts or {},
        reconciliation=reconciliation or {},
    )
    return run_id


def test_no_runs_alerts_missing_run_and_insufficient_baseline(pipeline_engine):
    checks = run_health_checks(pipeline_engine)

    assert "weekly_run_missing" in _alert_codes(checks)
    assert checks["baseline_status"] == "insufficient_baseline"


def test_fresh_completed_run_is_healthy(pipeline_engine):
    _completed_run(pipeline_engine, finished_at=datetime.now(UTC))

    checks = run_health_checks(pipeline_engine)

    assert checks["alerts"] == []
    assert checks["baseline_status"] == "insufficient_baseline"


def test_failed_latest_run_alerts(pipeline_engine):
    run_id = str(uuid.uuid4())
    run_log.create_or_adopt_run(
        pipeline_engine,
        run_id=run_id,
        trigger_type="scheduled",
        triggered_by=None,
        target_weeks=[WEEK],
        source_window_start=datetime(2026, 10, 19, tzinfo=UTC),
        source_window_end=datetime(2026, 10, 26, tzinfo=UTC),
    )
    run_log.finalize_run(
        pipeline_engine,
        run_id,
        status="failed",
        finished_at=datetime.now(UTC),
        error_code="load_conflict",
        error_message="sanitized failure",
    )

    checks = run_health_checks(pipeline_engine)

    assert "weekly_run_failed" in _alert_codes(checks)


def test_stale_active_run_alerts(pipeline_engine):
    run_id = str(uuid.uuid4())
    run_log.create_or_adopt_run(
        pipeline_engine,
        run_id=run_id,
        trigger_type="scheduled",
        triggered_by=None,
        target_weeks=[WEEK],
        source_window_start=datetime(2026, 10, 19, tzinfo=UTC),
        source_window_end=datetime(2026, 10, 26, tzinfo=UTC),
    )
    stale_time = datetime.now(UTC) - timedelta(minutes=30)
    run_log.update_run(
        pipeline_engine, run_id, heartbeat_at=stale_time, started_at=stale_time
    )

    checks = run_health_checks(pipeline_engine)

    assert "stale_run" in _alert_codes(checks)


def test_missed_run_beyond_eight_days_alerts(pipeline_engine):
    _completed_run(
        pipeline_engine,
        finished_at=datetime.now(UTC) - timedelta(days=9),
        records_extracted=1,
    )

    checks = run_health_checks(pipeline_engine)

    assert "weekly_run_missing" in _alert_codes(checks)


def test_zero_week_after_activity_alerts_unexpected_silence(pipeline_engine):
    _completed_run(
        pipeline_engine,
        finished_at=datetime.now(UTC) - timedelta(days=1),
        records_extracted=4,
        office_counts={"valencia": 4},
    )
    _completed_run(
        pipeline_engine,
        finished_at=datetime.now(UTC),
        records_extracted=0,
        office_counts={},
    )

    checks = run_health_checks(pipeline_engine)

    assert "unexpected_silence" in _alert_codes(checks)
    assert checks["baseline_status"] == "insufficient_baseline"


def test_zero_week_without_history_is_a_true_zero(pipeline_engine):
    _completed_run(
        pipeline_engine,
        finished_at=datetime.now(UTC),
        records_extracted=0,
    )

    checks = run_health_checks(pipeline_engine)

    assert "unexpected_silence" not in _alert_codes(checks)
    assert checks["baseline_status"] == "insufficient_baseline"


def test_one_sided_office_silence_alerts_that_office(pipeline_engine):
    _completed_run(
        pipeline_engine,
        finished_at=datetime.now(UTC) - timedelta(days=1),
        records_extracted=6,
        office_counts={"valencia": 4, "miami": 2},
    )
    _completed_run(
        pipeline_engine,
        finished_at=datetime.now(UTC),
        records_extracted=3,
        office_counts={"valencia": 3},
    )

    checks = run_health_checks(pipeline_engine)

    silence = [
        alert for alert in checks["alerts"] if alert["alert"] == "office_silence"
    ]
    assert [alert["office"] for alert in silence] == ["miami"]


def test_rejected_events_and_reconciliation_warnings_alert(pipeline_engine):
    _completed_run(
        pipeline_engine,
        finished_at=datetime.now(UTC),
        records_extracted=10,
        records_rejected=1,
        reconciliation={"warnings": ["unknown_programme_ids"]},
    )

    checks = run_health_checks(pipeline_engine)

    assert "rejected_events" in _alert_codes(checks)
    assert "reconciliation_warning" in _alert_codes(checks)
