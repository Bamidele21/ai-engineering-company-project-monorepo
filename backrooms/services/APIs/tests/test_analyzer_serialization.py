"""Serialization tests for the Nexova incident analyzer API.

The analyzer is a standalone app root (``analyzer-api.py``), so it is loaded by
path. These tests pin the wire contract: the analyze response exposes only the
fields the UI reads (``score_counts`` stays internal), and the CSV export is a
documented non-JSON response.
"""

import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[4]
ANALYZER_PATH = REPO_ROOT / "backrooms" / "services" / "APIs" / "analyzer-api.py"

_spec = importlib.util.spec_from_file_location("analyzer_api", ANALYZER_PATH)
analyzer_api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(analyzer_api)

HEADER = (
    "ticket_id,date,client_company,category,description,"
    "agent_id,status,customer_email,satisfaction_score\n"
)
VALID_ROW = "1,2025-01-01,Acme,TECHNICAL,Printer issue,AGT-01,CLOSED,user@acme.com,5\n"


@pytest.fixture(autouse=True)
def reset_last_metrics():
    """Keep the module-level ``_last_metrics`` global isolated per test."""
    analyzer_api._last_metrics = None
    yield
    analyzer_api._last_metrics = None


@pytest.fixture()
def client():
    return TestClient(analyzer_api.app)


def _upload(client, content: str):
    return client.post(
        "/api/incidents/analyze",
        files={"file": ("incidents.csv", content, "text/csv")},
    )


EXPECTED_FIELDS = {
    "total",
    "valid",
    "invalid",
    "invalid_counts",
    "category_counts",
    "status_counts",
    "closed_count",
    "scored_count",
    "average_score",
}


# --- Happy path -------------------------------------------------------------


def test_analyze_returns_slim_serialized_payload(client):
    response = _upload(client, HEADER + VALID_ROW)
    assert response.status_code == 200

    body = response.json()
    assert set(body) == EXPECTED_FIELDS
    # score_counts is computed internally for the export but never returned.
    assert "score_counts" not in body
    assert body["total"] == 1
    assert body["valid"] == 1
    assert body["closed_count"] == 1
    assert body["average_score"] == 5.0


def test_export_streams_csv_after_analysis(client):
    _upload(client, HEADER + VALID_ROW)
    response = client.get("/api/incidents/results/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert response.text.splitlines()[0] == "metric,value"


# --- Failure / edge ---------------------------------------------------------


def test_analyze_rejects_csv_missing_required_columns(client):
    response = _upload(client, "ticket_id,date\n1,2025-01-01\n")
    assert response.status_code == 400
    assert response.json()["detail"] == "The uploaded file is not a valid CSV."


def test_analyze_rejects_empty_file(client):
    response = _upload(client, "   \n")
    assert response.status_code == 400
    assert response.json()["detail"] == "The uploaded CSV file is empty."


def test_export_without_prior_analysis_returns_404(client):
    response = client.get("/api/incidents/results/export")
    assert response.status_code == 404
