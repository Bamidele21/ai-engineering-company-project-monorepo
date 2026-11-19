"""Behavior tests for the standalone nightly export script.

The script is loaded by file path (``scripts/`` is not a package) and its
module globals are monkeypatched so every test runs against the in-memory
SQLite engine with a temporary ``data/raw`` directory and a recorded pipeline
trigger.
"""

import csv
import importlib.util
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.job_runner.service import JOB_NAME  # noqa: E402
from services.job_runner.storage import job_runs  # noqa: E402
from services.telemetry.storage import telemetry_events_table  # noqa: E402

_SCRIPT_PATH = REPO_ROOT / "scripts" / "nightly_export.py"
_spec = importlib.util.spec_from_file_location("nightly_export", _SCRIPT_PATH)
nightly = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(nightly)

TARGET_ISO = "2026-11-01"
TARGET_DATE = date(2026, 11, 1)


class _FakeResult:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _PipelineRecorder:
    def __init__(self):
        self.calls = 0
        self.returncode = 0
        self.stderr = ""

    def __call__(self):
        self.calls += 1
        return _FakeResult(self.returncode, stderr=self.stderr)


@pytest.fixture()
def pipeline_recorder(monkeypatch):
    recorder = _PipelineRecorder()
    monkeypatch.setattr(nightly, "trigger_pipeline", recorder)
    return recorder


@pytest.fixture()
def raw_dir(tmp_path, monkeypatch, engine, pipeline_recorder):
    """Bind the script to the isolated engine and a temporary raw directory."""
    monkeypatch.setattr(nightly, "get_engine", lambda: engine)
    monkeypatch.setattr(nightly, "dispose_engine", lambda: None)
    monkeypatch.setattr(nightly, "DATA_RAW_DIR", tmp_path / "data" / "raw")
    monkeypatch.setattr(nightly, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("TARGET_DATE", TARGET_ISO)
    return tmp_path / "data" / "raw"


def _insert_telemetry_event(engine, *, timestamp, event_type="page_view", tags=None):
    with engine.begin() as connection:
        connection.execute(
            telemetry_events_table.insert().values(
                id=uuid4(),
                timestamp=timestamp,
                service="backoffice",
                event_type=event_type,
                level="info",
                value=None,
                message=None,
                tags=tags or {},
            )
        )


def _insert_job_run(engine, *, status, target_date=TARGET_DATE, started_at=None):
    with engine.begin() as connection:
        connection.execute(
            job_runs.insert().values(
                id=uuid4(),
                job_name=JOB_NAME,
                target_date=target_date,
                status=status,
                started_at=started_at,
                finished_at=None,
                error_message=None,
                created_at=datetime.now(timezone.utc),
            )
        )


def _jobs(engine):
    with engine.connect() as connection:
        return list(connection.execute(select(job_runs)).mappings())


def _job_count(engine, status=None):
    query = select(func.count()).select_from(job_runs)
    if status is not None:
        query = query.where(job_runs.c.status == status)
    with engine.connect() as connection:
        return connection.execute(query).scalar_one()


def test_resolve_target_date_defaults_to_yesterday_utc(monkeypatch):
    monkeypatch.delenv("TARGET_DATE", raising=False)

    resolved = nightly.resolve_target_date(
        now=datetime(2026, 11, 2, 2, 30, tzinfo=timezone.utc)
    )

    assert resolved == date(2026, 11, 1)


def test_resolve_target_date_env_override(monkeypatch):
    monkeypatch.setenv("TARGET_DATE", "2026-10-25")

    assert nightly.resolve_target_date() == date(2026, 10, 25)


def test_invalid_target_date_exits_2(raw_dir, monkeypatch, engine, pipeline_recorder):
    monkeypatch.setenv("TARGET_DATE", "not-a-date")

    assert nightly.main() == 2
    assert pipeline_recorder.calls == 0
    assert _job_count(engine) == 0
    assert list(raw_dir.glob("*")) == []


def test_duplicate_completed_run_is_skipped(raw_dir, engine, pipeline_recorder):
    _insert_job_run(engine, status="completed")

    assert nightly.main() == 0

    assert pipeline_recorder.calls == 0
    assert _job_count(engine) == 1
    assert not (raw_dir / f"telemetry_{TARGET_ISO}.csv").exists()


def test_processing_lock_aborts_silently(raw_dir, engine, pipeline_recorder):
    _insert_job_run(engine, status="processing", started_at=datetime.now(timezone.utc))

    assert nightly.main() == 0

    assert pipeline_recorder.calls == 0
    assert _job_count(engine) == 1
    assert _jobs(engine)[0]["status"] == "processing"
    assert not (raw_dir / f"telemetry_{TARGET_ISO}.csv").exists()


def test_stale_processing_row_is_recovered_then_run_completes(
    raw_dir, engine, pipeline_recorder
):
    _insert_job_run(
        engine,
        status="processing",
        target_date=date(2026, 10, 30),
        started_at=datetime.now(timezone.utc) - timedelta(hours=7),
    )

    assert nightly.main() == 0

    rows = {row["target_date"]: row for row in _jobs(engine)}
    assert rows[date(2026, 10, 30)]["status"] == "failed"
    assert (
        rows[date(2026, 10, 30)]["error_message"]
        == "marked failed: stale processing lock"
    )
    assert rows[TARGET_DATE]["status"] == "completed"
    assert pipeline_recorder.calls == 1
    assert (raw_dir / f"telemetry_{TARGET_ISO}.csv").exists()


def test_success_exports_csv_and_records_completed(raw_dir, engine, pipeline_recorder):
    first_id = uuid4()
    second_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            telemetry_events_table.insert().values(
                id=first_id,
                timestamp=datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc),
                service="backoffice",
                event_type="page_view",
                level="info",
                value=None,
                message=None,
                tags={"_meta": {"eventId": "e1"}, "page": "/login"},
            )
        )
        connection.execute(
            telemetry_events_table.insert().values(
                id=second_id,
                timestamp=datetime(2026, 11, 1, 23, 59, 59, tzinfo=timezone.utc),
                service="inventory-api",
                event_type="inbound_order_created",
                level="info",
                value=12.5,
                message="order received",
                tags={},
            )
        )
        connection.execute(
            telemetry_events_table.insert().values(
                id=uuid4(),
                timestamp=datetime(2026, 10, 31, 23, 59, 59, tzinfo=timezone.utc),
                service="backoffice",
                event_type="page_view",
                level="info",
                value=None,
                message=None,
                tags={},
            )
        )
        connection.execute(
            telemetry_events_table.insert().values(
                id=uuid4(),
                timestamp=datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc),
                service="backoffice",
                event_type="page_view",
                level="info",
                value=None,
                message=None,
                tags={},
            )
        )

    assert nightly.main() == 0

    csv_path = raw_dir / f"telemetry_{TARGET_ISO}.csv"
    assert csv_path.exists()
    with csv_path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    assert list(rows[0].keys()) == list(nightly.CSV_COLUMNS)
    assert len(rows) == 2
    # SQLite persists UUIDs as 32-character hex.
    assert [row["id"] for row in rows] == [first_id.hex, second_id.hex]
    assert rows[0]["timestamp"].startswith("2026-11-01T00:00:00")
    assert rows[1]["timestamp"].startswith("2026-11-01T23:59:59")
    assert rows[0]["event_type"] == "page_view"
    assert rows[1]["event_type"] == "inbound_order_created"
    assert json.loads(rows[0]["tags"]) == {"_meta": {"eventId": "e1"}, "page": "/login"}
    assert json.loads(rows[1]["tags"]) == {}
    assert rows[1]["message"] == "order received"

    assert pipeline_recorder.calls == 1
    completed = _jobs(engine)[0]
    assert completed["status"] == "completed"
    assert completed["target_date"] == TARGET_DATE
    assert completed["started_at"] is not None
    assert completed["finished_at"] is not None
    assert _job_count(engine, status="processing") == 0
    assert list(raw_dir.glob("*.tmp")) == []


