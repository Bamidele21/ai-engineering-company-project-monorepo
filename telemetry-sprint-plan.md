# Nexova Telemetry — Three-Sprint Delivery Plan

- **Status:** Proposed implementation plan
- **Planning date:** 2026-10-21
- **Cadence:** Three sequential sprints; 

## 1. Objective and source requirements

Deliver a working telemetry path for Nexova's backoffice: capture technical and inventory events, persist validated batches in Supabase, and expose a cached technical report for Sergio Molina's engineering team. Inventory capture supports future analysis of Elena's training materials and Patricia's onboarding kits across Valencia and Miami; executive/business reporting belongs to the later Data Pipelines milestone.

| Sprint | Primary requirement source | Outcome |
|---|---|---|
| 1 — Capture | [telemetry1-context.md](./telemetry1-context.md) | Backoffice events reach a validating FastAPI stub through a shared, batched transport. |
| 2 — Storage | [telemetry2-context.md](./telemetry2-context.md) | The same endpoint persists valid events using one bulk insert and rejects invalid events individually. |
| 3 — Technical reporting | [telemetry3-context.md](./telemetry3-context.md) | At least three operational metrics are calculated with Pandas and served through a 60-second cache. |

Supporting contracts:

- [Nexova telemetry briefing](./docs/telemetry/nexova-telemetry-briefing.md): mandatory events, inventory dimensions, currency rules, and suggested demonstration data.
- [Existing telemetry plan](./docs/telemetry/telemetry-plan.md): 22-event catalogue, instrumentation points, and enabling changes EC1–EC10.
- [Event schemas](./docs/telemetry/event-schemas.json): normative event identifiers, envelope, types, and property allowlists.

Repository paths below use `backrooms/services/` for the contexts' generic `services/` directory. Frontend scope is `uis/backoffice/`; related business changes belong in the Inventory API, Supply Directory API, and incident analyzer as needed. This document schedules future work; it does not assert that capture, storage, or reporting is already implemented.

## 2. Decisions and prerequisites to close in Sprint 1

The approved catalogue predates the three implementation contexts. Resolve these differences in task T1.1 and record the resulting contract in `docs/telemetry/telemetry-plan.md` and, where necessary, `event-schemas.json` **before freezing the Sprint 1 model**.

| Issue | Evidence and planned resolution |
|---|---|
| Transport cadence | The old plan specifies 30-second browser batching, `pagehide` keepalive, and a daily delivery window. The capture context requires **10 seconds or 20 events**, `visibilitychange` with `sendBeacon`, and at most three retries. Use the capture requirements for transport; stream/batch labels describe downstream processing priority and must not cause one HTTP request per captured event. |
| Authoritative business events | The catalogue assigns mandatory inventory events to the backend; the capture context asks for every mandatory event to flow from the backoffice through `track()`. Agree a bridge for backend-confirmed facts into the browser batch, or explicitly revise emitter ownership. The bridge must expose threshold/variance/rejection facts, preserve correlation, and avoid double emission. Backend-only direct-edit attempts also need a documented capture path. This is a blocking architecture decision, not permission to omit mandatory events. |
| Session lifecycle | The old contract uses a per-tab `sessionStorage` UUID; the new context requires a session generated at login and held in session memory. Define an anonymous pre-login session for login failures/navigation, rotate on successful login, and clear authenticated identity on logout/expiry. Reconcile reload behavior in the catalogue before implementation. |
| Envelope fields | Preserve the eight context fields **plus the existing required `source` field**. Use catalogue versions from shared constants. Finalise the model in Sprint 1 and reuse it unchanged in Sprint 2. |
| Authentication examples | Catalogue names are `login_failed` and `login_succeeded`, not the report context's example `user_login_*` names. Its failure reasons are backend-specific, whereas capture suggests `invalid_credentials`, `session_expired`, and `network_error`. If the optional auth activity is selected, reconcile and version the reason allowlist before emission; do not expose account-existence details just to populate telemetry. |
| Performance coverage | `api_latency_recorded` captures only requests taking at least 500 ms and is throttled. It cannot represent overall API latency. Use `page_view.load_duration_ms` for baseline page-load timing and label any API analysis as **sampled slow-request latency**. Web Vitals require an explicit schema addition before capture. |
| Mandatory inventory prerequisites | The existing plan records missing programmes, cost/currency fields, minimum-stock configuration, direct-edit rejection hooks, and category alignment. Re-check EC3–EC7 against current code, then implement only the missing pieces. Never fabricate these values in events. |

