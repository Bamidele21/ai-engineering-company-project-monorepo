# Nexova Business Performance Pipeline — Two-Sprint Implementation Plan

**Date:** 2026-10-26

**Status:** Proposed implementation backlog covering both ETL contexts.

**Planning assumption:** Two sprints of two weeks each, with pipeline/backend and frontend work shared across engineers. Durations and role assignments are estimates, not confirmed team commitments; re-estimate for a single implementer.

**Outcome:** Laura Mendoza and Elena Vargas can view an auditable Weekly Office & Programme Performance Report in the backoffice, refreshed for Monday morning.

## 1. Source documents and scope

| Source | Planning use |
| --- | --- |
| [`etl-context1.md`](./etl-context1.md) | Part 2 implementation requirements: Prefect flows/tasks, retries, optional-task failure handling, caching, idempotency, CLI execution, run metadata, and three endpoints. |
| [`etl-context2.md`](./etl-context2.md) | Part 3 requirements: at least three reusable subflows, isolated transformation-task tests in `tests/pipelines/test_pipeline.py`, preserved CLI execution, and a mandatory business dashboard. |
| [`PIPELINE_DESIGN.md`](./PIPELINE_DESIGN.md) | Architecture, exact identifiers, KPI semantics, persistence, recovery, schedules, API contracts, and verification strategy. This is the actual filename; `PIPELINE__DESIGN.md` is not present. |
| [`ETL-company-Briefing.md`](./ETL-company-Briefing.md) | Source of truth for KPI definitions, destination DDL, business audience, and response shape. |
| [`README.md`](./README.md) | Pipeline location, configuration, and execution documentation requirements. |

Sprint 1 implements Part 2 from `etl-context1.md`, including all three reporting endpoints. Sprint 2 implements Part 3 from `etl-context2.md`: subflows, isolated tests, the dashboard, and operational hardening from the design. The design's Part 1 "design only" and dashboard exclusions describe the earlier milestone; the two implementation contexts now extend that scope.

### Fixed business contract

- Source: read-only `public.telemetry_events`, filtered to `service='inventory-api'` and the four events below. Read `public.assets` and `public.programmes` for the real office/programme dimension scaffold.
- Destination: exact briefing table `reporting.weekly_office_program_performance`, with unique grain `(office, programme_id, week_start)`; supporting tables are `reporting.pipeline_runs` and `reporting.pipeline_rejected_events`.
- Week: completed ISO weeks only, Monday UTC; inclusive start and exclusive end. Scheduled runs recompute the last two complete weeks.
- Money: `Decimal`/Postgres `numeric`, half-up rounding to two decimal places after aggregation; Valencia uses `EUR`, Miami uses `USD`.
- Zero-fill: actual catalogue office/programme pairs plus valid observed pairs, including unknown non-empty programme slugs with warnings. Do not invent pairs through an unconditional cross join.
- Reporting module: `backrooms/services/reporting/`, importing business functions from `data/pipelines/`; Inventory API hosts the router.
- Preserve the existing technical telemetry report and source data. Fixtures and validation evidence belong under `data/eval/weekly_performance/`; `data/raw/**` is protected.

| KPI field | Source event | Required calculation after deduplication and validation |
| --- | --- | --- |
| `total_material_cost` | `inbound_order_created` | Sum `quantity * unit_cost`; ignore the source `value` column for cost. |
| `kits_delivered_count` | `outbound_order_created` | Count events, not `sum(quantity)`. |
| `shortage_events_count` | `stock_threshold_triggered` | Count captured shortage events. |
| `cost_variance_events_count` | `kit_cost_variance_detected` | Count captured variance events; do not add their cost to material spend. |

## 2. Decisions to settle at Sprint 1 kickoff

These are implementation gaps or ambiguities in the design, not reasons to change the briefing contract.

