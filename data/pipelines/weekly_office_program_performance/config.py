"""Runtime configuration for the weekly performance pipeline."""

from __future__ import annotations

import hashlib
import os
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

from data.process.weekly_performance.constants import (
    FLOW_NAME,
    PIPELINE_NAME,
    REJECTION_THRESHOLD,
    STALE_RUN_MINUTES,
    TRANSFORMATION_VERSION,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_DIR = Path(__file__).resolve().parents[1]
ENV_FILES = (
    REPO_ROOT / ".env",
    REPO_ROOT / "backrooms" / "services" / "Inventory-API" / ".env",
)

PREFECT_DEPLOYMENT_NAME = os.getenv(
    "PREFECT_DEPLOYMENT_NAME", "weekly-office-program-performance"
)
PREFECT_WORK_POOL = os.getenv("PREFECT_WORK_POOL", "nexova-data-pipelines")
PREFECT_API_URL_DEFAULT = "http://localhost:4200/api"

TRANSFORM_CACHE_EXPIRATION = timedelta(hours=1)
RETRY_DELAYS_SECONDS = [30, 120, 300]
RETRY_COUNT = 3
SNAPSHOT_DIRECTORY = REPO_ROOT / "data" / "eval" / "weekly_performance"

_REJECTION_THRESHOLD = Decimal(
    os.getenv("REPORTING_REJECTION_THRESHOLD", str(REJECTION_THRESHOLD))
)
_STALE_RUN_MINUTES = int(os.getenv("REPORTING_STALE_RUN_MINUTES", str(STALE_RUN_MINUTES)))

_environment_loaded = False


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
    raw_url = os.getenv("DATABASE_URL")
    if not raw_url:
        raise RuntimeError("DATABASE_URL must be configured for the reporting pipeline")
    return _with_psycopg2_driver(raw_url)


def session_mode_database_url() -> str | None:
    """Return a session-mode URL for the advisory lock.

    Supabase transaction pooling runs on port 6543 and does not preserve a
    session-level advisory lock. Session pooling is exposed on port 5432 of the
    same pooler host, so derive that URL when the configured URL uses 6543.
    """
    load_environment()
    url = make_url(database_url())
    if url.get_backend_name() != "postgresql":
        return None
    if (url.port or 5432) == 6543:
        url = url.set(port=5432)
    return url.render_as_string(hide_password=False)


def prefect_api_url() -> str:
    raw = os.getenv("PREFECT_API_URL", PREFECT_API_URL_DEFAULT)
    return raw.rstrip("/")


def prefect_deployment_name() -> str:
    return os.getenv("PREFECT_DEPLOYMENT_NAME", PREFECT_DEPLOYMENT_NAME)


def prefect_work_pool() -> str:
    return os.getenv("PREFECT_WORK_POOL", PREFECT_WORK_POOL)


def rejection_threshold() -> Decimal:
    return _REJECTION_THRESHOLD


def stale_run_minutes() -> int:
    return _STALE_RUN_MINUTES


def transformation_version() -> str:
    return TRANSFORMATION_VERSION


def advisory_lock_key() -> int:
    digest = hashlib.sha256(PIPELINE_NAME.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def snapshot_directory() -> Path:
    directory = Path(os.getenv("REPORTING_SNAPSHOT_DIR", SNAPSHOT_DIRECTORY))
    directory.mkdir(parents=True, exist_ok=True)
    return directory


__all__ = [
    "FLOW_NAME",
    "PIPELINE_NAME",
    "REPO_ROOT",
    "RETRY_COUNT",
    "RETRY_DELAYS_SECONDS",
    "TRANSFORM_CACHE_EXPIRATION",
    "advisory_lock_key",
    "database_url",
    "load_environment",
    "prefect_api_url",
    "prefect_deployment_name",
    "prefect_work_pool",
    "rejection_threshold",
    "session_mode_database_url",
    "snapshot_directory",
    "stale_run_minutes",
    "transformation_version",
]
