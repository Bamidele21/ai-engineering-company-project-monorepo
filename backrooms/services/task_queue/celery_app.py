"""Celery application for the Nexova async task queue.

Redis serves as both broker and result backend. The connection URL is read
from ``REDIS_URL`` (``redis://redis:6379/0`` inside Docker Compose,
``redis://localhost:6379/0`` for host development) so the API, the worker,
and Flower all talk to the same Redis instance.

Producer/consumer rules applied from the async-tasks milestone context:

1. **Messages stay lightweight.** Tasks receive only the path of a staged
   CSV file, never the file contents; the worker reads the file itself.
2. **ACK only after success.** ``task_acks_late`` plus
   ``task_reject_on_worker_lost`` return unconfirmed messages to the queue
   when a worker dies mid-task instead of losing them.
3. **Every task has a timeout.** ``task_soft_time_limit`` / ``task_time_limit``
   bound execution so a stuck task cannot block the worker pool forever.

Run a worker from the repository root::

    celery -A services.task_queue.celery_app:celery_app worker --app-dir backrooms --loglevel=info
"""

import os

from celery import Celery
from dotenv import load_dotenv

# Host development: read REDIS_URL/DATABASE_URL from the repo-root .env.
# No-op inside Docker Compose, where the environment is already injected.
load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "nexova",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_time_limit=180,
    task_soft_time_limit=90,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
)

# Imported last so the worker registers every task when it loads the app.
# The task module imports this module back, which is safe because the app is
# fully configured by the time this import runs.
from services.task_queue import tasks  # noqa: E402,F401  (isort:skip)