| Decision / gap | Proposed resolution and completion condition | Owner |
| --- | --- | --- |
| Part 3 extends the design's task topology and test layout | Keep the existing task names; define domain-named subflows and KPI tasks in Sprint 2. Put required isolated tests in root `tests/pipelines/test_pipeline.py`, with integration suites alongside the pipeline/API packages. | Pipeline engineer |
| Design says "Proposed / design only"; implementation context assumes approval | Confirm the implementation baseline; update design status and implementation-specific details as the work lands. | Tech lead |
| CLI, optional task, and one-hour caching are absent from the proposed layout/task table | Add `pipeline.py`, optional `write_eval_snapshot`, and explicit transform caching while retaining the four designed task names. | Pipeline engineer |
| Runtime and dependency ownership | Use a dedicated `data/pipelines/pyproject.toml` for the worker and `uv add "prefect>=3"` there. Specify test dependencies and result storage. Keep HTTP-facing imports usable without importing Prefect flow code. If using the recommended REST trigger, promote `httpx` to a backend runtime dependency; it is currently dev-only. | Pipeline + backend engineers |
| Session advisory lock versus transaction-pooler URL | Validate the connection mode before implementing the lock. Session-scoped advisory locks require a stable database session; use a direct/session-mode connection for the dedicated lock connection, or review an alternative locking design. A dedicated client connection through a transaction pooler is insufficient. | Pipeline engineer |
| Data-quality publication gate | Freeze the rejection threshold, denominator, and reconciliation strictness in config and the design. Proposed v1: any rejection warns; more than 5% of extracted rows fails before load; untrustworthy count/currency reconciliation always blocks the affected week. Test zero denominators and threshold boundaries. | Tech lead + pipeline engineer |
| Queue/worker identity and recovery | Pass the API-created `run_id` to the worker so it adopts that row rather than creating a second active row. Define dispatch-failure handling, stale queued-run handling, and checkpoints as last committed week plus current failure stage. | Backend + pipeline engineers |
| KPI and default-week wording | Confirm event-count semantics with Laura/Elena; preserve v1 fields. Define "most recent computed week" as greatest published `week_start`, so recomputing an old week does not move the default report backwards. | Tech lead + business owners |

Document the decisions in `PIPELINE_DESIGN.md` during implementation. Keep secrets in runtime configuration/Prefect blocks; any necessary protected-path edits require the confirmation specified by `AGENTS.md`.

## 3. Sprint 1 — Deliver the resilient pipeline and reporting API

**Goal:** Run `python data/pipelines/pipeline.py`, produce correct weekly KPI rows, and expose all three authenticated reporting endpoints with an independently running Prefect worker.

**Suggested sequence:** Days 1–2: S1-01/02; days 3–5: S1-03/04 plus API contract work; days 6–8: S1-05/06/07/08; days 9–10: S1-09 and acceptance demonstration. Backend/API work can proceed alongside pipeline implementation once contracts are frozen. Tests accompany every functional work item.

