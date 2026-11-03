"""Nightly telemetry export for Nexova (ticket DEV-53).

Standalone cron entry point. Run from the repository root:

    python scripts/nightly_export.py

For the previous UTC calendar day it (1) exports ``telemetry_events`` rows to
``data/raw/telemetry_YYYY-MM-DD.csv`` when the file does not exist yet,
(2) triggers the weekly ETL pipeline as a subprocess, and (3) records the
execution in ``reporting.job_runs`` following the state machine
``pending -> processing -> completed | failed``.

The ``processing`` status is the distributed lock: a second simultaneous
instance aborts silently. A completed row for ``(job_name, target_date)``
makes the run idempotent. ``TARGET_DATE=YYYY-MM-DD`` overrides the target
date for testing without code changes.

This script never imports FastAPI code and never shares the API's threads.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import subprocess
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKROOMS_ROOT = REPO_ROOT / "backrooms"
for _root in (REPO_ROOT, BACKROOMS_ROOT):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from dotenv import load_dotenv  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from services.job_runner.service import (  # noqa: E402
    JOB_NAME,
    claim_run,
    create_run,
    delete_run,
    finalize_run,
    has_completed_for_date,
    has_processing_lock,
    recover_stale_runs,
    sanitize_error,
)
from services.job_runner.storage import ensure_job_runs_table  # noqa: E402

logger = logging.getLogger("nexova.nightly")

ENV_FILES = (
    REPO_ROOT / ".env",
    REPO_ROOT / "backrooms" / "services" / "Inventory-API" / ".env",
)
DATA_RAW_DIR = REPO_ROOT / "data" / "raw"
CSV_COLUMNS = ("id", "timestamp", "service", "event_type", "level", "value", "message", "tags")
PIPELINE_SCRIPT = "data/pipelines/pipeline.py"
STDERR_TAIL_LIMIT = 2000

_environment_loaded = False
_engine: Engine | None = None


def load_environment() -> None:
    """Load the repo and Inventory API dotenv files once, without overriding."""
    global _environment_loaded
    if _environment_loaded:
        return
    for path in ENV_FILES:
        if path.is_file():
            load_dotenv(path, override=False)
    _environment_loaded = True


def _with_psycopg2_driver(raw_url: str) -> str:
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if raw_url.startswith("postgres://"):
        return raw_url.replace("postgres://", "postgresql+psycopg2://", 1)
    return raw_url


def database_url() -> str:
    load_environment()
    raw_url = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_URL")
    if not raw_url:
        raise RuntimeError("DATABASE_URL must be configured for the nightly export")
    return _with_psycopg2_driver(raw_url)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(database_url(), pool_pre_ping=True)
    return _engine


def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


def resolve_target_date(now: datetime | None = None) -> date | None:
    """Return ``TARGET_DATE`` when set, else the previous UTC calendar day."""
    override = os.getenv("TARGET_DATE")
    if override:
        try:
            return date.fromisoformat(override)
        except ValueError:
            logger.error(
                "nightly_export [failed] invalid TARGET_DATE=%r; expected YYYY-MM-DD",
                override,
            )
            return None
    return ((now or datetime.now(timezone.utc)).date() - timedelta(days=1))


def _iso_timestamp(value: Any) -> str:
    """Serialize a source timestamp as aware UTC (same contract as extract.py)."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, str):
        text_value = value.strip()
        try:
            parsed = datetime.fromisoformat(text_value)
        except ValueError:
            return text_value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    return str(value)


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return json.dumps(value)
    return str(value)