The memory bank flags `projectbrief.md` as stale, and `techContext.md` incorrectly describes the now-populated root `CONTEXT.md` as a placeholder. Use the source documents above and current scoped context for implementation decisions. Re-check file locations rather than relying on historical line numbers.

## 3. Sprint 1 — Capture and validate events

### Goal

Demonstrate Nexova business and cross-cutting technical events reaching `POST /telemetry/events` in batches, with no telemetry database writes.

### Ordered backlog

| ID | Work item | Deliverable / acceptance criteria | Dependency |
|---|---|---|---|
| T1.1 | Reconcile and freeze the contract | Close the decisions in section 2; create an event-to-hook coverage checklist; define session/request correlation, emitter ownership, allowlists, and schema-version constants. | Source review |
| T1.2 | Enable mandatory inventory facts | Implement missing EC3–EC7: programme linkage/backfill, Nexova categories, `min_stock`, inbound unit cost/local currency, rejection hooks, and threshold/variance calculations. Update affected form/API contracts in this sprint. | T1.1 |
| T1.3 | Build the FastAPI receiver stub | Add a dedicated telemetry package/router under `backrooms/services/telemetry/`, registered in the selected host API. Define `TelemetryEvent`, accept `{ "events": [...] }`, validate format, log only event count/types, and return HTTP 200 with `{ "received": N }`. No telemetry persistence. | T1.1 |
| T1.4 | Implement the shared frontend service | Add an equivalent of `uis/backoffice/lib/telemetry/telemetry.ts` exposing `track(eventType: string, properties: Record<string, unknown>): void`; implement the queue, automatic envelope, batch timer/threshold, lifecycle flush, and retries described below. | T1.1, T1.3 |
| T1.5 | Connect business and technical hooks | Instrument all five mandatory events and the baseline below. Use central navigation, error, and API/auth hooks instead of duplicating tracking logic across pages. Implement the agreed authoritative-event bridge. | T1.2, T1.4 |
| T1.6 | Verify capture and assemble evidence | Run happy/edge/failure tests, inspect real browser batches, document instrumented/deferred events, and capture a redacted DevTools screenshot with a 200 response. | T1.5 |

Use a `telemetry/` package rather than the old plan's proposed sibling `telemetry.py`, so Sprint 3 can add `analysis.py` without a module/package naming collision. Select the host API in T1.1 and retain its public URL through Sprint 2.

### Transport contract

- Accumulate events in memory; flush at 20 events or no later than 10 seconds after pending work begins. Repeated captures must not postpone the timer indefinitely.
- Generate `eventId` at capture time, ISO 8601 UTC `timestamp`, session/user identity, `schemaVersion`, `requestId`, and `source` inside the service or agreed internal adapter. Components pass only event type and allowed properties. Preserve IDs and capture timestamps on retry.
- Keep the in-flight batch separate from newly queued events. Use an initial send plus at most three retries with exponential delay, then discard the exhausted batch without interrupting the user's workflow.
- On `visibilitychange` to hidden, flush using `navigator.sendBeacon`; check its return value and define fallback behavior. Beacon is best-effort: browser termination/offline delivery is not guaranteed, and acceptance by the browser is not a server acknowledgement.
- Configure `NEXT_PUBLIC_TELEMETRY_ENDPOINT` and declare/read backend `TELEMETRY_ENDPOINT`. Document examples in `.env.example`; configure actual environments during setup. Test the chosen JSON content type, CORS, and authentication strategy with Beacon, which cannot attach arbitrary authorization headers.
- The frontend treats HTTP success as acknowledgement and does not depend on the response body's shape. All browser telemetry transport lives in the service; telemetry delivery failures must not recursively emit telemetry requests.

