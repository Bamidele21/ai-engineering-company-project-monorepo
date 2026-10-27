# Sprint 1 validation report — weekly office and programme performance

Date: 2026-10-27
Scope: Sprint 1 of `ETL_SPRINT_PLAN.md` (resilient Prefect pipeline plus the three reporting endpoints).

## Environment

1. Python 3.13.2 with the pipeline environment at `data/pipelines/.venv` (Prefect 3.9.0, SQLAlchemy, psycopg2).
2. Backend suite runs from `backrooms/services` (FastAPI, SQLModel, pytest).
3. Live source/destination: the configured Supabase PostgreSQL project.
4. PostgreSQL integration tests: disposable local PostgreSQL 17 cluster on port 55432. The Docker daemon was unavailable in this session, so the container-based path was not used.
5. Prefect server and process worker ran locally on port 4200; the worker used work pool `nexova-data-pipelines`.

## Live KPI output — week starting 2026-10-19

Source window: `[2026-10-19T00:00:00Z, 2026-10-26T00:00:00Z)`.
Source rows: 58 extracted, 58 deduplicated, 0 rejected. Raw event counts: inbound 35, outbound 19, threshold 3, variance 1.

| Office | Programme | Material cost | Kits delivered | Shortage events | Variance events | Currency |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| miami | new-hire-onboarding | 490.00 | 4 | 0 | 0 | USD |
| miami | test-programme | 380.00 | 2 | 0 | 0 | USD |
| valencia | basic-leadership | 278.00 | 2 | 0 | 0 | EUR |
| valencia | new-hire-onboarding | 755.00 | 7 | 1 | 1 | EUR |
| valencia | test-programme | 2500.00 | 4 | 2 | 0 | EUR |
| **Total** | | **4403.00** | **19** | **3** | **1** | mixed currencies, never summed across offices |

Reconciliation checks were all true: currency/office match, inbound/outbound/threshold/variance counts match the KPI totals, and deduplicated = accepted + rejected. `test-programme` is an unknown non-empty slug, so it was published with an `unknown_programme_ids` warning.

Week starting 2026-10-12 had no source events. The dimension scaffold produced 3 zero rows with the correct office currencies.

## Commands and results

| Check | Command | Result |
| --- | --- | --- |
| Exact CLI | `python data/pipelines/pipeline.py` (worker environment active) | Completed; 8 rows loaded across weeks 2026-10-12 and 2026-10-19 |
| Explicit week CLI | `python data/pipelines/pipeline.py --week-start 2026-10-19 --weeks 1` | Completed; 5 rows loaded |
| Isolated KPI tests | `python -m pytest tests/pipelines/test_pipeline.py` | 16 passed |
| Prefect behavior tests | `uv run pytest -q` from `data/pipelines` | 2 passed, 6 skipped (PostgreSQL marker) |
| Backend suite | `uv run pytest -q` from `backrooms/services` | 238 passed, 2 pre-existing deprecation warnings |
| PostgreSQL integration | `TEST_DATABASE_URL=... uv run pytest -q -m postgres` | 6 passed |
| Compose validation | `docker compose config -q` | Passed |
| Whitespace | `git diff --check` | Passed (CRLF notices only) |

## Resilience evidence

1. **Transform cache hit:** a repeated unchanged range logged `Task run 'transform_weekly_performance-79a' - Finished in state Cached(type=COMPLETED)`.
2. **Cache invalidation:** the Prefect behavior test invoked the real task three times, twice with identical input and once with a changed unit cost. The wrapped transform executed twice, proving reuse then invalidation.
3. **Optional-task failure:** `--fail-snapshot` made `write_eval_snapshot` fail. The flow still completed, persisted the KPI rows, and recorded `eval_snapshot_failed` in `warnings`.
4. **Idempotent reruns:** repeated loads of 2026-10-19 preserved the five destination row IDs while `computed_at` advanced. No duplicate grain rows appeared.
5. **Transactional rollback:** a PostgreSQL trigger injected a mid-load failure after the first row was attempted; the whole week rolled back and the table contained zero rows. The retry path then succeeds because the upsert is full-week and idempotent.
6. **Advisory lock:** two nested lock acquisitions on the same key returned `true` then `false` on the disposable PostgreSQL cluster.
7. **Stale runs:** the repository implements the 15-minute stale lease and marks abandoned queued/running rows failed; the database partial unique index allows only one active run per pipeline. A reporting API test injects a 30-minute-old running row and proves the next trigger marks it `failed` with `error_code='stale_run'` before starting.

## Endpoint evidence

1. `GET /reporting/weekly-office-program-performance?week_start=2026-10-19` with a bearer token returned `200` and 5 entries. Money is a JSON number (for example `490.0`), and the order is office then programme.
2. The same GET without a token returned `401`.
3. `GET /reporting/pipeline-runs/latest` returned `200` with status, timestamps, target weeks, counts, source counts, and a null `error` for a successful run.
4. `POST /reporting/pipeline-runs` without a token returned `401`.
5. `POST /reporting/pipeline-runs` with a manager token returned `202` with `run_id=7b03703b-49bb-4614-b331-05bfe26859f7` and target week `2026-10-19`.
6. The worker adopted that row: `flow_run_id=f8d2c723-d4d4-423f-80ef-495f69a9be77`, `status=completed_with_warnings`, `records_extracted=58`, `records_loaded=5`, `checkpoint_stage=complete`, `error=null`.
7. The authenticated KPI read after worker completion returned `200` with 5 entries.
8. Endpoint tests additionally cover `404` (no report/run), `422` (non-Monday/current/future week and invalid ranges), `409` (active run), `403` (regular user trigger), and `503` (database/dispatch outage).

## Deployment evidence

1. Work pool: `nexova-data-pipelines` (process).
2. Deployment: `weekly_office_program_performance_flow/weekly-office-program-performance`.
3. Entrypoint: `data/pipelines/pipeline.py:weekly_office_program_performance_flow`.
4. Schedule: `0 2 * * 1`, timezone UTC.
5. Concurrency: 1 (global deployment concurrency limit).
6. Parameters: `weeks: 2` by default.
7. Worker status during validation: `READY`, last polled at `2026-10-27T02:31:56Z`.

## Data-safety checks

1. `public.telemetry_events` was read-only: 60 `inventory-api` rows and 5 `backoffice` rows before and after the runs; the 58 allowlisted week rows were unchanged.
2. No `.env`, `CONTEXT.md`, `company-choice.md`, `data/raw/**`, `infra/**`, `internal/**`, or `mcps/**` file was modified.
3. The manager token used for the live API trigger came from a temporary TinyDB copy; the tracked `suppliers_db.json` was not edited.

## Limitations

1. Docker Desktop/image builds were not exercised; the PostgreSQL integration suite ran against a disposable local PostgreSQL 17 cluster instead.
2. The Prefect schedule was inspected on the deployment; no wall-clock scheduler tick was waited for.
3. The live source contains only one completed week with activity, so the two-week scheduled default produced one populated week and one zero week.
4. The unknown `test-programme` slug is published with a warning by design; it is not silently dropped.
