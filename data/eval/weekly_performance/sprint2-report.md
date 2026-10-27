# Sprint 2 validation report — subflows, isolated tests, and business dashboard

Date: 2026-10-27
Scope: Sprint 2 of `ETL_SPRINT_PLAN.md` (subflow refactor, isolated KPI task
tests, the `/reporting` dashboard, recovery/late-event validation, monitoring,
and the Sprint 2 acceptance evidence).

## Environment

1. Python 3.13.2; pipeline environment at `data/pipelines/.venv` (Prefect 3.9.0).
2. Backend suite runs from `backrooms/services`.
3. Live source/destination: the configured Supabase PostgreSQL project.
4. PostgreSQL integration tests: disposable local PostgreSQL 17 cluster on port
   55432. The Docker daemon was unavailable in this session, so container
   builds were not exercised; `docker compose config -q` validates the wiring.
5. Prefect server and a process worker ran locally on port 4200 during the live
   checks; the Inventory API ran on port 8001 with a temporary manager copy of
   the TinyDB auth store (the tracked `suppliers_db.json` was not edited).
6. Browser evidence: headless Chrome driven over the DevTools protocol against
   the production backoffice build.

## Test results

| Check | Command | Result |
| --- | --- | --- |
| Isolated KPI tests | `python -m pytest tests/pipelines/test_pipeline.py` | 22 passed |
| Pipeline package tests | `uv run pytest -q` from `data/pipelines` | 24 passed, 6 skipped (PostgreSQL marker) |
| PostgreSQL integration | `TEST_DATABASE_URL=... uv run pytest -q -m postgres` | 8 passed |
| Backend suite | `uv run pytest -q` from `backrooms/services` | 238 passed, 2 pre-existing deprecation warnings |
| Frontend Jest | `npx jest --runInBand` from the repo root | 117 passed across 15 suites (24 reporting tests) |
| Backoffice lint | `npm run lint` in `uis/backoffice` | Passed |
| Backoffice build | `npm run build` in `uis/backoffice` | Passed; `/reporting` generated |

## Subflow refactor evidence

The main flow now coordinates subflows instead of implementing stages:

```
weekly_office_program_performance_flow
  ├─ extract_weekly_office_program_telemetry_flow
  ├─ transform_weekly_office_program_performance_flow
  │    ├─ transform_weekly_performance (cached validation boundary)
  │    ├─ compute_total_material_cost
  │    ├─ count_kits_delivered
  │    ├─ count_shortage_events
  │    └─ count_cost_variance_events
  ├─ load_weekly_office_program_performance_flow
  ├─ publish_weekly_performance_snapshot_flow   (return_state=True)
  └─ alert_weekly_performance_flow              (return_state=True)
```

The live CLI log shows each subflow beginning and finishing for both target
weeks, with the four KPI tasks executing inside the transform subflow. The
isolated suite calls the KPI task `.fn` implementations with in-memory
telemetry-shaped fixtures, including the required hand-calculated cases:

- `test_total_material_cost_uses_quantity_and_decimal_cost` — 3 × 12.50 + 2 × 5.25
  produces `48.00` EUR; a variance event adds no spend.
- `test_kits_delivered_counts_events_not_units` — outbound quantities 10 and 2
  produce `2`, not 12.
- `test_shortage_frequency_counts_captured_threshold_events` — two accepted
  threshold events, including stock quantity zero, produce `2`.
- `test_cost_variance_frequency_counts_alerts` — one positive and one negative
  variance alert produce `2`.
- Defensive cases for every task: empty input yields the empty mapping,
  malformed quantities/costs/dimensions raise `ValueError` instead of
  corrupting totals, and currency separation is asserted across offices.

## CLI after the refactor

`python data/pipelines/pipeline.py` completed with the subflow topology. Run
`e9147269-0563-4e20-96ab-4f2c50c4c848` loaded 8 rows across weeks 2026-10-12
(3 zero rows) and 2026-10-19 (5 rows), status `completed_with_warnings` with
`unknown_programme_ids` (the live `test-programme` slug). `recomputed_weeks`
was empty and `supersedes_run_id` null because the unchanged data matched the
previous fingerprints.

`--health-check` ran the independent health flow: 1 alert
(`reconciliation_warning`), `baseline_status=available`,
`prior_completed_runs=4`. The alert subflow executed as a non-critical subflow.

## Recovery and late-event evidence

1. **Late-event supersession (SQLite flow test):** a first run publishes
   10.00; a late event arrives in the same week; the recompute records
   `supersedes_run_id` = the first run, `recomputed_weeks` holds the old and
   new week fingerprints, the total becomes 15.00, and the existing KPI row
   keeps its `id`.
2. **Unchanged recompute:** a second unchanged run supersedes nothing.
3. **Resume:** a two-week run fails on the second week (`checkpoint_stage=load`,
   `checkpoint_week=2026-10-19`). `--resume-from` plans only the failed week,
   leaves the committed week's row identities untouched, and publishes the
   failed week.
