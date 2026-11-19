"""FastAPI endpoints for the Nexova incident CSV analyzer.

The CSV analysis is the slowest operation in this API: parsing and validating
up to 10 MB of support records used to run inside the request cycle. Since
the async-tasks milestone it is produced/consumed through Celery:

- ``POST /api/incidents/analyze`` stages the upload on disk and enqueues the
  task, returning ``202 Accepted`` with a ``task_id`` immediately. The
  message carries only the staged file path, never the file contents.
- ``GET /tasks/{task_id}`` reads the task status and result from Redis.
- ``GET /api/incidents/results/export?task_id=...`` streams the CSV export of
  a completed analysis.
- ``GET /tasks/dead-letter`` lists tasks that exhausted their retries.
"""

import csv
import io
import logging
import os
import sys
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from dotenv import load_dotenv

# Host development: read REDIS_URL/DATABASE_URL from the repo-root .env.
# No-op inside Docker Compose, where the environment is already injected.
load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKROOMS_ROOT = Path(__file__).resolve().parents[2]
for candidate in (PROJECT_ROOT, BACKROOMS_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from scripts.CSV_analyzer.analyze import metric_rows

from services.task_queue import storage
from services.task_queue.celery_app import celery_app
from services.task_queue.tasks import analyze_incident_csv

logger = logging.getLogger(__name__)
allowed_origins = [origin.strip() for origin in os.getenv("ANALYZER_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001").split(",") if origin.strip()]

MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# Shared with the Celery worker (named volume in Docker Compose): the API
# writes the staged CSV here and the worker reads it back. The default keeps
# host development self-contained inside the APIs folder.
UPLOAD_DIR = Path(os.getenv("ANALYZER_UPLOAD_DIR") or (Path(__file__).resolve().parent / "uploads"))

# Celery states surfaced by GET /tasks/{task_id}. Anything unknown (including
# a task id that never existed) is reported as pending.
STATE_TO_STATUS = {
    "PENDING": "pending",
    "RECEIVED": "pending",
    "RETRY": "pending",
    "STARTED": "started",
    "SUCCESS": "success",
    "FAILURE": "failure",
    "REVOKED": "failure",
}


class AnalyzeAcceptedResponse(BaseModel):
    """Returned by ``POST /api/incidents/analyze``: the client polls status."""

    task_id: str
    status: str


class TaskStatusResponse(BaseModel):
    """Status of one queued task, read from the Celery result backend."""

    task_id: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None


class DeadLetterEntry(BaseModel):
    task_id: str
    task_name: str
    attempt: int
    error_message: str
    created_at: datetime


class DeadLetterResponse(BaseModel):
    entries: list[DeadLetterEntry]


@asynccontextmanager
async def lifespan(app: FastAPI):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    try:
        storage.ensure_dead_letter_table()
    except Exception:  # noqa: BLE001 - the API must start even without a DB
        logger.warning(
            "dead letter storage unavailable; /tasks/dead-letter will return 503"
        )
    yield


app = FastAPI(title="Nexova Incident Analyzer API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def _error_message(value: Any) -> str:
    """Normalize whatever the result backend stored for a failed task."""
    if value is None:
        return "Task failed"
    if isinstance(value, BaseException):
        return f"{type(value).__name__}: {value}"
    if isinstance(value, dict):
        exc_type = value.get("exc_type")
        if exc_type:
            exc_message = value.get("exc_message")
            if isinstance(exc_message, (list, tuple)):
                exc_message = " ".join(str(part) for part in exc_message)
            return f"{exc_type}: {exc_message}"
        return str(value)
    return str(value)


@app.post("/api/incidents/analyze", response_model=AnalyzeAcceptedResponse, status_code=202)
async def analyze_incidents(file: UploadFile = File(...)) -> AnalyzeAcceptedResponse:
    """Stage an incident CSV and enqueue its analysis; return ``task_id``.

    The request returns immediately after the file is written to the shared
    upload directory and the task message is deposited in Redis — it never
    waits for the analysis itself. ``GET /tasks/{task_id}`` reports progress.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="A CSV file is required.")

    try:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
    except Exception as error:
        logger.exception("Failed to read the uploaded incident CSV")
        raise HTTPException(
            status_code=400,
            detail="The uploaded file could not be read.",
        ) from error

    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="The uploaded file is too large. The maximum size is 10 MB.",
        )

    if not content.strip():
        raise HTTPException(status_code=400, detail="The uploaded CSV file is empty.")

    # The staged filename mirrors the task id so files and tasks can be
    # correlated on disk, in the queue, and in the result backend.
    task_id = str(uuid4())
    staged_path = UPLOAD_DIR / f"{task_id}.csv"
    try:
        staged_path.write_bytes(content)
    except OSError as error:
        logger.exception("Failed to stage the uploaded incident CSV")
        raise HTTPException(
            status_code=503,
            detail="The uploaded file could not be staged for analysis.",
        ) from error

    # The message carries only identifiers and the path — never the CSV
    # contents — per the producer/consumer rules.
    analyze_incident_csv.apply_async(
        args=[str(staged_path), file.filename],
        task_id=task_id,
    )
    logger.info(
        "task enqueued task_id=%s file=%s bytes=%d",
        task_id,
        file.filename,
        len(content),
    )
    return AnalyzeAcceptedResponse(task_id=task_id, status="pending")


@app.get("/tasks/dead-letter", response_model=DeadLetterResponse)
def dead_letter_tasks() -> DeadLetterResponse:
    """List tasks that exhausted their retries, newest first."""
    try:
        entries = storage.list_dead_letter()
    except storage.DeadLetterStorageUnavailableError as error:
        raise HTTPException(
            status_code=503, detail="Dead letter storage is not configured."
        ) from error
    except Exception as error:  # noqa: BLE001 - translated to a typed HTTP error
        logger.exception("Could not read the dead letter queue")
        raise HTTPException(
            status_code=500, detail="Dead letter storage is unavailable."
        ) from error
    return DeadLetterResponse(
        entries=[DeadLetterEntry(**entry) for entry in entries]
    )


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def task_status(task_id: str) -> TaskStatusResponse:
    """Return the current state of a queued task from the result backend.

    Statuses: ``pending`` (queued, received, or awaiting retry), ``started``
    (a worker picked it up), ``success`` (result attached), ``failure``
    (error attached). Unknown ids report ``pending``, matching Celery's own
    behavior for results that were never stored.
    """
    async_result = celery_app.AsyncResult(task_id)
    state = async_result.state
    status = STATE_TO_STATUS.get(state, "pending")
    payload = TaskStatusResponse(task_id=task_id, status=status)
    if state == "SUCCESS":
        payload.result = async_result.result
    elif state == "FAILURE":
        payload.error = _error_message(async_result.result)
    return payload


@app.get(
    "/api/incidents/results/export",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/csv": {}},
            "description": "Aggregate metrics from one completed analysis as CSV.",
        }
    },
)
def export_analysis(task_id: str = Query(..., description="The task id returned by POST /api/incidents/analyze")) -> StreamingResponse:
    """Download aggregate metrics from a completed analysis.

    Documented ``response_model`` exception: this route streams a CSV file
    rather than a JSON body, so no Pydantic response schema applies.
    """
    async_result = celery_app.AsyncResult(task_id)
    state = async_result.state
    if state == "FAILURE":
        raise HTTPException(
            status_code=422,
            detail=f"The analysis failed: {_error_message(async_result.result)}",
        )
    if state != "SUCCESS":
        raise HTTPException(
            status_code=409,
            detail="The analysis is not complete yet. Poll GET /tasks/{task_id} until it succeeds.",
        )

    metrics = async_result.result
    # The JSON result stores plain dicts; ``metric_rows`` indexes them with
    # Counter semantics (missing keys count as zero), so reconstruct counters
    # at the serialization boundary.
    exportable = {
        **metrics,
        "invalid_counts": Counter(metrics.get("invalid_counts") or {}),
        "category_counts": Counter(metrics.get("category_counts") or {}),
        "status_counts": Counter(metrics.get("status_counts") or {}),
        "score_counts": Counter(
            {int(score): count for score, count in (metrics.get("score_counts") or {}).items()}
        ),
    }
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("metric", "value"))
    writer.writerows(metric_rows(exportable))
    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=results.csv"},
    )