def export_csv(engine: Engine, target_date: date, csv_path: Path) -> int:
    """Write the target day's telemetry rows to ``csv_path`` atomically.

    Uses the same half-open UTC window as the ETL extract query. Returns the
    number of exported rows.
    """
    window_start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    window_end = window_start + timedelta(days=1)
    table_prefix = "public." if engine.dialect.name == "postgresql" else ""
    query = text(
        f"SELECT id, timestamp, service, event_type, level, value, message, tags "
        f"FROM {table_prefix}telemetry_events "
        "WHERE timestamp >= :start AND timestamp < :end "
        "ORDER BY timestamp ASC, id ASC"
    )
    temporary_path = csv_path.with_name(csv_path.name + ".tmp")
    count = 0
    with temporary_path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.writer(destination)
        writer.writerow(CSV_COLUMNS)
        with engine.connect().execution_options(
            stream_results=True
        ) as connection:
            for row in connection.execute(
                query, {"start": window_start, "end": window_end}
            ).mappings():
                writer.writerow(
                    [
                        str(row["id"]) if row["id"] is not None else "",
                        _iso_timestamp(row["timestamp"]),
                        _csv_cell(row["service"]),
                        _csv_cell(row["event_type"]),
                        _csv_cell(row["level"]),
                        _csv_cell(row["value"]),
                        _csv_cell(row["message"]),
                        _csv_cell(row["tags"]),
                    ]
                )
                count += 1
    os.replace(temporary_path, csv_path)
    return count


def trigger_pipeline() -> subprocess.CompletedProcess[str]:
    """Run the weekly ETL pipeline as a child process and return its result."""
    return subprocess.run(
        [sys.executable, PIPELINE_SCRIPT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001 - CLI parity
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    target_date = resolve_target_date()
    if target_date is None:
        return 2

    run_id = None
    try:
        engine = get_engine()
        ensure_job_runs_table(engine)

        recovered = recover_stale_runs(engine)
        if recovered:
            logger.warning(
                "nightly_export [recovered] marked %d stale processing run(s) failed",
                recovered,
            )

        if has_completed_for_date(engine, job_name=JOB_NAME, target_date=target_date):
            logger.info(
                "nightly_export [skipped] already completed for %s",
                target_date.isoformat(),
            )
            return 0

        if has_processing_lock(engine, job_name=JOB_NAME):
            logger.info(
                "nightly_export [aborted] another instance is processing; "
                "target date %s",
                target_date.isoformat(),
            )
            return 0

        run_id = create_run(engine, job_name=JOB_NAME, target_date=target_date)
        logger.info(
            "nightly_export [pending] run %s created for %s",
            run_id,
            target_date.isoformat(),
        )

        try:
            claimed = claim_run(engine, run_id)
        except IntegrityError:
            delete_run(engine, run_id)
            logger.info(
                "nightly_export [aborted] lost the processing-lock claim race for %s",
                target_date.isoformat(),
            )
            return 0
        if not claimed:
            delete_run(engine, run_id)
            logger.info(
                "nightly_export [aborted] run %s was already claimed", run_id
            )
            return 0
        logger.info("nightly_export [processing] run %s started", run_id)

        DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
        csv_path = DATA_RAW_DIR / f"telemetry_{target_date.isoformat()}.csv"
        if csv_path.exists():
            logger.info(
                "nightly_export [processing] CSV %s already exists, skipping export",
                csv_path.name,
            )
        else:
            row_count = export_csv(engine, target_date, csv_path)
            logger.info(
                "nightly_export [processing] exported %d row(s) to %s",
                row_count,
                csv_path.name,
            )

        completed = trigger_pipeline()
        if completed.returncode != 0:
            stderr_tail = (completed.stderr or "").strip()[-STDERR_TAIL_LIMIT:]
            raise RuntimeError(
                f"pipeline exited with code {completed.returncode}: {stderr_tail}"
            )
        logger.info(
            "nightly_export [processing] pipeline trigger finished (exit 0)"
        )

        finalize_run(engine, run_id, status="completed")
        logger.info(
            "nightly_export [completed] run %s for %s",
            run_id,
            target_date.isoformat(),
        )
        return 0
    except BaseException as error:  # noqa: BLE001 - includes KeyboardInterrupt
        message = sanitize_error(error)
        if run_id is not None:
            try:
                finalize_run(engine, run_id, status="failed", error_message=message)
            except Exception:  # noqa: BLE001 - persistence must never mask the cause
                logger.exception(
                    "nightly_export [failed] could not persist the failed status"
                )
        logger.error(
            "nightly_export [failed] run %s for %s: %s",
            run_id,
            target_date.isoformat(),
            message,
        )
        raise
    finally:
        dispose_engine()


if __name__ == "__main__":
    raise SystemExit(main())