| ID | Work and concrete deliverables | Acceptance criteria | Depends on |
| --- | --- | --- | --- |
| S1-01 | Resolve kickoff decisions; bootstrap `data/pipelines/pipeline.py`, package imports, worker environment, and test discovery. Document setup/run commands. | `pipeline.py` defines `weekly_office_program_performance_flow` and invokes it through `__main__`, satisfying both contexts' entrypoint requirement. Validate explicit week/range inputs. Imports work from repository root without relying on incidental working-directory state. | Kickoff |
| S1-02 | Add `backrooms/services/reporting/migrations/001_reporting_schema.sql` and idempotent schema initialization; implement run-log/quarantine repositories under `data/pipelines/weekly_office_program_performance/`. | KPI DDL matches the briefing exactly. All three reporting tables have appropriate RLS/revokes; indexes and active-run uniqueness are present. Initialization works twice. Logs capture start/end, counters, status, and sanitized errors. | S1-01 |
| S1-03 | Implement `extract_weekly_telemetry` and dimension reads in `extract.py`. Select allowlisted fields, including `service`, schema version, event identity, and order identity needed downstream. | SQL filters four event types, service, and UTC bounds. Dedup uses `tags._meta.eventId`, falling back to source row `id`; earliest timestamp then smallest row ID wins. Raw and deduplicated counts remain distinguishable; payload conflicts and order-identity anomalies are observable. | S1-01/02 |
| S1-04 | Implement pure normalization/aggregation in `data/process/weekly_performance/` and `transform_weekly_performance`. | Four KPIs match golden expected values. Invalid rows produce sanitized rejection records; integer quantity, positive cost, schema version, currency, and UTC rules are enforced. Valid unknown slugs remain visible with warnings. Zero-fill uses the real dimension scaffold. Reconciliation gates publication. | S1-03 |
| S1-05 | Implement `load_weekly_performance`, quarantine persistence, and `record_pipeline_run`. | One transaction per week uses `ON CONFLICT (office, programme_id, week_start)` to replace aggregates. Reruns preserve row IDs and KPI values; only freshness metadata changes. A mid-load failure leaves the previous week intact. Checkpoints advance only after commit; retrying persistence does not duplicate quarantine entries for the same run/source/reason. | S1-02/04 |
| S1-06 | Assemble the main Prefect flow with the four named tasks, retry policies, transform caching, and optional `write_eval_snapshot`. Add active-run gate, dedicated advisory lock, heartbeat, and finalization. | Transient I/O failures retry; validation failures fail deliberately. Optional snapshot failure is handled with `return_state=True` and does not fail an otherwise valid publication. Required-task failure prevents downstream publication. Locks release on completion/failure; failure logging preserves the original error. | S1-03/04/05 |
| S1-07 | Implement `queries.get_weekly_report()`, `status.get_latest_run()`, and `triggers.trigger_manual_run()` in the pipeline package; expose all three routes with Pydantic models in `backrooms/services/reporting/`. | KPI contract matches the briefing; reads require bearer auth; manual trigger requires manager/admin and returns `202`. Worker adopts the API-created run row. HTTP layer imports pipeline functions without duplicating ETL logic. Handle dispatch failures, invalid ranges, and active-run conflicts explicitly. | S1-02/05/06 |
| S1-08 | Register reporting router/schema initialization in Inventory API; configure API/worker imports, dependencies, deployment, and Monday schedule. | Container sees root `data` package; worker runs independently in pool `nexova-data-pipelines`. Deployment `weekly-office-program-performance` invokes `pipeline.py:weekly_office_program_performance_flow`, uses `0 2 * * 1` UTC and concurrency 1, and targets the last two complete weeks. Manual endpoint actually dispatches to the worker. | S1-01/06/07 |
| S1-09 | Complete happy/edge/failure tests, API/deployment smoke, and CLI demonstration; save sanitized evidence in `data/eval/weekly_performance/sprint1-report.md`. | Demonstrate exact KPIs, dedup, zero activity, cache reuse/invalidation, optional failure tolerance, rollback/rerun, and all three endpoints. Include actual commands/results and reconcile source counts to destination rows. | S1-01–08 |

### Endpoint acceptance contract (Sprint 1)

| Endpoint | Happy / edge behavior | Failure behavior |
| --- | --- | --- |
| `GET /reporting/weekly-office-program-performance` | `{week_start, entries}` with exact briefing fields and numeric money; explicit/default completed week; all real pairs including zero rows; order by `office`, then `programme_id`; no API cache in v1. | `404` for no computed rows; `422` for malformed/non-Monday/current/future week; `503` for database outage; bearer authentication required. |
| `GET /reporting/pipeline-runs/latest` | Latest pipeline run with status, timestamps, counts, target weeks, and sanitized error; handle queued timestamps being null. | `404` when no run exists; `503` for database outage; continues serving stored status during Prefect outage. |
| `POST /reporting/pipeline-runs` | Default most recent complete week; explicit `week_start` with `weeks` 1–52; `202` queued response linked to actual worker execution. | `409` active run; `422` invalid/incomplete range; `503` dispatch/database failure; `401` unauthenticated, `403` unauthorized role. |

### Resilience implementation contract

