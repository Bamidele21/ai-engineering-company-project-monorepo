"""Behavioral tests for the incident CSV analysis task.

Happy / edge / failure tiers per the repo test-coverage rule:

- a valid CSV produces the expected metrics and the staged file is removed;
- a permanently-invalid CSV fails without retries and without a DLQ row;
- a transient read failure is retried with exponential backoff and moves to
  the dead letter queue only after the retries are exhausted.
"""

from pathlib import Path

import pytest

from services.task_queue import storage
from services.task_queue.tasks import InvalidCsvError, analyze_incident_csv

HEADER = (
    "ticket_id,date,client_company,category,description,"
    "agent_id,status,customer_email,satisfaction_score\n"
)
VALID_ROW = "1,2025-01-01,Acme,TECHNICAL,Printer issue,AGT-01,CLOSED,user@acme.com,5\n"
# Empty description -> invalid_description; every other field is valid.
INVALID_ROW = "2,2025-01-02,Globex,BILLING,,AGT-02,OPEN,user@globex.com,\n"


@pytest.fixture()
def valid_csv(tmp_path):
    path = tmp_path / "incidents.csv"
    path.write_text(HEADER + VALID_ROW, encoding="utf-8")
    return path


@pytest.fixture()
def dlq_engine(engine, monkeypatch):
    """Route the task's DLQ writes to the isolated test database."""
    monkeypatch.setattr(storage, "get_engine", lambda: engine)
    return engine


def _run(path: Path, name: str = "incidents.csv"):
    return analyze_incident_csv.apply(args=[str(path), name]).get()


# --- Happy path -------------------------------------------------------------


def test_valid_csv_produces_expected_metrics(valid_csv):
    result = _run(valid_csv)

    assert result["total"] == 1
    assert result["valid"] == 1
    assert result["invalid"] == 0
    assert result["invalid_counts"] == {}
    assert result["category_counts"] == {"TECHNICAL": 1}
    assert result["status_counts"] == {"CLOSED": 1}
    assert result["closed_count"] == 1
    assert result["scored_count"] == 1
    assert result["average_score"] == pytest.approx(5.0)
    assert result["score_counts"] == {"5": 1}


def test_staged_file_is_removed_after_success(valid_csv):
    _run(valid_csv)
    assert not valid_csv.exists()


# --- Edge cases -------------------------------------------------------------


def test_mixed_csv_reports_valid_and_invalid_records(tmp_path):
    path = tmp_path / "mixed.csv"
    path.write_text(HEADER + VALID_ROW + INVALID_ROW, encoding="utf-8")

    result = _run(path)

    assert result["total"] == 2
    assert result["valid"] == 1
    assert result["invalid"] == 1
    assert result["invalid_counts"] == {"invalid_description": 1}


# --- Failure paths ----------------------------------------------------------


def test_invalid_csv_fails_without_retries_or_dead_letter(tmp_path, dlq_engine):
    path = tmp_path / "broken.csv"
    path.write_text("ticket_id,date\n1,2025-01-01\n", encoding="utf-8")

    with pytest.raises(InvalidCsvError):
        _run(path)

    # A permanent failure is never retried, so it never reaches the DLQ.
    assert storage.list_dead_letter(engine=dlq_engine) == []
    assert not path.exists()


def test_non_utf8_csv_fails_permanently(tmp_path, dlq_engine):
    path = tmp_path / "latin.csv"
    path.write_bytes(b"ticket_id,date\n1,2025-01-01\xe9\n")

    with pytest.raises(InvalidCsvError):
        _run(path)

    assert storage.list_dead_letter(engine=dlq_engine) == []


def test_transient_read_failure_is_retried_then_moves_to_dead_letter(dlq_engine):
    from celery.exceptions import Retry

    missing = Path("staged-file-that-does-not-exist.csv")

    # Eager mode has no worker to redeliver, so ``Retry`` surfaces instead of
    # re-executing. Drive the three retried attempts explicitly, mirroring
    # the worker's redelivery cycle with the attempt counter.
    for retries in range(analyze_incident_csv.max_retries):
        with pytest.raises(Retry):
            analyze_incident_csv.apply(
                args=[str(missing), "incidents.csv"], retries=retries
            )

    # Nothing is dead-lettered while retries remain.
    assert storage.list_dead_letter(engine=dlq_engine) == []

    # The final attempt has no retries left: it fails and lands in the DLQ.
    with pytest.raises(OSError):
        analyze_incident_csv.apply(
            args=[str(missing), "incidents.csv"],
            retries=analyze_incident_csv.max_retries,
        )

    # Exactly one DLQ row with the task id, attempt number, error message,
    # and timestamp.
    rows = storage.list_dead_letter(engine=dlq_engine)
    assert len(rows) == 1
    row = rows[0]
    assert row["task_id"]
    assert row["task_name"] == "nexova.analyze_incident_csv"
    assert row["attempt"] == 4
    assert "FileNotFoundError" in row["error_message"]
    assert row["created_at"] is not None


# --- Retry policy -----------------------------------------------------------


def test_retry_policy_uses_exponential_backoff():
    assert analyze_incident_csv.max_retries == 3
    assert OSError in analyze_incident_csv.autoretry_for
    assert analyze_incident_csv.retry_backoff is True
    assert analyze_incident_csv.retry_backoff_max == 30
    assert analyze_incident_csv.retry_jitter is True


def test_every_task_has_a_time_limit():
    from services.task_queue.celery_app import celery_app

    assert celery_app.conf.task_soft_time_limit > 0
    assert celery_app.conf.task_time_limit > celery_app.conf.task_soft_time_limit
