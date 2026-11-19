"""Celery tasks for the Nexova async task queue.

The single task in this first iteration is the incident CSV analysis, the
slowest synchronous operation in the request cycle before this milestone:
parsing and validating up to 10 MB of support records used to happen inside
the ``POST /api/incidents/analyze`` request itself.

Retry policy:

- ``OSError`` (the staged file could not be read, e.g. the shared volume was
  briefly unavailable) is retried automatically up to ``max_retries=3`` with
  exponential backoff (countdown doubles per attempt, capped at 30s, with
  jitter so no retry fires immediately).
- Validation errors (bad encoding, bad CSV structure) are permanent: retrying
  them could never succeed, so they fail on the first attempt.
- When the retries are exhausted, the failure is recorded in the dead letter
  queue (``task_queue.dead_letter_tasks``) with ``task_id``, attempt number,
  and the full error message.
"""

from __future__ import annotations

import csv
import logging
import time
from pathlib import Path
from typing import Any

from celery import signals

from . import storage
from .celery_app import celery_app

logger = logging.getLogger("nexova.tasks")


class InvalidCsvError(Exception):
    """Permanent failure: the staged file is not a valid UTF-8 incident CSV."""


def metrics_to_json(metrics: dict[str, Any]) -> dict[str, Any]:
    """Convert analyzer counters into JSON-serializable values.

    Mirrors the wire contract of the old synchronous analyze endpoint so the
    result backend returns exactly what the UI expects, plus ``score_counts``
    (score histogram keys as strings) which the CSV export needs.
    """
    return {
        "total": metrics["total"],
        "valid": metrics["valid"],
        "invalid": metrics["invalid"],
        "invalid_counts": dict(metrics["invalid_counts"]),
        "category_counts": dict(metrics["category_counts"]),
        "status_counts": dict(metrics["status_counts"]),
        "closed_count": metrics["closed_count"],
        "scored_count": metrics["scored_count"],
        "average_score": metrics["average_score"],
        "score_counts": {str(score): count for score, count in metrics["score_counts"].items()},
    }


def _remove_staged_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("could not remove staged CSV %s", path, exc_info=True)


def _record_dead_letter(
    *, task_id: str, task_name: str, attempt: int, error: Exception
) -> None:
    try:
        storage.record_dead_letter(
            task_id=str(task_id),
            task_name=task_name,
            attempt=attempt,
            error=f"{type(error).__name__}: {error}",
        )
        logger.error(
            "task moved to DLQ task_id=%s attempt=%d task_name=%s",
            task_id,
            attempt,
            task_name,
        )
    except Exception:  # noqa: BLE001 - DLQ persistence must never hide the task failure
        logger.exception("could not record DLQ entry for task_id=%s", task_id)


@celery_app.task(
    bind=True,
    name="nexova.analyze_incident_csv",
    max_retries=3,
    autoretry_for=(OSError,),
    retry_backoff=True,
    retry_backoff_max=30,
    retry_jitter=True,
)
def analyze_incident_csv(self, file_path: str, original_name: str) -> dict[str, Any]:
    """Validate and analyze a staged incident CSV export.

    The message carries only the staged file path (never the file contents);
    the worker reads the file itself. Returns the JSON-safe metrics dict that
    the UI consumes.
    """
    # The analyzer lives in repo-root ``scripts/``, which the producer
    # process does not need: only the worker imports it, and only when a
    # task actually runs.
    from scripts.CSV_analyzer.analyze import analyze_records, load_records

    task_id = str(self.request.id)
    attempt = self.request.retries + 1
    started = time.monotonic()
    path = Path(file_path)

    logger.info(
        "task started task_id=%s attempt=%d/%d file=%s original=%s",
        task_id,
        attempt,
        self.max_retries + 1,
        path.name,
        original_name,
    )

    try:
        records = load_records(path)
        metrics = analyze_records(records)
    except (UnicodeDecodeError, ValueError, csv.Error) as error:
        duration = time.monotonic() - started
        logger.error(
            "task failed task_id=%s attempt=%d status=failure duration=%.3fs "
            "error=%s: %s",
            task_id,
            attempt,
            duration,
            type(error).__name__,
            error,
        )
        _remove_staged_file(path)
        raise InvalidCsvError(
            "The uploaded file is not a valid UTF-8 incident CSV: "
            f"{type(error).__name__}: {error}"
        ) from error
    except OSError as error:
        duration = time.monotonic() - started
        if self.request.retries >= self.max_retries:
            logger.error(
                "task failed task_id=%s attempt=%d status=failure duration=%.3fs "
                "error=%s: %s",
                task_id,
                attempt,
                duration,
                type(error).__name__,
                error,
            )
            _record_dead_letter(
                task_id=task_id,
                task_name=self.name,
                attempt=attempt,
                error=error,
            )
            _remove_staged_file(path)
            raise
        logger.warning(
            "task failed task_id=%s attempt=%d status=retry duration=%.3fs "
            "error=%s: %s",
            task_id,
            attempt,
            duration,
            type(error).__name__,
            error,
        )
        raise

    duration = time.monotonic() - started
    result = metrics_to_json(metrics)
    logger.info(
        "task completed task_id=%s attempt=%d status=success duration=%.3fs "
        "records=%d valid=%d invalid=%d",
        task_id,
        attempt,
        duration,
        metrics["total"],
        metrics["valid"],
        metrics["invalid"],
    )
    _remove_staged_file(path)
    return result


@signals.worker_process_init.connect
def ensure_dead_letter_schema(*args: Any, **kwargs: Any) -> None:
    """Create the DLQ table in every worker process before it consumes."""
    try:
        storage.ensure_dead_letter_table()
    except Exception:  # noqa: BLE001 - the worker must start even without a DB
        logger.exception(
            "dead letter storage unavailable; exhausted tasks will not be recorded"
        )