1. **Critical path:** extraction, valid transformation/reconciliation, load, and auditable run-state persistence. Failure here must not be disguised as a successful report. If logging fails during an outage, preserve the original failure in Prefect/structured logs and recover the stale database row later.
2. **Optional path:** `write_eval_snapshot` runs after the critical ETL, uses `return_state=True`, and records a sanitized warning if it fails. Keep authoritative run logging out of this optional category. Any external notification added later receives its own bounded retries.
3. **Retries:** database tasks, including dimension reads, quarantine writes, and `record_pipeline_run`, use explicit `retries` and `retry_delay_seconds`. Start with three retries and delays of 30, 120, and 300 seconds for transient I/O failures, with an inline justification. Do not retry deterministic validation/constraint failures. Load retries repeat the entire failed week's transaction.
4. **One-hour transform cache:** configure `cache_key_fn` and `cache_expiration=timedelta(hours=1)`. Hash normalized relevant input content, target week, dimension scaffold, quality configuration, and transformation version. Exclude `run_id`, credentials, and database connection objects. A date-only or event-ID-only key is insufficient: late events, changed costs, and dimension changes must invalidate cached results.
5. **Safe cache scope:** cache the pure result, including deterministic rejection/reconciliation data; persist run-specific metadata separately on every run. Configure result persistence accessible to the worker. Fresh extraction still checks for late events; never cache away required loads, locks, heartbeats, or audit writes.
6. **Recovery:** heartbeat frequently enough to remain live during the longest stage/retry interval. Treat 15-minute stale leases only after checking lock/worker ownership. Record the failed stage separately from committed-week progress so restart cannot skip an uncommitted week.

### Sprint 1 verification and exit gate

| Tier | Required evidence |
| --- | --- |
| Happy | Both offices and all four event types produce independently calculated totals; multi-unit inbound affects cost, multi-unit outbound still counts once. CLI succeeds and run metadata is complete. |
| Edge | Sunday/Monday and year boundaries; duplicate ties and missing event IDs; empty-source week with valid dimensions; office-specific programmes; unknown valid slug; zero threshold quantity; one-hour cache expiry and changes to input/dimensions. |
| Failure | Currency mismatch, malformed numeric/schema values, dimension outage, rejection-threshold breach, transient/exhausted database retries, injected mid-load failure, optional snapshot failure, and failure to record final status. |

- [ ] `pipeline.py` runs the actual flow, with at least extraction, transformation, and load tasks plus the named audit task.
- [ ] PostgreSQL integration tests prove JSONB extraction, uniqueness, advisory locking, and transaction rollback; SQLite alone is insufficient for these guarantees.
- [ ] A repeated unchanged range has identical business values and row identities, with no duplicate grain; `computed_at` may advance.
- [ ] Tests exercise actual Prefect cache/state behavior as well as pure functions; decorator inspection alone is insufficient.
- [ ] All three endpoints pass happy/edge/failure and permission tests; trigger → worker → persisted report → authenticated KPI read succeeds.
- [ ] API/worker container imports and UTC schedule are verified; failed or ambiguous dispatch cannot silently strand an active row or launch duplicate workers.
- [ ] Source telemetry is unchanged by execution, and the existing telemetry regression suite passes.
- [ ] Design, run instructions, and `memory-bank/progress.md` reflect the implemented behavior and actual validation results.

## 4. Sprint 2 — Reusable subflows, isolated tests, and business dashboard

**Goal:** Preserve the working Part 2 pipeline while making its stages independently reusable and putting all four real business KPIs in front of Laura and Elena.

**Suggested sequence:** Days 1–3: S2-01/02; days 2–5: S2-03/04 in parallel with pipeline work; days 6–8: S2-05/06; days 9–10: S2-07 and handoff. Frontend work depends on Sprint 1's stable API, not on completion of the subflow refactor.