### Required event coverage

| Event / category | Capture criteria |
|---|---|
| `inbound_order_created` | Emit only after a confirmed inbound order; include the catalogue's programme, supplier, unit cost, order ID, and local currency dimensions. |
| `outbound_order_created` | Emit only after a confirmed outbound order; retain `exit_type` and order ID, never `assigned_to`. |
| `stock_threshold_triggered` | Emit on `previous_stock >= min_stock > new_stock`, with the catalogue throttle; remaining below the threshold is not a new crossing. |
| `direct_stock_edit_rejected` | Capture rejected direct-stock modification attempts while preserving the prohibition on direct edits. Use route templates and the schema's nullable unresolved-asset dimensions. |
| `kit_cost_variance_detected` | Compare the new unit cost to prior history for the same material/supplier, excluding the new order; emit only above 10% absolute variance. First purchase has no comparison. |
| Navigation | Capture `page_view` centrally across overview, inventory, suppliers, incidents, and auth routes; strip queries/tokens. |
| Frontend errors | Capture uncaught errors and unhandled rejections via `frontend_error_captured`; sanitise messages and apply catalogue throttles. |
| Performance | Capture valid `page_view.load_duration_ms` for actual document navigation, and prioritise `api_latency_recorded` for relevant slow calls. Do not label the initial document timing as the timing of every client-side route transition. |
| Additional coverage | Prioritise `validation_failed`, `network_request_failed`, and `outbound_order_rejected` for coverage across validation, errors, and business categories. |

Every mandatory inventory event carries `office`, `product_id`, `product_category`, `programme_id`, `quantity`, and `currency` with event-specific semantics. Offices are `valencia`/`miami`; currencies remain EUR/USD respectively; categories are `training_kit`, `certification`, or `onboarding_equipment`. Preserve the catalogue's explicit nullable exceptions.

The remaining catalogue events stay on an explicit opportunity backlog: `product_created`, `supplier_rate_edited`, `incident_report_analyzed`, `login_succeeded`, `login_failed`, `session_expired`, `password_reset_requested`, `password_reset_failed`, `user_registered`, `admin_role_changed`, and `form_abandoned`. Add these in Sprint 1 as capacity allows after required coverage. Document every deferral; do not move required capture work into the backend-only storage sprint.

**Optional activity:** Web Vitals with route dimensions and centrally captured authentication events. If the daily authentication report is selected for Sprint 3, both login outcome events become Sprint 1 dependencies.

### Validation and exit gate

- **Happy:** valid events receive automatic envelope fields; 20-event batches and the 10-second flush reach the stub; successful inventory writes emit the correct facts.
- **Edge:** empty queues, events arriving during a send, repeated lifecycle events, anonymous-to-authenticated session transitions, threshold equality, exactly 10% variance, and first-purchase history behave as defined.
- **Failure:** malformed events, disallowed properties, transport failures, exhausted retries, Beacon refusal, rejected inventory writes, and error-message PII are handled deliberately.
- Add meaningful Jest and pytest coverage for each functional change; run affected frontend lint/build and backend tests. Assert no business event is emitted twice for one action.
- Exit only when **all five mandatory events**, errors, navigation, and at least one performance metric have demonstrated capture; the stub persists nothing; no passwords, emails, names, reset tokens, or submitted form values appear in payloads.
- Evidence: event/hook checklist, test results, representative payloads, DevTools screenshot, and optional-activity status. Required PR title from the context: `feat: telemetry event capture`.

## 4. Sprint 2 — Validate individually and persist in Supabase

