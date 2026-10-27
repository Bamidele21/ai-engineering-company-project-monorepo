# Weekly Office & Programme Performance — Runbook

This runbook covers operating the Nexova weekly performance pipeline. The
architecture and KPI contract live in `data/pipelines/PIPELINE_DESIGN.md`;
evidence lives in `data/eval/weekly_performance/`.

## 1. Setup

1. Worker environment: `cd data/pipelines && uv sync`.
2. `DATABASE_URL` is read from the repository-root `.env` (or
   `backrooms/services/Inventory-API/.env`). It is the Supabase transaction
   pooler URI (`:6543`). The advisory lock derives a session-mode URL by
   switching to `:5432` on the same host.
3. Prefect configuration:
   - `PREFECT_API_URL` — the Prefect API (default `http://localhost:4200/api`).
   - `PREFECT_DEPLOYMENT_NAME` — `weekly-office-program-performance`.
   - `PREFECT_WORK_POOL` — `nexova-data-pipelines`.
   - `PREFECT_RESULTS_PERSIST_BY_DEFAULT=true` on the worker so the one-hour
     transform cache survives between process runs.
   - `REPORTING_REJECTION_THRESHOLD` — rejection share that blocks publication
     (default `0.05`).
   - `REPORTING_STALE_RUN_MINUTES` — stale heartbeat lease (default `15`).
   - `REPORTING_ALERTS_WEBHOOK` — optional webhook for the non-critical alert
     subflow. Alerts are observability-only; unset means no delivery.
4. Schema: the Inventory API startup applies
   `backrooms/services/reporting/migrations/001_reporting_schema.sql`
   idempotently. The pipeline CLI also bootstraps the schema when it starts.

## 2. CLI

From the repository root with the worker environment active:

```bash
# Last two complete UTC weeks (the scheduled default):
python data/pipelines/pipeline.py

# One explicit completed Monday week:
python data/pipelines/pipeline.py --week-start 2026-10-19 --weeks 1

# Backfill a range of up to 52 completed Monday weeks:
python data/pipelines/pipeline.py --week-start 2026-08-24 --weeks 8 --trigger-type backfill

# Resume a failed run (skips committed weeks, recomputes the failed one):
python data/pipelines/pipeline.py --resume-from <failed-run-id>

# Freshness/silence/baseline health check (independent of the ETL):
python data/pipelines/pipeline.py --health-check

# Adopt an API-created queued run instead of creating a new row:
python data/pipelines/pipeline.py --run-id <run-id> --week-start 2026-10-19
```

Week inputs must be Mondays. Current and future weeks are rejected.

## 3. Manual trigger (API)

`POST /reporting/pipeline-runs` with a manager/admin bearer token. Body:

```json
{ "week_start": "2026-10-19", "weeks": 1 }
```

`week_start` defaults to the most recent completed week and `weeks` to 1
(maximum 52). The response is `202` with the queued `run_id`. The API writes a
`queued` row in `reporting.pipeline_runs` and dispatches the flow run to the
Prefect deployment; the worker adopts the row rather than creating a second one.
`409` means a run is already active.

## 4. Schedule

The Prefect deployment `weekly-office-program-performance` runs `0 2 * * 1` UTC
(Monday 02:00) with concurrency 1 and parameters `weeks=2`, so every scheduled
run recomputes the last two complete weeks and absorbs late events.

Start the stack locally:

```bash
prefect server start --host 127.0.0.1 --port 4200
export PREFECT_API_URL=http://127.0.0.1:4200/api
prefect work-pool create nexova-data-pipelines --type process --overwrite
prefect deploy --all --no-prompt --prefect-file data/pipelines/prefect.yaml
prefect worker start --pool nexova-data-pipelines --type process
```

Docker Compose provides `prefect-server` and `prefect-worker` services with the
same topology.

## 5. Backfill

Backfill is a manual run with `--trigger-type backfill` or an API trigger with
`week_start` and `weeks` (up to 52). Every target week must be a completed
Monday. Weeks are processed in order, one transaction per week, and
`checkpoint_week` advances after each commit.

## 6. Failed-run investigation

1. Read `reporting.pipeline_runs` for the run: `status`, `error_code`,
   `error_message`, `checkpoint_stage`, `checkpoint_week`, and the counters.
   `GET /reporting/pipeline-runs/latest` exposes the same row.
2. `failed` with `stale_run` means the worker died; the next run recovers the
   lease automatically.
3. `failed` with a stage checkpoint means the stage failed after earlier weeks
   committed. Resume with `--resume-from <run-id>`; committed weeks are
   skipped and the failed week is recomputed transactionally.
4. `publication_blocked` means rejections exceeded `REPORTING_REJECTION_THRESHOLD`
   or reconciliation failed. Inspect `reporting.pipeline_rejected_events` for
   the sanitized reasons (it never stores payloads or user data).
5. The Prefect UI (linked via `flow_run_id`) holds the raw flow logs; the run
   row stays readable even when Prefect is down.

## 7. Worker restart

Stop the worker process, restart it with the same pool and environment, and
re-deploy after code changes (`prefect deploy --all --no-prompt --prefect-file
data/pipelines/prefect.yaml`). The one-hour transform cache lives in Prefect's
result storage; a restart within an hour can still serve cache hits, and any
stale cache expires by design.

## 8. Credentials and configuration names

- `DATABASE_URL` — Supabase transaction pooler URI (source and destination).
- `JWT_SECRET_KEY` — shared with the Supply Directory API for reporting auth.
- `PREFECT_API_URL`, `PREFECT_DEPLOYMENT_NAME`, `PREFECT_WORK_POOL`,
  `PREFECT_RESULTS_PERSIST_BY_DEFAULT` — orchestrator wiring.
- `REPORTING_REJECTION_THRESHOLD`, `REPORTING_STALE_RUN_MINUTES`,
  `REPORTING_ALERTS_WEBHOOK`, `REPORTING_SNAPSHOT_DIR` — pipeline quality gates
  and outputs.
- `INVENTORY_ALLOWED_ORIGINS` — API CORS origins for the backoffice.

## 9. Alert ownership

Alerts describe business-facing pipeline health; they are not infrastructure
pages. Owners:

- **Weekly run missing/failed** — the pipeline engineer (investigate worker,
  Prefect schedule, and database connectivity).
- **Stale run** — the pipeline engineer (crashed worker recovery is automatic;
  verify the lease).
- **Rejected events / reconciliation warnings** — the pipeline engineer with
  the inventory team (schema drift or emitter payload problems).
- **Unexpected or one-sided office silence** — L&D operations (Elena) with the
  pipeline engineer (could be a real business pattern or a capture outage).

## 10. Report-consumer notes

- `kits_delivered_count` counts delivery events, not units.
- Shortage and variance frequencies count captured alerts; the inventory
  emitter throttles them (one shortage alert per product per hour, one variance
  alert per product/supplier per day).
- Valencia rows are EUR and Miami rows are USD; the dashboard never sums
  across currencies.
- Events older than the scheduled two-week lookback need an explicit backfill;
  the source has no `received_at` column, so automatic lateness detection is
  not possible in v1.