| ID | Work and concrete deliverables | Acceptance criteria | Depends on |
| --- | --- | --- | --- |
| S2-01 | Refactor `weekly_office_program_performance_flow` in `pipeline.py` to invoke at least three `@flow` subflows in sequence; move optional snapshot orchestration into its own subflow. | Explicit inputs/outputs, independent execution, and domain names follow the contract below. Main flow coordinates rather than implementing stages. Preserve task retries/cache, locks, audit identity, atomic load, and CLI. Optional subflow is called with `return_state=True`. | Sprint 1 gate |
| S2-02 | Expose four isolated KPI transformation tasks and add root `tests/pipelines/test_pipeline.py`; extend pure-function and orchestration regression tests. | At least three transformation tasks tested independently, with happy/edge/failure coverage; planned coverage includes all four KPIs. In-memory telemetry-shaped fixtures need no DB, network, Prefect server, or secrets. Exact required pytest command passes. | S2-01; Sprint 1 transform logic |
| S2-03 | Add `uis/backoffice/lib/reporting.ts` and its Jest tests for typed KPI fetching, week selection, currency formatting, and error handling. | Reuse `authorizedFetch`, `parseApiError`, and the existing Inventory API URL. Fetch `/reporting/weekly-office-program-performance`; preserve server totals, numeric zeros, and office currencies. Validate malformed responses rather than presenting them as zero business activity. | S1-07 |
| S2-04 | Build `uis/backoffice/app/reporting/page.tsx`; add Reporting navigation in `BackofficeShell`; reuse existing card/table styles. | Display all four exact KPI labels and the returned UTC reporting week, with office/programme breakdowns. Show real endpoint data, loading, no-report, zero-activity, and failure/retry states. Keep Valencia/EUR and Miami/USD separate and make the view readable to Laura/Elena. | S2-03 |
| S2-05 | Complete backfill/resume and late-event supersession validation after the refactor; exercise concurrent starts and worker restart. | Manual range accepts 1–52 completed Monday weeks, processed in order. Restart skips committed weeks and recomputes the failed week. Late events change the correct week without inflated counts; fingerprints, `recomputed_weeks`, and `supersedes_run_id` record the change. Manual/scheduled races and stale queued/running recovery cannot overlap loads. | S2-01/02, S1-07/08 |
| S2-06 | Complete freshness/silence alerts and eight-week baseline diagnostics; update the design with the resilience questions each enhancement answers. | Missed run beyond eight days, stale heartbeat, failed weekly run, rejection/reconciliation problems, and anomalous silence are observable. Missing-run detection executes independently of ETL. Insufficient baseline history is labelled explicitly. Optional alert delivery uses a non-critical subflow and cannot undo committed data. | S2-01/05 |
| S2-07 | Run API, PostgreSQL, Prefect, container, frontend, and end-to-end acceptance checks; publish `data/eval/weekly_performance/sprint2-report.md` and operating instructions. | Demonstrate trigger → subflows → database → API → dashboard, unchanged rerun, late-event correction, rollback/recovery, and optional-subflow failure. Capture dashboard evidence and preserved CLI execution, plus real commands/results with secrets/PII removed. | S2-01–06 |

### Subflow and transformation-task contract

Proposed names extend the existing design and must be recorded there during implementation. Keep subflows under `data/pipelines/weekly_office_program_performance/`; pure calculations remain in `data/process/weekly_performance/`.

| Subflow (`@flow`) | Explicit inputs → outputs |
| --- | --- |
| `extract_weekly_office_program_telemetry_flow` | Week bounds and source configuration reference → sanitized source rows, dimension scaffold, source counters. |
| `transform_weekly_office_program_performance_flow` | Source rows, dimensions, target week, validation configuration → KPI rows, rejection records, reconciliation. |
| `load_weekly_office_program_performance_flow` | Validated aggregates, rejection records, week, `run_id`, destination configuration reference → committed row count and checkpoint outcome. |
| `publish_weekly_performance_snapshot_flow` (optional) | Sanitized result/run summary and output configuration → snapshot outcome; failure observed via `return_state=True` in the main flow. |

Do not pass credentials as logged flow parameters or share mutable global state. Each critical subflow can run independently with explicit inputs and configured dependencies. The main flow retains run-level locking/finalization around their sequence.

The transform subflow invokes domain-named tasks for `compute_total_material_cost`, `count_kits_delivered`, `count_shortage_events`, and `count_cost_variance_events`, followed by assembly/zero-fill/reconciliation. Preserve `transform_weekly_performance` as the existing cached validation/normalization task boundary, returning reusable validated input for these KPI tasks; document its refined responsibility. Do not call nested Prefect tasks from inside that task. Isolated tests can call task `.fn` implementations; separate Prefect tests verify orchestration and caching.

`tests/pipelines/test_pipeline.py` must contain named, hand-calculated cases, for example:

- `test_total_material_cost_uses_quantity_and_decimal_cost`: two Valencia inbound events, `3 * 12.50 + 2 * 5.25`, produce `48.00 EUR`; variance events do not add spend.
- `test_kits_delivered_counts_events_not_units`: outbound quantities 10 and 2 produce count `2`, not `12`.
- `test_shortage_frequency_counts_captured_threshold_events`: two accepted threshold events, including stock quantity zero, produce count `2`.
- `test_cost_variance_frequency_counts_alerts`: one positive and one negative variance alert produce count `2`.
- Defensive and edge cases for every task: empty input yields the defined zero; malformed required values reject explicitly rather than corrupting totals. Validate currency separation and non-finite/nonnumeric costs in the appropriate transform boundary tests.