### Goal and entry gate

Replace the receiver internals with real persistence while retaining the endpoint URL, Sprint 1 `TelemetryEvent` model, and every frontend source line. Sprint 1 must be accepted before storage work starts.

### Ordered backlog

| ID | Work item | Deliverable / acceptance criteria | Dependency |
|---|---|---|---|
| T2.1 | Create storage and mapping | Inspect the intended Supabase project's schema; add a reproducible migration for the eight columns and three indexes below. Document envelope-to-row mapping in `docs/telemetry/telemetry-plan.md`. | Sprint 1 exit |
| T2.2 | Implement per-event validation | Accept a loose outer envelope with an `events` array; call the unchanged `TelemetryEvent.model_validate(raw)` per item and enforce catalogue event/version/property allowlists. Count invalid items without cancelling valid siblings. | T2.1 |
| T2.3 | Implement bulk persistence | Map valid events and insert them in **one bulk operation/transaction per batch**. Return HTTP 200 with `{ "received": N, "stored": M, "rejected": R }` after successful handling. | T2.2 |
| T2.4 | Prove compatibility and partial acceptance | Exercise the existing frontend unchanged, mixed batches, database failure, and immutable storage. Verify rows directly in Supabase. | T2.3 |
| T2.5 | Prepare real report data | Generate at least 20 real backoffice events, including inbound/outbound activity and at least one technical event; record counts/type distribution for the Sprint 3 handoff. | T2.4 |

### Storage contract

| Column | Type / default | Mapping |
|---|---|---|
| `id` | `uuid` primary key; default `gen_random_uuid()` | Database record ID; do not silently equate it with envelope `eventId`. |
| `timestamp` | `timestamptz NOT NULL` | `event.timestamp` |
| `service` | `text NOT NULL` | Map `source=web` to `backoffice`; preserve documented API-source distinctions for server-origin events. |
| `event_type` | `text NOT NULL` | Exact catalogue identifier |
| `level` | `text DEFAULT 'info'` | Explicit event-to-severity mapping; record which types count as errors in Sprint 3. |
| `value` | `numeric NULL` | Only a documented numeric event property, such as `duration_ms`; otherwise null. |
| `message` | `text NULL` | Optional sanitised summary; never raw request/error content. |
| `tags` | `jsonb DEFAULT '{}'` | Validated allowlisted `properties`; preserve flat dimensions for report extraction. |

Add separate indexes on `timestamp` and `event_type`, plus a GIN index on `tags`. Events are append-only: introduce no UPDATE/DELETE application operations. Define access for ingestion and report reads without granting browser database writes.

Decide before T2.3 whether to retain `eventId`, `sessionId`, `userId`, `schemaVersion`, and `requestId` as reserved storage metadata in `tags`, as permitted by the storage context. Document their exact mapping separately from event-property allowlists. Also document duplicate-delivery semantics: retries/Beacon can duplicate facts unless a deliberate idempotency policy is implemented; do not claim exactly-once storage by default.

### Response behavior and validation

- Never declare the request body as `events: list[TelemetryEvent]`: that would reject the entire batch before the handler can perform partial validation. Non-object items in a parseable array count as individually rejected events.
- For successful processing, `received = stored + rejected`. Empty batch returns all zeroes; all-invalid batch returns zero stored and no database insert. A malformed outer envelope receives a validation error rather than a misleading success.
- Database failure is a server failure, not an event-validation rejection. Roll back the bulk transaction and return an appropriate non-2xx response so existing retry behavior remains effective; never report rows as stored before commit.
- **Happy:** all-valid batch is stored with one bulk call and correct types/dimensions; existing backoffice works without edits.
- **Edge:** empty, all-invalid, mixed, null optional fields, non-object items, and replayed batches follow documented semantics.
- **Failure:** unsupported events/versions, missing required dimensions, unexpected properties, and database unavailability produce the expected rejection or failure without silently losing valid siblings.
- Exit evidence: migration/index inspection, pytest results, mixed-batch request/response, direct Supabase row checks, and a frontend diff confirming no changes in this sprint. Include at least one real inbound, one real outbound, and one technical event.
- Report handoff requires **at least 20 real rows**. Aim for the briefing's richer demonstration set: 6–8 materials, three programmes, 12–15 inbound and 12–15 outbound orders across both offices, two threshold crossings, and one cost variance. Generate activity through real workflows rather than inserting fabricated telemetry rows.

