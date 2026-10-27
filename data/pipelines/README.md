# `data/pipelines` folder

This folder groups **all data pipelines in the monorepo** related to the company: ingestion, ETL/ELT, cleaning, transformation, and loading into analytical or production systems.

Each subfolder or file under `data/pipelines/` should represent **one pipeline or job set** (for example `sales-etl`, `telemetry-stream`, `customer-segmentation`) and include the required configuration (scripts, orchestration, connectors, schemas, etc.).

- **Main purpose**: consolidate in one place the data movement and transformation logic that powers the company’s applications and analytics.
- **Recommendation**: document pipelines as you add them—their goal, data sources and sinks, dependencies, and how to run them in development, testing, and production.

> _Spanish version: [README.es.md](./README.es.md)._

---

## Nexova weekly office and programme performance pipeline

This pipeline reads the four allowlisted inventory events from `public.telemetry_events`, computes the four briefing KPIs, and upserts them into `reporting.weekly_office_program_performance`. It never writes to `telemetry_events`.

### Layout

- `pipeline.py` — CLI and Prefect flow entrypoint.
- `weekly_office_program_performance/` — extraction, tasks, flow, load, run log, queries, status, triggers, schema.
- `../process/weekly_performance/` — pure normalization, deduplication, aggregation, zero-fill, and reconciliation.
- `../eval/weekly_performance/` — sanitized validation evidence and optional run snapshots.

### Setup

```bash
cd data/pipelines
uv sync
```

`DATABASE_URL` comes from the repository-root `.env` (or `backrooms/services/Inventory-API/.env`). See `data/pipelines/.env.example` for worker and Prefect settings.

### CLI

```bash
# From the repository root, using the worker environment:
python data/pipelines/pipeline.py
python data/pipelines/pipeline.py --week-start 2026-10-19 --weeks 1
python data/pipelines/pipeline.py --week-start 2026-10-12 --weeks 4 --trigger-type backfill
```

The no-argument command recomputes the last two complete ISO weeks (Monday UTC). Explicit weeks must be completed Mondays; non-Monday or current/future weeks are rejected.

### Tests

```bash
# Isolated KPI transformation tests (no database, network, Prefect, or secrets):
python -m pytest tests/pipelines/test_pipeline.py

# Worker project tests (PostgreSQL integration tests skip unless TEST_DATABASE_URL is set):
cd data/pipelines
uv run pytest -q

# Disposable PostgreSQL integration suite:
TEST_DATABASE_URL=postgresql+psycopg2://... uv run pytest -q -m postgres
```

### Prefect deployment

```bash
prefect server start --host 127.0.0.1 --port 4200
export PREFECT_API_URL=http://127.0.0.1:4200/api
prefect work-pool create nexova-data-pipelines --type process --overwrite
prefect deploy --all --no-prompt --prefect-file data/pipelines/prefect.yaml
prefect worker start --pool nexova-data-pipelines --type process
```

The deployment is `weekly-office-program-performance`; it runs at `0 2 * * 1` UTC with concurrency 1 and defaults to `weeks=2`. Docker Compose provides `prefect-server` and `prefect-worker` services for the same topology.

### Reporting API

The Inventory API hosts `backrooms/services/reporting/`:

- `GET /reporting/weekly-office-program-performance?week_start=YYYY-MM-DD` (bearer auth).
- `GET /reporting/pipeline-runs/latest` (bearer auth).
- `POST /reporting/pipeline-runs` (manager or admin; returns `202`).

The KPI endpoint returns no cache; the latest-run endpoint reads the database so it keeps answering during a Prefect outage. The manual trigger writes a queued run row and dispatches to the Prefect REST API.

### Operational notes

- The API process does not run the ETL; the worker does.
- The reporting schema enables RLS and revokes `anon`/`authenticated`; the browser uses the API.
- The advisory lock needs a session-mode connection. The transaction pooler URL is converted from port 6543 to 5432; if unavailable, the flow falls back to the active-run unique index and Prefect concurrency limit.
- `total_material_cost` is decimal money in the local office currency. EUR and USD are never summed together.

### Sprint 2 additions

- The main flow coordinates the `extract`, `transform`, `load`, and optional
  `publish` subflows; the transform subflow runs the four domain KPI tasks.
- `--resume-from <run-id>` skips committed weeks and recomputes the failed one.
- `--health-check` runs the freshness/silence/baseline checks independently of
  the ETL; alert delivery uses the optional `alert_weekly_performance_flow`.
- The operating runbook lives in [RUNBOOK.md](./RUNBOOK.md).
- The business dashboard is served by `uis/backoffice` at `/reporting`.