### Dashboard acceptance contract

- Page title: **Weekly Office & Programme Performance Report**. Show the actual `week_start` returned by the endpoint and the covered UTC week; allow selecting a completed Monday week.
- Use four clearly labelled tables/sections: **Material Cost per Office/Programme**, **Kits Delivered**, **Shortage Frequency**, and **Cost Variance Frequency**. Each identifies office and programme; cost is formatted in the row's currency with no cross-currency grand total.
- Explain "Kits Delivered counts delivery events" and that shortage/variance frequencies count captured alerts. Friendly office/programme labels may be added without changing API keys.
- A computed zero row displays zero; `404` displays "No report has been computed for this week"; authentication and service failures never masquerade as zero activity. Prevent stale responses from overwriting a newly selected week.
- Reuse `BackofficeShell`, existing authenticated API utilities, and current table styles. Review local Next.js guidance required by `uis/backoffice/AGENTS.md` before implementation.
- Automated tests cover fetch/format/state behavior; browser checks prove all four real KPI values, period selection, readability, and loading/empty/error states. Manual run controls in the UI are optional; the reporting endpoint is mandatory.

### Sprint 2 verification and exit gate

- [ ] Happy/edge/failure tests cover each endpoint's business behavior and permissions, not just HTTP status codes.
- [ ] Main flow in `pipeline.py` calls at least three independently executable subflows sequentially; optional subflow failure does not fail the valid report.
- [ ] `python -m pytest tests/pipelines/test_pipeline.py` passes without a database or external APIs; at least three transformation tasks are tested, including malformed input and hand-calculated KPI assertions.
- [ ] `python data/pipelines/pipeline.py` still completes after refactoring, using the existing entrypoint and deployed configuration.
- [ ] `/reporting` displays all four exact KPI names and the reporting period from real reporting-table data; frontend tests, lint/build, and browser checks pass.
- [ ] Race tests cover manual versus scheduled starts, worker adoption of queued rows, stale-run recovery, and dispatch uncertainty.
- [ ] PostgreSQL tests demonstrate full-week atomicity, unchanged rerun identity, late-event replacement, and multi-week resume after a later week fails.
- [ ] Run fingerprints include all KPI values/dimensions needed to detect cost-only as well as count changes; input cache fingerprints remain a separate concern.
- [ ] Freshness monitoring can detect a run that never started; silence warnings distinguish missing execution from a successfully computed zero week.
- [ ] Sanitized evidence includes report JSON, run metadata, cache-hit/miss evidence, recovery results, deployment schedule, and test command results.
- [ ] Runbook covers setup, CLI, manual trigger, schedule, backfill, failed-run investigation, worker restart, credentials/configuration names, and alert ownership.
- [ ] Shortage/variance emitter throttling, event-count delivery semantics, currency separation, and older-than-lookback limitations are documented for report consumers.
- [ ] Design describes the final subflow topology and links selected enhancements to its resilience questions; both ETL contexts are traced to implementation evidence.

## 5. Validation commands and evidence policy

These are planned commands, not checks already executed. Run them in the indicated working directory after the implementation and its environments exist.

| Working directory | Command / action | Purpose |
| --- | --- | --- |
| `data/pipelines` | `uv add "prefect>=3"` | Install the milestone's required orchestrator in the worker project. |
| Repository root, with configured worker environment active | `python data/pipelines/pipeline.py` | Verify the exact required CLI entry point. Document equivalent project-specific `uv` invocation during implementation. |
| `data/pipelines` | `uv run pytest -q` | Discover and run pipeline/pure-transform/Prefect tests through the worker project's pytest configuration. |
| Repository root, with configured worker environment active | `python -m pytest tests/pipelines/test_pipeline.py` | Required Part 3 isolated transformation tests; configure root imports/test discovery explicitly. |
| `backrooms/services` | `uv run pytest -q` | Run backend/reporting tests and existing API/telemetry regressions; add reporting suites to test discovery. |
| Repository root | `npx jest --runInBand` | Run frontend reporting-client/state tests and existing regression suites. |
| `uis/backoffice` | `npm run lint` and `npm run build` (separate commands) | Validate the dashboard and route build. |
| Repository root | `docker compose config -q` | Validate deployment wiring; follow with actual API/worker build, import, and runtime checks. |
| Repository root | `git diff --check` | Check patch whitespace before handoff. |

