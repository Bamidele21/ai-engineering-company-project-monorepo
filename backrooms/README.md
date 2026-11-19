# `backrooms` folder

This folder contains **all the backend services** (APIs and background workers) related to the company for the cross-functional AI Engineering project.

Each subfolder inside `backrooms/` must correspond to **one specific service** (for example: `admin-api`, `data-processor-worker`) and include its own technical and functional documentation.

- **Main purpose**: to centralize all the backend logic, APIs, and queue consumers that support the company's use cases.
- **Recommendation**: document in this file (or in sub-READMEs) the services you add, their objective, the technology used, and how to run them.

> _Spanish version: [README.es.md](./README.es.md)._

---

## Services in this folder

### `services/Supply_directory_API` — FastAPI (port 8000)

Supplier directory and authentication (TinyDB), with password reset email
delivery through Resend.

### `services/Inventory-API` — FastAPI (port 8001)

Asset inventory on Supabase PostgreSQL, telemetry emission, and the weekly
office/programme performance reporting module (dispatches Prefect flows).

### `services/APIs/analyzer-api.py` — FastAPI (port 8002)

Incident CSV analyzer. Since the async-tasks milestone, `POST
/api/incidents/analyze` stages the upload and enqueues the analysis through
Celery, returning `202 Accepted` with a `task_id` immediately. Also serves
`GET /tasks/{task_id}` (status/result), `GET /api/incidents/results/export`
(CSV by task id), and `GET /tasks/dead-letter` (exhausted tasks).

### `services/task_queue/` — Celery app + tasks + DLQ storage

The async task queue implementation:

- `celery_app.py` — Celery instance; Redis (`REDIS_URL`) as broker and result
  backend. ACK-after-success (`task_acks_late`), JSON serializers, and hard
  time limits (90s soft / 180s hard).
- `tasks.py` — `nexova.analyze_incident_csv`: validates and analyzes a staged
  CSV. Transient read failures (`OSError`) retry up to 3 times with
  exponential backoff; exhausted retries record the failure in the dead
  letter queue.
- `storage.py` + `migrations/` — `task_queue.dead_letter_tasks` table
  (PostgreSQL migration + SQLite metadata for tests), recording `task_id`,
  task name, attempt number, error message, and timestamp.

**Run the worker** (from the `backrooms/` folder, with Redis reachable via `REDIS_URL`):

```bash
uv run --project services celery -A services.task_queue.celery_app:celery_app worker --loglevel=info --pool=solo
```

Stop it with `Ctrl+C` (or `docker compose stop celery-worker` when running in
Docker). See the root `README.md` for the full Docker Compose runbook and the
retry/DLQ demo instructions.

### `services/job_runner/` — nightly telemetry export

Scheduled job (see `scripts/nightly-crontab`) that exports telemetry CSVs and
records each run in `reporting.job_runs`.

### `services/reporting/` and `services/telemetry/` — supporting modules

Shared by the Inventory API: reporting queries/triggers and the telemetry
event catalog, emitter, and storage.