def test_existing_csv_skips_export_but_still_triggers_pipeline(
    raw_dir, engine, pipeline_recorder
):
    csv_path = raw_dir / f"telemetry_{TARGET_ISO}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text("sentinel\n", encoding="utf-8")
    _insert_telemetry_event(
        engine, timestamp=datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    )

    assert nightly.main() == 0

    assert csv_path.read_text(encoding="utf-8") == "sentinel\n"
    assert pipeline_recorder.calls == 1
    assert _jobs(engine)[0]["status"] == "completed"


def test_pipeline_nonzero_exit_marks_failed_and_raises(
    raw_dir, engine, pipeline_recorder
):
    pipeline_recorder.returncode = 1
    pipeline_recorder.stderr = "boom"
    _insert_telemetry_event(
        engine, timestamp=datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    )

    with pytest.raises(RuntimeError, match="pipeline exited with code 1"):
        nightly.main()

    rows = _jobs(engine)
    assert len(rows) == 1
    assert rows[0]["status"] == "failed"
    assert "boom" in rows[0]["error_message"]
    assert rows[0]["finished_at"] is not None
    assert _job_count(engine, status="processing") == 0


def test_export_exception_marks_failed_and_raises(raw_dir, engine, pipeline_recorder, monkeypatch):
    def _raiser(*args, **kwargs):
        raise ValueError("csv failed")

    monkeypatch.setattr(nightly, "export_csv", _raiser)
    _insert_telemetry_event(
        engine, timestamp=datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    )

    with pytest.raises(ValueError, match="csv failed"):
        nightly.main()

    rows = _jobs(engine)
    assert len(rows) == 1
    assert rows[0]["status"] == "failed"
    assert rows[0]["error_message"] == "csv failed"
    assert pipeline_recorder.calls == 0
    assert _job_count(engine, status="processing") == 0


def test_claim_race_aborts_silently(raw_dir, engine, pipeline_recorder, monkeypatch):
    monkeypatch.setattr(
        nightly, "has_processing_lock", lambda engine, *, job_name: False
    )
    _insert_job_run(engine, status="processing", started_at=datetime.now(timezone.utc))

    assert nightly.main() == 0

    assert pipeline_recorder.calls == 0
    assert _job_count(engine) == 1
    assert _job_count(engine, status="processing") == 1
    assert _job_count(engine, status="pending") == 0


def test_trigger_pipeline_builds_cli_command(tmp_path, monkeypatch):
    calls = {}

    def _fake_run(args, **kwargs):
        calls["args"] = list(args)
        calls["kwargs"] = kwargs
        return _FakeResult(0, stdout="{}")

    monkeypatch.setattr(nightly.subprocess, "run", _fake_run)
    monkeypatch.setattr(nightly, "REPO_ROOT", tmp_path)

    result = nightly.trigger_pipeline()

    assert result.returncode == 0
    assert calls["args"][0] == sys.executable
    assert calls["args"][1] == "data/pipelines/pipeline.py"
    assert calls["kwargs"]["cwd"] == tmp_path
    assert calls["kwargs"]["capture_output"] is True
    assert calls["kwargs"]["text"] is True