## 5. Sprint 3 — Cached technical analysis and report endpoint

### Goal and entry gate

Turn persisted telemetry into temporally grouped engineering metrics. Begin only after Sprint 2 has supplied at least 20 real events with multiple event types and at least one technical event.

### Ordered backlog

| ID | Work item | Deliverable / acceptance criteria | Dependency |
|---|---|---|---|
| T3.1 | Define metric populations | Document eligible event types, dimensions, severity mapping, numeric units, denominators, and missing-data behavior for each metric below. | Sprint 2 data handoff |
| T3.2 | Build analysis functions | Add `backrooms/services/telemetry/analysis.py` with at least three independent metric functions accepting explicit `start_date` and `end_date`. Keep calculations outside the router. | T3.1 |
| T3.3 | Add report endpoint | Implement `GET /telemetry/report`, validate optional ISO 8601 date parameters, resolve one UTC window, and return `{ "period": { "from": "...", "to": "..." }, "metrics": { ... } }`. | T3.2 |
| T3.4 | Add 60-second caching | Cache successful report results by resolved UTC start/end; equivalent requests reuse the result without running queries/aggregations again. | T3.3 |
| T3.5 | Validate and demonstrate | Compare metrics against known fixtures and real stored events, verify cache behavior, and capture a representative JSON report with its period. | T3.4 |

### Core metric definitions

| JSON key / function | Operational question | Population and aggregation |
|---|---|---|
| `events_per_day` | Which event types dominate, and how does volume change each day? | SQL filters the explicit captured catalogue types and requested window; Pandas counts by UTC day and `event_type`. Business-event counts here describe system activity, not commercial outcomes. |
| `error_rate_by_type` | What share of captured activity is classified as an error, and which types contribute? | Load the complete declared event population for the denominator in one filtered query. Compute daily total counts and daily error counts by type; return counts and `error_count / daily_total` by day/type. Label this as a **captured-event error share**, not a failed-request rate. |
| `page_load_latency_by_day` | How does observed backoffice document-load time vary by route and day? | SQL selects `page_view` in the window; extract `page_path` and `load_duration_ms`, discard missing/invalid measurements, and calculate mean milliseconds and sample count by UTC day/route. |

If using `api_latency_recorded` instead of page-load timings, expose a clearly named slow-request metric grouped by day, service, and route template. Explain the >=500 ms threshold and throttling bias; do not present it as overall API response time. Ensure real performance observations exist before demoing either metric.

### Pipeline and period contract

1. **Load in SQL:** parameterise `timestamp >= :start AND timestamp < :end` and `event_type = ...` or `IN (...)`. Never load the whole telemetry table and filter it later. Ratio metrics load numerator and denominator populations together.
2. **Refine in Pandas:** extract required `tags` dimensions, drop null dimensions for the relevant metric, coerce numeric observations, and apply metric-specific predicates across all dimension values.
3. **Convert types:** call `pd.to_datetime(df['timestamp'], utc=True)` before temporal grouping; derive UTC day from the converted column.
4. **Group and aggregate:** use vectorised `groupby`, `agg`, `count`, `sum`, and `mean`; no row loops for metric calculations. Define zero-denominator behavior without NaN/Infinity.
5. **Serialise:** return `.reset_index().to_dict(orient='records')` with JSON-safe dates/numbers. Empty populations return predictable empty arrays. Functions have no writes or shared mutable calculation state; repeatability assumes unchanged source rows.