4. **PostgreSQL late-event replacement:** loading the same week twice with an
   expanded row set updates the total, preserves the row `id`, and adds no
   duplicate grain rows.
5. **PostgreSQL multi-week resume:** after the later week fails, `plan_resume`
   returns exactly the uncommitted week and the resumed load lands alongside
   the intact committed week.
6. **Races:** flow-level tests cover a scheduled run skipping when a run is
   active, a manual run raising the conflict, worker adoption of the
   API-created queued run, stale-run recovery before a new run, and resume
   validation errors. PostgreSQL tests cover the active-run unique index and
   the advisory lock.
7. **Fingerprints:** pure tests prove an identical input keeps the same
   fingerprint while a cost-only change and a count-only change both
   invalidate it.

## Dashboard evidence (`uis/backoffice/app/reporting/page.tsx`)

The page title is **Weekly Office & Programme Performance Report**. The four
sections are labelled **Material Cost per Office/Programme**, **Kits
Delivered**, **Shortage Frequency**, and **Cost Variance Frequency**. Each
table identifies office and programme; costs use the row's currency with no
cross-currency grand total. The notes explain that Kits Delivered counts
delivery events and that the shortage/variance frequencies count captured
(throttled) alerts.

Headless Chrome, authenticated with a manager token, rendered the real
2026-10-19 data:

- Material cost: Miami new-hire-onboarding $490.00, Miami test-programme
  $380.00, Valencia basic-leadership €278.00, Valencia new-hire-onboarding
  €755.00, Valencia test-programme €2,500.00.
- Kits delivered: 4 / 2 / 2 / 7 / 4.
- Shortage events: 0 / 0 / 0 / 1 / 2.
- Cost variance events: 0 / 0 / 0 / 1 / 0.

The week selector offered 12 completed Monday weeks. Selecting 2026-10-12
showed the computed zero rows plus the "No activity this week" card; selecting
2026-10-05 (never computed) showed "No report has been computed for this
week."; selecting 2026-10-19 again restored the real data, confirming the
stale-response guard. A screenshot is saved at
`data/eval/weekly_performance/sprint2-dashboard.png`.

## End-to-end trigger

1. `POST /reporting/pipeline-runs` with a manager token returned `202` and
   `run_id=23a2b005-f06c-4b32-a98b-06710104b260`.
2. The worker adopted the row: `flow_run_id=0807a191-13de-418d-bfb6-0dbbd6cebd4a`,
   status `completed_with_warnings`, 58 extracted, 5 loaded,
   `checkpoint_stage=complete`, error null.
3. The authenticated KPI read returned `200` with the 5 entries above.

## Data-safety checks

1. `public.telemetry_events` remained read-only from the pipeline's side. Live
   business activity (16 new `inventory-api` order events at 2026-10-27T03:40Z,
   one rejected outbound) arrived through the Inventory API during validation
   and landed in the **incomplete current week** (2026-10-26), which the
   completed-week rule never publishes. The published weeks 2026-10-12 and
   2026-10-19 kept their source counts and values.
2. No `.env`, `CONTEXT.md`, `company-choice.md`, `data/raw/**`, `infra/**`,
   `internal/**`, or `mcps/**` file was modified.
3. The manager token used for live API and browser checks came from a temporary
   TinyDB copy under the system temp directory.

## Container verification (2026-10-27, follow-up fix)

The backend image originally lacked `data/`, so the reporting module's import
of `data.pipelines` failed inside it. Fixed and verified:

1. `backrooms/services/Dockerfile` now copies `data/` into the image, and the
   Compose build context moved to the repository root so both backend services
   build with `data/` included.
2. The worker's `./data` bind mount was removed: it shadowed the image's Linux
   virtualenv with the Windows host copy, which broke the `prefect` binary on
   PATH inside the container.
3. The root `.dockerignore` now excludes `.env` files, the TinyDB auth store,
   caches, and build artifacts, so no secrets reach any image.
4. Verified inside the built backend image: `from services.reporting.service
   import get_report, get_latest_run, trigger_run` succeeds, the Inventory API
   main import succeeds, and all three `/reporting` paths appear in OpenAPI.
5. Verified inside the built worker image: the exact
   `from data.pipelines.weekly_office_program_performance import queries,
   status, triggers` import succeeds, the CLI help renders, and a full ETL run
   against the live database completed (5 rows loaded, subflows executed).
6. Full Compose stack (`docker compose build` + `up -d`): all five images
   built; suppliers-api, inventory-api, and prefect-server are healthy; the
   worker registered `nexova-data-pipelines` and the
   `weekly-office-program-performance` deployment; the UI container serves on
   ports 3000/3001.
7. Through the stack: an authenticated read of the KPI endpoint returned `200`
   with the 5 entries, a trigger by a regular user returned `403`, and a
   deployment run created through the stack's Prefect API was executed by the
   container worker (`flow_run_id=c55faad7-5f60-4b8e-859c-a8bc48948fa4`,
   58 extracted, 5 loaded, error null).

## Limitations

1. No wall-clock scheduler tick was awaited; deployment runs exercised the same
   worker/deployment path.