Configure a disposable PostgreSQL test database and clearly identify any integration suites requiring it. Synthetic events belong in isolated test databases, not production telemetry. Evidence must state whether a check was unit, integration, container, or live execution; skipped checks are not passes. Functional changes include happy, edge, and failure tests under the repository test-coverage rule.

## 6. Requirement traceability

| Available requirement | Planned work / evidence |
| --- | --- |
| Named flow, independent extract/transform/load tasks with explicit I/O | S1-01, S1-03–06; CLI and Prefect execution evidence. |
| Optional step invoked with `return_state=True`; failure does not interrupt publication | S1-06/09, S2-01/07; injected task and optional-subflow failures. |
| Retries and retry-delay settings for external I/O, with justification | S1-03/05/06/07 and S2-06 where applicable; transient/exhaustion tests. |
| Expensive transformation uses `cache_key_fn` and `cache_expiration`; reuse within one hour | S1-06/09, S2-01/02; identical-input hit, changed-input miss, expiry tests. |
| Idempotent destination load keyed by briefing unique grain | S1-05/09, S2-05; repeated execution and partial-failure rollback evidence. |
| At least five execution metadata fields, including errors | S1-02/05/06; full designed run log and failure evidence. |
| `pipeline.py` and documented direct script invocation/schedule | S1-01/08/09, S2-01/07; CLI preserved across refactor and deployment evidence. |
| Exact four KPIs, schema, event names, and briefing response contract | S1-02–05/07, S2-02/04; DDL comparison and golden KPI assertions. |
| Three endpoints in a separate reporting module importing pipeline functions | S1-07/08/09; API and dependency-direction checks. |
| Existing telemetry source and engineering report preserved | S1-09, S2-07; source immutability assertions and regression suite. |
| Design recovery, locks, quarantine, late events, backfill, observability | S1-02/05/06 and S2-05–07; PostgreSQL and operational failure demonstrations. |
| At least three domain-named subflows with explicit I/O, independently reusable | S2-01/07; main-flow topology and independent execution tests. |
| Optional steps extracted into subflows and called with `return_state=True` | S2-01/06/07; optional snapshot/alert failure tests. |
| Root `tests/pipelines/test_pipeline.py`, isolated tests of at least three transformation tasks | S2-02; exact pytest command, in-memory inputs, malformed input, hand-calculated KPIs. |
| Mandatory business dashboard with every exact KPI label, period, and real API data | S2-03/04/07; frontend assertions and stakeholder-readable browser evidence. |
| Additional design enhancements documented with rationale | S2-06; map heartbeat/silence/locking improvements to design questions 16.4, 16.7, and 16.10. |

## 7. Delivery boundary and priorities

The critical path is S1-01 → schema/extraction → transformation → transactional load → resilient flow → reporting endpoints/worker → Sprint 1 gate → subflows and dashboard → final acceptance. Tests and documentation ship with their corresponding work items. Suggested ownership: pipeline engineer for ETL/subflows, backend engineer for API/deployment, frontend engineer for dashboard, and shared QA/business review for handoff.

The optional daily reconcile deployment (`0 3 * * *` UTC, trailing four complete weeks) is stretch work after both sprint gates. New telemetry fields, currency conversion, and exactly-once HTTP trigger keys require separate scope decisions. The dashboard and three-subflow topology are mandatory Sprint 2 deliverables; the required optional-failure demonstration task is mandatory in Sprint 1 and becomes an optional subflow in Sprint 2.

**Handoff is ready when:** both contexts' criteria and the implemented design are evidenced, the CLI and isolated test commands pass, the operational runbook is usable, and Laura/Elena can read all four real KPIs in `/reporting`. This planning document does not claim that any pipeline feature has been implemented.