The endpoint owns the window. With neither parameter supplied, resolve `end_date = now` and `start_date = now - 7 days`, both UTC. For a single supplied bound, use a documented seven-day window anchored to that bound. Reject malformed or reversed/empty ranges; normalise explicit timezone offsets to UTC. Pass the same resolved window to every function, without a second relative-date filter in Pandas.

For explicit dates, the cache key is the normalised `(start_date, end_date)` pair. For omitted dates, reuse a cached resolved default window for its 60-second lifetime; computing a fresh `now`-based key on every request would defeat caching. Return the actual cached period. Different periods must never share cached results. A failed calculation must not be cached as successful empty data.

### Validation, optional activities, and exit gate

- **Happy:** fixtures with known counts/errors/timings produce correct daily groups, ratios, route means, and JSON output; identical windows hit the cache.
- **Edge:** inclusive start/exclusive end, timezone offsets across midnight, empty windows of data, null dimensions, missing performance samples, zero denominators, single-bound requests, and TTL expiry behave consistently.
- **Failure:** invalid dates, failed database reads, malformed stored values, and pipeline errors produce deliberate behavior rather than misleading zero metrics. Verify SQL predicates and that a cache hit skips queries/calculation.
- **Optional authentication metric:** add `auth_failure_rate` using the actual catalogue types `login_failed / (login_failed + login_succeeded)` by UTC day; load both types together. This depends on capturing both outcomes in Sprint 1 and documenting any throttling bias.
- **Optional dashboard:** add `/telemetry` in `uis/backoffice/`, showing a chart or simple table per metric, the current `from`/`to` period, and loading/empty/error states. Keep it an engineering view of the same API metrics.
- Exit only when three independent operational metrics, SQL filtering, UTC grouping, JSON serialisation, and 60-second cache behavior are verified. No revenue, conversion, or executive KPI calculations are included.
- Evidence: metric definitions/questions, tests, real-data JSON, cache-hit/expiry demonstration, and optional-activity status. Required PR title from the context: `feat: telemetry report endpoint`.

## 6. Delivery controls and dependency summary

**Critical path:** contract decisions → mandatory inventory prerequisites → capture/stub demonstration → storage migration → partial validation/bulk insert → 20+ real events → analysis functions → report endpoint → cache verification.

- Treat Sprint 1 enabling changes as committed scope, not invisible setup. If capacity is tight, defer opportunity events and optional activities first; do not weaken mandatory coverage or push frontend contract work into Sprint 2.
- Reuse the repository's Jest and pytest conventions. For each functional change, cover happy, edge, and failure behavior; run relevant lint/build/tests and record results in `memory-bank/progress.md`.
- Reuse `backrooms/services/cache.py` for reporting if its TTL/key behavior fits; account for its process-local scope. Each worker may hold its own cache.
- Confirm the intended Supabase project before migrations: the memory bank records a historical mismatch between the MCP project and the application's database. Validate against the actual target, preferably locally first.
- Protected `.env`, `infra/**`, and other paths listed in `AGENTS.md` require explicit confirmation before edits. Environment examples can document setup without embedding credentials.
- Review and merge each sprint through the repository workflow before basing the next sprint on it. PR creation, commits, and merges are separate execution actions, not performed by this planning document.

### Final completion checklist

- [ ] Sprint 1: all mandatory inventory events plus cross-cutting errors, performance, and navigation captured through the agreed contract and batched transport.
- [ ] Sprint 2: eight-column immutable table, three indexes, per-event rejection, one bulk insert, unchanged frontend/model/URL, and at least 20 real events.
- [ ] Sprint 3: at least three independent Pandas metrics, SQL-side time/type filtering, UTC grouping, JSON report, and verified 60-second cache.
- [ ] Evidence, schema/mapping decisions, optional work, deferred opportunities, and known delivery/sampling limitations documented.
