"""State-machine tests for the nightly orchestration ``job_runs`` service."""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from services.job_runner.service import (
    JOB_NAME,
    claim_run,
    create_run,
    delete_run,
    finalize_run,
    get_run,
    has_completed_for_date,
    has_processing_lock,
    recover_stale_runs,
    sanitize_error,
)
from services.job_runner.storage import ensure_job_runs_table, job_runs

TARGET_DATE = date(2026, 11, 1)


def _count(engine, status=None):
    query = select(func.count()).select_from(job_runs)
    if status is not None:
        query = query.where(job_runs.c.status == status)
    with engine.connect() as connection:
        return connection.execute(query).scalar_one()


def _insert_processing(engine, job_name=JOB_NAME, started_at=None):
    from uuid import uuid4

    run_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            job_runs.insert().values(
                id=run_id,
                job_name=job_name,
                target_date=date(2026, 10, 31),
                status="processing",
                started_at=started_at or datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc),
            )
        )
    return run_id


def test_create_run_inserts_pending_with_defaults(engine):
    run_id = create_run(engine, job_name=JOB_NAME, target_date=TARGET_DATE)

    row = get_run(engine, run_id)
    assert row is not None
    assert row["job_name"] == JOB_NAME
    assert row["target_date"] == TARGET_DATE
    assert row["status"] == "pending"
    assert row["started_at"] is None
    assert row["finished_at"] is None
    assert row["error_message"] is None
    assert row["created_at"] is not None


def test_claim_run_transitions_pending_to_processing(engine):
    run_id = create_run(engine, job_name=JOB_NAME, target_date=TARGET_DATE)

    assert claim_run(engine, run_id) is True

    row = get_run(engine, run_id)
    assert row["status"] == "processing"
    assert row["started_at"] is not None


def test_claim_run_returns_false_when_not_pending(engine):
    run_id = create_run(engine, job_name=JOB_NAME, target_date=TARGET_DATE)
    assert claim_run(engine, run_id) is True

    assert claim_run(engine, run_id) is False
    assert get_run(engine, run_id)["status"] == "processing"


def test_has_processing_lock_true_then_false(engine):
    run_id = create_run(engine, job_name=JOB_NAME, target_date=TARGET_DATE)
    claim_run(engine, run_id)

    assert has_processing_lock(engine, job_name=JOB_NAME) is True

    finalize_run(engine, run_id, status="failed", error_message="boom")

    assert has_processing_lock(engine, job_name=JOB_NAME) is False


def test_has_completed_for_date_only_matches_completed(engine):
    completed = create_run(engine, job_name=JOB_NAME, target_date=TARGET_DATE)
    claim_run(engine, completed)
    finalize_run(engine, completed, status="completed")

    failed = create_run(engine, job_name=JOB_NAME, target_date=date(2026, 10, 30))
    claim_run(engine, failed)
    finalize_run(engine, failed, status="failed", error_message="boom")

    assert (
        has_completed_for_date(engine, job_name=JOB_NAME, target_date=TARGET_DATE)
        is True
    )
    assert (
        has_completed_for_date(engine, job_name=JOB_NAME, target_date=date(2026, 10, 30))
        is False
    )
    assert (
        has_completed_for_date(engine, job_name=JOB_NAME, target_date=date(2026, 10, 29))
        is False
    )
    assert (
        has_completed_for_date(engine, job_name="other_job", target_date=TARGET_DATE)
        is False
    )


def test_finalize_completed_sets_finished_at(engine):
    run_id = create_run(engine, job_name=JOB_NAME, target_date=TARGET_DATE)
    claim_run(engine, run_id)

    finalize_run(engine, run_id, status="completed")

    row = get_run(engine, run_id)
    assert row["status"] == "completed"
    assert row["finished_at"] is not None
    assert row["error_message"] is None


def test_finalize_failed_sets_error_message(engine):
    run_id = create_run(engine, job_name=JOB_NAME, target_date=TARGET_DATE)
    claim_run(engine, run_id)

    finalize_run(engine, run_id, status="failed", error_message="export exploded")

    row = get_run(engine, run_id)
    assert row["status"] == "failed"
    assert row["finished_at"] is not None
    assert row["error_message"] == "export exploded"


def test_finalize_rejects_non_terminal_status(engine):
    run_id = create_run(engine, job_name=JOB_NAME, target_date=TARGET_DATE)

    with pytest.raises(ValueError, match="Unsupported terminal status"):
        finalize_run(engine, run_id, status="processing")


def test_only_one_processing_row_per_job(engine):
    _insert_processing(engine)

    with pytest.raises(IntegrityError):
        _insert_processing(engine)

    assert _count(engine, status="processing") == 1


def test_recover_stale_runs_marks_only_stale(engine):
    from uuid import uuid4

    stale_started = datetime.now(timezone.utc) - timedelta(hours=7)
    stale_id = _insert_processing(engine, started_at=stale_started)
    other_id = _insert_processing(
        engine, job_name="other_job", started_at=stale_started
    )

    completed_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            job_runs.insert().values(
                id=completed_id,
                job_name="other_job",
                target_date=date(2026, 10, 28),
                status="completed",
                created_at=datetime.now(timezone.utc),
            )
        )

    assert recover_stale_runs(engine) == 1

    # The lock is released, so the same job can claim a new run afterwards.
    fresh = create_run(engine, job_name=JOB_NAME, target_date=date(2026, 10, 29))
    assert claim_run(engine, fresh) is True

    rows = {}
    with engine.connect() as connection:
        for row in connection.execute(select(job_runs)).mappings():
            rows[row["id"]] = row
    assert rows[stale_id]["status"] == "failed"
    assert (
        rows[stale_id]["error_message"]
        == "marked failed: stale processing lock"
    )
    assert rows[stale_id]["finished_at"] is not None
    assert rows[other_id]["status"] == "processing"
    assert rows[completed_id]["status"] == "completed"
    assert rows[fresh]["status"] == "processing"


def test_delete_run_only_removes_pending(engine):
    run_id = create_run(engine, job_name=JOB_NAME, target_date=TARGET_DATE)

    delete_run(engine, run_id)

    assert get_run(engine, run_id) is None


def test_delete_run_keeps_claimed_rows(engine):
    run_id = create_run(engine, job_name=JOB_NAME, target_date=TARGET_DATE)
    claim_run(engine, run_id)

    delete_run(engine, run_id)

    assert get_run(engine, run_id)["status"] == "processing"


def test_sanitize_error_truncates_and_handles_empty(engine):  # noqa: ARG001
    long_message = "x" * 500
    assert sanitize_error(RuntimeError(long_message)) == long_message[:300]

    class _SilentError(Exception):
        def __str__(self):
            return ""

    assert sanitize_error(_SilentError()) == "_SilentError"


def test_ensure_job_runs_table_is_idempotent(engine):
    ensure_job_runs_table(engine)
    ensure_job_runs_table(engine)

    assert _count(engine) == 0
