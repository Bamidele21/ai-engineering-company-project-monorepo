"""Async contract tests for the Nexova incident analyzer API.

The analyze endpoint no longer runs the analysis in the request cycle: it
stages the upload and returns ``202`` + ``task_id``, and the client polls
``GET /tasks/{task_id}``. These tests pin that wire contract: staging
behavior, the task-status mapping, the CSV export keyed by task id, and the
dead letter listing.

The analyzer is a standalone app root (``analyzer-api.py``), so it is loaded
by path. The Celery task is replaced with a fake so enqueueing never touches
Redis, and the result backend is faked so status lookups are deterministic.
"""

import importlib.util
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[4]
BACKROOMS_ROOT = REPO_ROOT / "backrooms"
for candidate in (REPO_ROOT, BACKROOMS_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

os.environ.setdefault("DATABASE_URL", "sqlite://")

ANALYZER_PATH = BACKROOMS_ROOT / "services" / "APIs" / "analyzer-api.py"
_spec = importlib.util.spec_from_file_location("analyzer_api", ANALYZER_PATH)
analyzer_api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(analyzer_api)

HEADER = (
    "ticket_id,date,client_company,category,description,"
    "agent_id,status,customer_email,satisfaction_score\n"
)
VALID_ROW = "1,2025-01-01,Acme,TECHNICAL,Printer issue,AGT-01,CLOSED,user@acme.com,5\n"


def _upload(client, content: str):
    return client.post(
        "/api/incidents/analyze",
        files={"file": ("incidents.csv", content, "text/csv")},
    )


@pytest.fixture()
def uploads_dir(tmp_path, monkeypatch):
    """Point the staging directory at an isolated temporary folder."""
    monkeypatch.setattr(analyzer_api, "UPLOAD_DIR", tmp_path)
    return tmp_path


@pytest.fixture()
def fake_task(monkeypatch):
    """Replace the Celery task so enqueueing never touches Redis."""
    calls = []

    class FakeTask:
        @staticmethod
        def apply_async(args=None, task_id=None, **kwargs):
            calls.append({"args": args, "task_id": task_id})

    monkeypatch.setattr(analyzer_api, "analyze_incident_csv", FakeTask())
    return calls


@pytest.fixture()
def client(uploads_dir, fake_task):
    with TestClient(analyzer_api.app) as test_client:
        yield test_client


class FakeResult:
    """Stands in for ``celery.result.AsyncResult`` in status lookups."""

    def __init__(self, state: str, result=None):
        self.state = state
        self.result = result


@pytest.fixture()
def fake_async_result(monkeypatch):
    """Replace the result backend lookup with a dict keyed by task id."""
    states = {}

    class FakeApp:
        @staticmethod
        def AsyncResult(task_id):
            return states.get(task_id, FakeResult("PENDING"))

    monkeypatch.setattr(analyzer_api, "celery_app", FakeApp())
    return states


# --- Happy path -------------------------------------------------------------


def test_analyze_returns_202_with_task_id_and_stages_the_file(client, fake_task, uploads_dir):
    response = _upload(client, HEADER + VALID_ROW)
    assert response.status_code == 202

    body = response.json()
    assert set(body) == {"task_id", "status"}
    assert body["status"] == "pending"
    task_id = body["task_id"]
    assert task_id

    # Exactly one task was enqueued, under the returned id.
    assert len(fake_task) == 1
    call = fake_task[0]
    assert call["task_id"] == task_id
    path_arg, original_name = call["args"]
    staged = uploads_dir / f"{task_id}.csv"
    assert Path(path_arg) == staged
    assert original_name == "incidents.csv"

    # The message carries only the path — never the CSV contents.
    assert "Acme" not in " ".join(call["args"])
    assert staged.read_text(encoding="utf-8") == HEADER + VALID_ROW


def test_task_status_reports_success_with_result(client, fake_async_result):
    metrics = {"total": 1, "valid": 1, "invalid": 0, "average_score": 5.0}
    fake_async_result["t-success"] = FakeResult("SUCCESS", metrics)

    response = client.get("/tasks/t-success")
    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == "t-success"
    assert body["status"] == "success"
    assert body["result"] == metrics
    assert body["error"] is None


def test_export_streams_csv_for_a_completed_task(client, fake_async_result):
    metrics = {
        "total": 1,
        "valid": 1,
        "invalid": 0,
        "invalid_counts": {},
        "category_counts": {"TECHNICAL": 1},
        "status_counts": {"CLOSED": 1},
        "closed_count": 1,
        "scored_count": 1,
        "average_score": 5.0,
        "score_counts": {"5": 1},
    }
    fake_async_result["t-done"] = FakeResult("SUCCESS", metrics)

    response = client.get(
        "/api/incidents/results/export", params={"task_id": "t-done"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert response.text.splitlines()[0] == "metric,value"
    assert "total_records" in response.text
    assert "satisfaction_score_5,1" in response.text


# --- Edge cases -------------------------------------------------------------


def test_task_status_reports_started(client, fake_async_result):
    fake_async_result["t-started"] = FakeResult("STARTED", None)
    body = client.get("/tasks/t-started").json()
    assert body["status"] == "started"
    assert body["result"] is None


def test_task_status_reports_pending_for_unknown_ids(client, fake_async_result):
    body = client.get("/tasks/never-enqueued").json()
    assert body["status"] == "pending"
    assert body["result"] is None
    assert body["error"] is None


def test_task_status_reports_pending_while_awaiting_retry(client, fake_async_result):
    fake_async_result["t-retry"] = FakeResult("RETRY", None)
    body = client.get("/tasks/t-retry").json()
    assert body["status"] == "pending"


def test_export_requires_a_task_id(client, fake_async_result):
    response = client.get("/api/incidents/results/export")
    assert response.status_code == 422


# --- Failure paths ----------------------------------------------------------


def test_analyze_rejects_empty_file_without_enqueueing(client, fake_task):
    response = _upload(client, "   \n")
    assert response.status_code == 400
    assert response.json()["detail"] == "The uploaded CSV file is empty."
    assert fake_task == []


def test_analyze_rejects_oversized_file_without_enqueueing(client, fake_task):
    response = _upload(client, "a" * (10 * 1024 * 1024 + 1))
    assert response.status_code == 413
    assert fake_task == []


def test_task_status_reports_failure_with_error(client, fake_async_result):
    fake_async_result["t-failed"] = FakeResult(
        "FAILURE", "InvalidCsvError('The uploaded file is not a valid UTF-8 incident CSV')"
    )
    body = client.get("/tasks/t-failed").json()
    assert body["status"] == "failure"
    assert "InvalidCsvError" in body["error"]


def test_export_conflicts_while_the_task_is_still_running(client, fake_async_result):
    fake_async_result["t-running"] = FakeResult("STARTED", None)
    response = client.get(
        "/api/incidents/results/export", params={"task_id": "t-running"}
    )
    assert response.status_code == 409


def test_export_reports_a_failed_analysis(client, fake_async_result):
    fake_async_result["t-failed"] = FakeResult("FAILURE", "boom")
    response = client.get(
        "/api/incidents/results/export", params={"task_id": "t-failed"}
    )
    assert response.status_code == 422
    assert "boom" in response.json()["detail"]


# --- Dead letter listing ----------------------------------------------------


def test_dead_letter_listing_returns_recorded_failures(client, monkeypatch):
    rows = [
        {
            "task_id": "t-dead",
            "task_name": "nexova.analyze_incident_csv",
            "attempt": 4,
            "error_message": "FileNotFoundError: staged file missing",
            "created_at": datetime(2026, 11, 18, tzinfo=timezone.utc),
        }
    ]
    monkeypatch.setattr(analyzer_api.storage, "list_dead_letter", lambda: rows)

    response = client.get("/tasks/dead-letter")
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["task_id"] == "t-dead"
    assert entries[0]["attempt"] == 4


def test_dead_letter_listing_returns_503_when_storage_is_missing(client, monkeypatch):
    def unavailable():
        raise analyzer_api.storage.DeadLetterStorageUnavailableError("nope")

    monkeypatch.setattr(analyzer_api.storage, "list_dead_letter", unavailable)
    response = client.get("/tasks/dead-letter")
    assert response.status_code == 503
