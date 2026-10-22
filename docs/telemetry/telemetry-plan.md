# Nexova Telemetry Plan

- **Version:** 1.0
- **Date:** 2026-10-18
- **Project:** Nexova — Telemetry series, milestone 1 of 4 (Plan · Capture · Storage · Report)
- **Paired deliverable:** [`event-schemas.json`](./event-schemas.json) — the normative, machine-readable schema catalogue. This document holds the rationale, the instrumentation points, and the delivery strategy. Where a schema detail differs, the JSON wins.

---

## 1. Purpose and how to read

Management filed an RFI: can the production inventory system generate actionable business information — not just about inventory, but about any part of the application a user or internal process touches? This plan is the response. It identifies, as exhaustively as possible, what data is worth capturing today and what could be valuable tomorrow, **before a single line of instrumentation is written**.

**Scope (in):** the Nexova backoffice web app (`uis/backoffice`) and its three APIs: `Inventory-API` (port 8001), `Supply_directory_API` (port 8000), `analyzer-api`. The website, talent-pipeline-tracker, and landing page are out of scope (see §11).

**Conventions:**

- `event_type` strings are exact identifiers — they appear verbatim in this document, in `event-schemas.json`, and in any future capture code. They follow `entity_action` with past-tense verbs (§3).
- `MUST` / `MUST NOT` carry their usual RFC meaning.
- Every event's `hypothesis` and `decision` has **identical wording** in this document and in `event-schemas.json`. Here they appear completing the sentence **We capture `event_type` because {hypothesis}, which allows us to make the decision to {decision}** — the first letter's case is adapted to sentence position and the hypothesis's trailing period yields to the sentence's comma. The cross-document check in §5.5 verifies this mechanically.
- Instrumentation points cite `file:line` against the working tree on 2026-10-18 (branch `telemetry-operations`). Some events require *enabling changes* (§9) — net-new code without which the event cannot fire today.
- This milestone defines the **emission contract** only. Capture, storage, and reporting are later milestones; the delivery class (stream/batch) is fixed here, the transport is described but not built.

---

## 2. System under measurement

### 2.1 Services

| Service | Port | Stack | Data store | Auth |
|---|---|---|---|---|
| backoffice web app | 3000/3001 | Next.js 16.3, React 19.2, TypeScript 5 | — | JWT in `localStorage` (`nexova.auth.token`) |
| Supply Directory API | 8000 | FastAPI 0.141, Pydantic 2.13 | TinyDB JSON files | JWT bearer HS256, no refresh tokens |
| Inventory API | 8001 | FastAPI, SQLModel / SQLAlchemy 2.1 | Supabase PostgreSQL (psycopg2) | JWT on **writes**; reads are public |
| Incident Analyzer API | 8000 (compose) | FastAPI | in-memory | none (public) |

### 2.2 Entity mapping (briefing → code)

| Briefing entity | Code | Notes |
|---|---|---|
| `Product` | `Asset` (`Inventory-API/models.py:22-29`, table `assets`) | Category per briefing: `training_kit` / `certification` / `onboarding_equipment` (today: different literals — EC7) |
| `InboundOrder` | `AssetEntry` (`models.py:32-41`, table `asset_entries`) | No unit cost / currency today — EC5 |
| `OutboundOrder` | `AssetExit` (`models.py:44-54`, table `asset_exits`) | `exit_type`: `allocation` / `consumption` |
| `office` | `Asset.office` (`"Valencia"` / `"Miami"` today; emitted lowercase per briefing) | Valencia → EUR, Miami → USD |
| `programme` | **does not exist yet** — EC6 | Required by the briefing in every inventory event |

**The business rule.** Stock is never stored and never modified directly. It is always *derived* (`Inventory-API/routers/inventory.py:35-51`: inbound minus outbound), and every modification goes through an `InboundOrder` or `OutboundOrder` traceable to a user (`user_uuid` stamped at `inventory.py:123` and `:149`). This rule is why `direct_stock_edit_rejected` is a mandatory metric.

### 2.3 Inventory flow walkthrough — instrumentation points

```
operator ──login──▶ Supply Directory API (/auth/login)
                        │  [P1] login_succeeded / login_failed
                        ▼
backoffice (AuthGuard session check on every route change)
   │  [P2] session_expired (client) · page_view (every route)
   ▼
products list ──▶ GET /inventory/products
   │  [P3] api_latency_recorded (≥500 ms) · page_view
   ▼
inbound order form ──▶ POST /inventory/orders/inbound
   │  [P4] validation_failed (client rules) → inbound_order_created
   │      + kit_cost_variance_detected (post-commit check)
   ▼
outbound order form ──▶ POST /inventory/orders/outbound
   │  [P5] validation_failed → outbound_order_created
   │      or outbound_order_rejected (insufficient stock, 400)
   │      or stock_threshold_triggered (post-commit edge check)
   ▼
order history ──▶ GET /inventory/orders
   │  [P6] api_latency_recorded (unbounded read, in-Python sort)
   ▼
direct stock edit attempt ──▶ PUT/PATCH/DELETE /inventory/products*
        [P7] direct_stock_edit_rejected (EC3 stub routes)
mid-request token expiry ──▶ get_current_user
        [P8] session_expired (server, EC2 expiry split)
```

| # | Point | Where it fires | Events |
|---|---|---|---|
| P1 | Login attempt (success or failure) | `Supply_directory_API/routes/auth.py:62-87` | `login_succeeded`, `login_failed` |
| P2 | Session check on route change | `uis/backoffice/components/auth/AuthGuard.tsx:22-39` | `session_expired` (client), `page_view` |
| P3 | Products list load | `Inventory-API/routers/inventory.py:72-82` (+ 15 s cache `:30-31`) | `api_latency_recorded` |
| P4 | Inbound order submit | FE `uis/backoffice/app/inventory/orders/inbound/page.tsx:74-117` → BE `inventory.py:116-128` | `validation_failed` (FE 79-94), `inbound_order_created` (after :126), `kit_cost_variance_detected` (EC5) |
| P5 | Outbound order submit | FE `.../outbound/page.tsx:86-131` → BE `inventory.py:131-154` | `validation_failed` (FE 91-106), `outbound_order_created` (after :152), `outbound_order_rejected` (400 at :139-147), `stock_threshold_triggered` (EC4) |
| P6 | Order history view | `inventory.py:157-199` | `api_latency_recorded` |
| P7 | Direct stock edit attempt | NEW stub routes (EC3) in `inventory.py` | `direct_stock_edit_rejected` |
| P8 | Expired token during a request | `Supply_directory_API/auth/dependencies.py:13-31` | `session_expired` (server, EC2) |

### 2.4 Verified gaps — where mandatory events have no hook today

| Gap | Evidence | Consequence | Fix |
|---|---|---|---|
| No direct-stock-edit route | `inventory.py` defines no `PUT`/`PATCH`/`DELETE` on products; attempts hit generic FastAPI 405 with no hook | `direct_stock_edit_rejected` cannot fire | **EC3** stub routes that reject and emit |
| No minimum-stock threshold in the backend | no `min_stock` in `models.py:22-29` / `schemas.py:23-27`; the only threshold is client-side `uis/backoffice/lib/inventory.ts:82` (`LOW_STOCK_THRESHOLD = 10`) | `stock_threshold_triggered` cannot fire | **EC4** |
| No unit cost / currency on orders | `AssetEntryCreate` (`schemas.py:39-43`) and `AssetEntry` (`models.py:32-41`) have no cost fields | `kit_cost_variance_detected` cannot fire | **EC5** |
| No programme entity | no `Programme` model anywhere | `programme_id` unavailable for every mandatory event | **EC6** |
| Category literal mismatch | `schemas.py:13-18`: `hardware/peripherals/office_supplies/training_materials`; briefing requires `training_kit/certification/onboarding_equipment` (FE mirror: `lib/inventory.ts:9-13`) | briefing taxonomy cannot be emitted | **EC7** |
| Office casing | `schemas.py:19`: `"Valencia"`/`"Miami"`; briefing wants lowercase `valencia`/`miami` | lowercase mapping needed at emission | **EC1** (shared emitter) |
| Expired vs invalid token indistinguishable | `auth/dependencies.py:13-21` — both collapse into `ValueError` from `decode_access_token` (`auth/security.py:67-75`) | `session_expired` (server) cannot fire | **EC2** |
| No request-ID middleware, no exception handlers, no event logging | CORS is the only middleware (`Inventory-API/main.py:51-57`) | envelope `requestId`, `api_latency_recorded`, server-side `validation_failed` need new infrastructure | **EC1**, **EC8** |

---

## 3. Event taxonomy and naming rules

- **Format:** `entity_action`, past tense, snake_case. Regex: `^[a-z][a-z0-9]*(_[a-z][a-z0-9]*)+$`.
- **Verb vocabulary (closed set):** `created`, `rejected`, `triggered`, `detected`, `recorded`, `captured`, `failed`, `expired`, `changed`, `edited`, `abandoned`, `registered`, `requested`, `analyzed`, `viewed`.
- **Categories:** `business/inventory`, `authentication`, `navigation`, `performance`, `errors`, `validation`.
- **Classification:** `mandatory` (required by the Nexova briefing from day one) or `opportunity` (proposed by this plan).
- **Delivery:** `stream` (real-time) or `batch` (periodic) — decided in §6 by business urgency, never by technical preference.

---

## 4. Phase 1 — Event catalogue

### 4.1 Mandatory metrics (from `nexova-telemetry-briefing.md` §3 — the floor)

These five events are non-negotiable. Hypotheses and decisions are the briefing's own wording.

#### `inbound_order_created` — business/inventory · mandatory · stream

Fires when a new batch of training or onboarding material arrives from a supplier.

- **We capture `inbound_order_created` because** we need to know how much material is being produced/purchased, for which programme, and at what cost, **which allows us to make the decision** to plan material production based on expected enrolment demand (Elena).
- **Emitter:** `Inventory-API/routers/inventory.py` `create_inbound_order` (:116-128) — emit after `session.refresh(entry)` (:126), before the return (:128). Requires EC5, EC6.
- **Allowlist (required):** `office`, `product_id`, `product_category`, `programme_id`, `quantity` (int > 0), `currency`, `supplier`, `unit_cost`, `order_id`.
- **PII:** none — `supplier` is a company name; the acting user is the envelope `userId`.

#### `outbound_order_created` — business/inventory · mandatory · stream

Fires when a kit or certificate is delivered to a client, candidate, consultant, or agent.

- **We capture `outbound_order_created` because** we need to know which programmes consume the most material, and at what rate, **which allows us to make the decision** to anticipate restocking needs before a large enrolment wave (Elena).
- **Emitter:** `inventory.py` `create_outbound_order` (:131-154) — emit after `session.refresh(exit_record)` (:152), before the return (:154). Requires EC6.
- **Allowlist (required):** `office`, `product_id`, `product_category`, `programme_id`, `quantity` (int > 0), `currency`, `exit_type`, `order_id`.
- **PII:** `assigned_to` MUST NOT be captured — not even as a presence flag. The briefing bans candidate, client, and consultant names in properties; `exit_type` is the only allocation signal.

#### `stock_threshold_triggered` — business/inventory · mandatory · stream

Fires when the stock of a material item falls below the configured minimum.

- **We capture `stock_threshold_triggered` because** we need to know how often a programme runs out of available material, **which allows us to make the decision** to adjust the minimum threshold or speed up reprinting/reproduction of that material.
- **Emitter:** `inventory.py` `create_outbound_order` — post-commit edge check comparing pre-commit `available` (:138) with post-commit stock; emit only on the crossing `previous_stock >= min_stock > new_stock`. Requires EC4, EC6.
- **Allowlist (required):** `office`, `product_id`, `product_category`, `programme_id`, `quantity` (= current stock after the order, int ≥ 0), `currency`, `min_stock`, `previous_stock`.
- **PII:** none.

#### `direct_stock_edit_rejected` — business/inventory · mandatory · stream

Fires when a user attempts to modify stock directly (outside an order) and the system rejects it.

- **We capture `direct_stock_edit_rejected` because** we need to know if staff are attempting to bypass material traceability controls, **which allows us to make the decision** to reinforce training or permissions at the office where this happens most (Patricia).
- **Emitter:** NEW stub routes (EC3) in `inventory.py` — `PUT`/`PATCH`/`DELETE` on `/inventory/products` and `/inventory/products/{asset_id}` → shared `_reject_direct_stock_edit()` that emits, then raises 405. Today any such attempt hits a generic FastAPI 405 with no hook; the stubs create the hook **without** creating an edit capability.
- **Allowlist (required, nullable where the asset cannot be resolved):** `office`, `product_id`, `product_category`, `programme_id`, `quantity` (always null — no stock movement occurs; key kept so every mandatory inventory event carries the briefing's minimum property set), `currency`, `method` (`PUT|PATCH|DELETE`), `path` (template form, e.g. `/inventory/products/{id}` — never the raw URL with real ids).
- **PII:** none.

#### `kit_cost_variance_detected` — business/inventory · mandatory · stream

Fires when the unit cost of an inbound order varies more than 10% from the historical value for that material/supplier pair.

- **We capture `kit_cost_variance_detected` because** we need to know when a material supplier raises prices abnormally, **which allows us to make the decision** to alert Elena and Laura to renegotiate or find an alternate supplier.
- **Emitter:** `inventory.py` `create_inbound_order` — post-commit check: historical mean `unit_cost` for `(asset_id, supplier)` over existing `AssetEntry` rows; emit when `|new − mean| / mean > 0.10`. First purchase for a pair emits nothing (no history). Requires EC5, EC6.
- **Allowlist (required):** `office`, `product_id`, `product_category`, `programme_id`, `quantity`, `currency`, `supplier`, `unit_cost`, `historical_avg_cost`, `variance_percent` (signed), `order_id`.
- **PII:** none.

### 4.2 Identified opportunities (proposed by this plan)

#### Business / inventory

##### `product_created` — opportunity · batch
- **We capture `product_created` because** we need to know how the catalogue grows per office and per programme, which reveals where material types are proliferating, **which allows us to make the decision** to identify unplanned item proliferation and standardise catalogues (Patricia/Elena).
- **Emitter:** `inventory.py` `create_product` (:85-104) — emit after `session.refresh(asset)` (:101). Requires EC4, EC6.
- **Allowlist (required):** `office`, `product_id`, `product_category`, `programme_id`, `quantity` (always 0 — new assets start at zero stock), `currency`, `sku`, `min_stock`.
- **PII:** none — the product free-text `name` is excluded (it could embed personal names); only the structured `sku` is captured.

##### `outbound_order_rejected` — opportunity · batch
- **We capture `outbound_order_rejected` because** we need to know when deliveries are rejected for lack of stock, per programme, **which allows us to make the decision** to trigger earlier restocking and validate demand forecasts (Elena).
- **Emitter:** `inventory.py` insufficient-stock branch (:139-147) — emit before `raise HTTPException(400)`.
- **Allowlist (required):** `office`, `product_id`, `product_category`, `programme_id`, `quantity` (requested), `currency`, `exit_type`, `available_stock`.
- **PII:** none — `assigned_to` never captured.

##### `supplier_rate_edited` — opportunity · batch
- **We capture `supplier_rate_edited` because** we need to know how often each supplier's rate changes and in which direction, **which allows us to make the decision** to feed supplier negotiation and cost-variance investigations (Laura).
- **Emitter:** `Supply_directory_API/routes/suppliers.py` `update_supplier_rate` (:128-149) — capture the old rate from `_find_supplier_or_404`'s result (:137, currently discarded), emit after `_get_after_write` (:146). The FE rate editor (`uis/backoffice/app/suppliers/page.tsx:101-147`) emits nothing — backend is canonical.
- **Allowlist (required):** `supplier_id`, `old_rate`, `new_rate`, `currency`.
- **PII:** none — supplier `contact_email` and `notes` are never captured.

##### `incident_report_analyzed` — opportunity · batch
- **We capture `incident_report_analyzed` because** we need to know how much the incident analyzer is used and how heavy its workloads are, **which allows us to make the decision** to plan analyzer capacity and track adoption of Roberto's support line.
- **Emitter:** `backrooms/services/APIs/analyzer-api.py` `analyze_incidents` (:83-121) — emit after `analyze_records` (:111), before the return (:121); measure duration around :91-:111.
- **Allowlist (required):** `row_count`, `valid_count`, `duration_ms`.
- **PII:** none — aggregate counts only; CSV contents (which may contain personal data) are never captured. Endpoint is unauthenticated → envelope `userId` null (documented risk, §8.3).

#### Authentication

##### `login_succeeded` — opportunity · batch
- **We capture `login_succeeded` because** we need to know account usage patterns: who logs in, when, and how often, **which allows us to make the decision** to identify inactive accounts for cleanup and spot unusual login-time clustering (Laura/Patricia).
- **Emitter:** `routes/auth.py` `login` — emit after `create_access_token` (:86), before the return (:87).
- **Allowlist:** `{}` — empty by design. The email is omitted entirely; identity lives in the envelope `userId`.

##### `login_failed` — opportunity · stream
- **We capture `login_failed` because** we need to know whether login failures are forgotten credentials or attack patterns, **which allows us to make the decision** to detect credential attacks and target security training (Patricia).
- **Emitter:** `routes/auth.py` — unknown-email branch (:66-71), corrupt-hash branch (:75-77), wrong-password/inactive branch (:79-84).
- **Allowlist (required):** `failure_reason` (`unknown_email|wrong_password|inactive_account|corrupt_hash`).
- **PII:** the attempted email is NEVER captured, not even hashed — the staff is small enough that hashes would be trivially re-identifiable.
- **Throttle:** cap 60/min/service (bounds brute-force storms; the spike shape stays visible).

##### `session_expired` — opportunity · batch
- **We capture `session_expired` because** we need to know how often sessions expire mid-use and where that friction happens, **which allows us to make the decision** to tune token_expiry_minutes and improve the session UX.
- **Emitters:** (server) `auth/dependencies.py` `get_current_user` (:13-31) with the EC2 expiry split; (client) `uis/backoffice/components/auth/AuthGuard.tsx:22-39` when the client detects expiry while idle.
- **Allowlist (required):** `detected_by` (`client|server`).

##### `password_reset_requested` — opportunity · batch
- **We capture `password_reset_requested` because** we need to know how much password-recovery demand exists over time, **which allows us to make the decision** to target onboarding improvements and evaluate SSO (Patricia).
- **Emitter:** `routes/auth.py` `forgot_password` — emit before the success return (:152).
- **Allowlist:** `{}` — the email is omitted; the endpoint already anti-enumerates registered addresses and telemetry must not weaken that.

##### `password_reset_failed` — opportunity · batch
- **We capture `password_reset_failed` because** we need to know which failure mode dominates the reset flow, **which allows us to make the decision** to fix email-configuration issues proactively and measure reset-token abuse.
- **Emitter:** `routes/auth.py` — 503 branches (:110-115, :124-131, :140-145 → `email_service_unavailable`) and `reset_password` invalid-token branches (:157-163, :165-169 → `invalid_reset_token`).
- **Allowlist (required):** `reason` (`email_service_unavailable|invalid_reset_token`).

##### `user_registered` — opportunity · batch
- **We capture `user_registered` because** we need to know the account-creation rate as a leading indicator of staff onboarding volume, **which allows us to make the decision** to forecast onboarding-kit demand (Patricia, including Roberto's 30 outsourced support agents).
- **Emitter:** `routes/users.py` `register` (:37-45) — emit after `create_user` succeeds, before the return (:45). Unauthenticated → `userId` null.
- **Allowlist (required):** `role` (`admin|manager|user`).
- **Note:** the User model has no office field, so office correlation for registrations is impossible today (future work, §11).

##### `admin_role_changed` — opportunity · stream
- **We capture `admin_role_changed` because** we need to know how often privileges change, in which direction, and by whom, **which allows us to make the decision** to maintain a permission-governance audit trail (Patricia).
- **Emitter:** `routes/users.py` `update_user_record` (:68-84) — when `payload.role is not None`; pre-fetch the existing user before `update_user` (:79) to obtain the previous role, emit after the successful update. (The 403 gate for non-admin role edits at :75-76 is not evented — documented exclusion, §8.1.)
- **Allowlist (required):** `target_user_id`, `previous_role`, `new_role`.

#### Navigation

##### `page_view` — opportunity · batch
- **We capture `page_view` because** we need to know which backoffice sections operators actually visit most, **which allows us to make the decision** to prioritise features and training on hot sections; simplify or cut underused ones.
- **Emitter:** NEW `uis/backoffice/components/telemetry/PageViewTracker.tsx` (client component using `usePathname`), mounted once in `uis/backoffice/app/layout.tsx` body. One point covers every route — including the dashboard's own sidebar (`app/page.tsx:26`) and `/login`.
- **Allowlist (required):** `page_path` (query string ALWAYS stripped — `/login?next=…` and `/reset-password?token=…` must never leak). **Optional:** `load_duration_ms` (from `performance.getEntriesByType("navigation")[0]?.duration`), `referrer_path` (same-origin only).
- **Throttle:** no dropping; transport-level batching only (10 s / 20-event buffer, `visibilitychange` Beacon flush with a normal-send fallback).

##### `form_abandoned` — opportunity · batch
- **We capture `form_abandoned` because** we need to know which flows lose operators before completion, **which allows us to make the decision** to redesign or re-train on the abandoned flows.
- **Emitter:** NEW `uis/backoffice/lib/telemetry/useFormAbandonment.ts` — emits on unmount when the form was dirtied (≥1 field entered) and never successfully submitted. Mount on: inbound form, outbound form, `SupplierRegistrationForm`, forgot-password form.
- **Allowlist (required):** `flow_id` (`inbound_order_form|outbound_order_form|supplier_registration_form|password_reset_flow`), `page_path`.
- **PII:** NO field values are ever captured.

#### Performance

##### `api_latency_recorded` — opportunity · stream
- **We capture `api_latency_recorded` because** we need to know which endpoints are slow and when slowness spikes, **which allows us to make the decision** to fix or optimise the slow endpoints operators depend on (ops team).
- **Emitter:** NEW `TelemetryMiddleware` (EC1) registered after CORS in `Inventory-API/main.py:51-57`, `Supply_directory_API/main.py`, and `APIs/analyzer-api.py:26-33`. Emits **only when duration ≥ 500 ms**.
- **Allowlist (required):** `service`, `method`, `path` (route template from `request.scope["route"].path`; numeric segments replaced with `{id}` when unresolvable — high-cardinality protection), `status_code`, `duration_ms`.
- **Throttle:** debounce 1/(service, method, path)/60 s.

#### Errors

##### `frontend_error_captured` — opportunity · stream
- **We capture `frontend_error_captured` because** we need to know which pages crash or throw in production, **which allows us to make the decision** to fix the top-crash pages first (dev team).
- **Emitter:** NEW `uis/backoffice/lib/telemetry/error-listeners.ts` (`window.addEventListener("error")` + `"unhandledrejection"`), registered from the client component in `app/layout.tsx`; optionally a NEW `app/error.tsx` boundary (`source: error_boundary`). No error handling exists today — this is the net-new hook.
- **Allowlist (required):** `error_type` (Error.name or `UnhandledRejection`), `message` (**sanitised**: ≤300 chars, emails/URLs stripped by regex), `page_path`, `source`. **Optional:** `stack_frame` (first frame only, `file:line`).
- **PII:** `contains_pii: true` — messages can contain emails/URLs/user content; sanitisation is mandatory before emission.
- **Throttle:** cap 10/min/session; identical (error_type, message) suppressed for 5 min.

##### `network_request_failed` — opportunity · stream
- **We capture `network_request_failed` because** we need to know which APIs fail from operators' browsers, **which allows us to make the decision** to prioritise service fixes and monitor availability (ops team).
- **Emitter:** `uis/backoffice/lib/auth/client.ts` `authorizedFetch` catch branch (:54-58) — emit before re-throwing.
- **Allowlist (required):** `target` (normalised `service:path`, e.g. `inventory-api:/inventory/orders/inbound`, query stripped), `page_path`.
- **Throttle:** 1/(target, page_path)/60 s.

#### Validation

##### `validation_failed` — opportunity · batch
- **We capture `validation_failed` because** we need to know which forms and endpoints generate the most invalid submissions, **which allows us to make the decision** to redesign the offending forms or clarify field rules (ops/UX).
- **Emitters:** (client) form validation branches — inbound `page.tsx:79-94`, outbound `page.tsx:91-106`, `SupplierRegistrationForm.tsx:44-58`; (server) NEW `RequestValidationError` handler in `Inventory-API/main.py` (EC8) — emit, then return the standard 422 body. Field names come from `exc.errors()` `loc` — **never the submitted values**.
- **Allowlist (required):** `source` (`client|server`), `context` (form id or endpoint path template), `field` (field name only), `reason` (rule code, e.g. `quantity_gt_0`, `assigned_to_required`, `asset_required`). **Optional:** `page_path` (client only).
- **PII:** PII-free by construction — values are never captured.
- **Throttle:** client 1/(context, reason)/60 s per session; server cap 10/min/endpoint.

### 4.3 Summary matrix

| # | event_type | Category | Classification | Delivery | Emitters |
|---|---|---|---|---|---|
| 1 | `inbound_order_created` | business/inventory | mandatory | stream | inventory-api |
| 2 | `outbound_order_created` | business/inventory | mandatory | stream | inventory-api |
| 3 | `stock_threshold_triggered` | business/inventory | mandatory | stream | inventory-api |
| 4 | `direct_stock_edit_rejected` | business/inventory | mandatory | stream | inventory-api |
| 5 | `kit_cost_variance_detected` | business/inventory | mandatory | stream | inventory-api |
| 6 | `product_created` | business/inventory | opportunity | batch | inventory-api |
| 7 | `outbound_order_rejected` | business/inventory | opportunity | batch | inventory-api |
| 8 | `supplier_rate_edited` | business/inventory | opportunity | batch | supply-directory-api |
| 9 | `incident_report_analyzed` | business/inventory | opportunity | batch | analyzer-api |
| 10 | `login_succeeded` | authentication | opportunity | batch | supply-directory-api |
| 11 | `login_failed` | authentication | opportunity | stream | supply-directory-api |
| 12 | `session_expired` | authentication | opportunity | batch | supply-directory-api, web |
| 13 | `password_reset_requested` | authentication | opportunity | batch | supply-directory-api |
| 14 | `password_reset_failed` | authentication | opportunity | batch | supply-directory-api |
| 15 | `user_registered` | authentication | opportunity | batch | supply-directory-api |
| 16 | `admin_role_changed` | authentication | opportunity | stream | supply-directory-api |
| 17 | `page_view` | navigation | opportunity | batch | web |
| 18 | `form_abandoned` | navigation | opportunity | batch | web |
| 19 | `api_latency_recorded` | performance | opportunity | stream | all three APIs |
| 20 | `frontend_error_captured` | errors | opportunity | stream | web |
| 21 | `network_request_failed` | errors | opportunity | stream | web |
| 22 | `validation_failed` | validation | opportunity | batch | web, inventory-api |

---

## 5. Phase 2 — Event envelope and schemas

### 5.1 The standard envelope

Every event, from every source, carries these nine fields. The draft-07 schema is `envelope` in `event-schemas.json`.

| Field | Type | Generated by | Notes |
|---|---|---|---|
| `eventId` | string (UUIDv4) | emitter | `crypto.randomUUID()` on web; `uuid.uuid4()` on APIs. Unique per event instance. |
| `timestamp` | string, ISO 8601 UTC | emitter | Emission time with millisecond precision, e.g. `2026-10-18T14:00:00.000Z`. Always UTC — emitters never attach offsets. |
| `sessionId` | string (UUIDv4) | web; APIs adopt | The web client creates one UUID per page lifetime in session memory (no `sessionStorage`), sends it as `X-Session-Id` on every fetch, and rotates it on successful login. Logout or a 401 rotates it back to an anonymous session. A hard reload starts a new anonymous session and re-binds to the authenticated token when one is valid. API middleware adopts the header; if absent (direct API call), it generates a fresh per-request UUID (server-side session, not persisted). Never null. |
| `userId` | string \| null | APIs from JWT `sub`; web decodes the token | Stringified TinyDB **integer id** from the JWT `sub` claim — NOT the `user_uuid` orders store; join via the admin `/users` lookup. Null when unauthenticated (login failures, password flows, registration, analyzer, `/login` page views). Never an email, never the uuid. |
| `event_type` | string | emitter | One of the 22 catalogue values (§4.3). |
| `schemaVersion` | string `X.Y` | emitter | Version of **this event's** `properties_schema` (`schema_version` in the catalogue). |
| `requestId` | string (UUIDv4) | web per action; APIs adopt | The web client generates one UUID per user action/fetch and sends it as `X-Request-Id` (added in `authorizedFetch`'s `buildHeaders`, `client.ts:24-41`). API middleware adopts the header or generates one, and echoes it in the `X-Request-Id` response header. |
| `source` | enum | emitter | `web` \| `inventory-api` \| `supply-directory-api` \| `analyzer-api` — the capture-pipeline routing discriminator. |
| `properties` | object | emitter | Flat keys only; always present (`{}` allowed); every key must be in the event's allowlist. |

### 5.2 Correlation — worked example

An operator submits an outbound order:

1. The web client generates `requestId = R` and sends `X-Request-Id: R`, `X-Session-Id: S`.
2. The Inventory API middleware adopts `R`, times the request, and echoes `X-Request-Id: R`.
3. `outbound_order_created` (BE) carries `requestId: R`, `sessionId: S`.
4. Had the FE validation failed instead, `validation_failed` (FE) would carry `requestId: R`, `sessionId: S` — and `outbound_order_created` would never fire.

Every event caused by one user action — frontend and backend — shares one `requestId`; `sessionId` ties them to one tab session; `userId` ties them to one person.

### 5.2.1 Emitter ownership (Sprint 1 contract)

The **Inventory API is canonical for all five mandatory inventory events** and for `outbound_order_rejected`. It emits them through the shared backend emitter after the business fact is confirmed, using the request's `X-Request-Id` and `X-Session-Id`. The backoffice does **not** re-emit business facts; it emits only navigation, client validation, network failures, and uncaught frontend errors. This prevents double counting and keeps threshold/variance/rejection facts authoritative.

The validating receiver is hosted by the **Inventory API** at `POST /telemetry/events`. `TELEMETRY_ENDPOINT` configures backend delivery; `NEXT_PUBLIC_TELEMETRY_ENDPOINT` configures the browser. Sprint 2 retains both the URL and the envelope model.

### 5.2.2 Sprint 2 storage mapping

The real receiver keeps the Sprint 1 URL and the unchanged `TelemetryEvent` model. It accepts `{ "events": [...] }` as a loose list, validates each item independently, inserts valid items with one bulk operation, and returns `{ "received": N, "stored": M, "rejected": R }`. A non-object item is rejected individually; a missing or non-list `events` field is a malformed envelope (`422`); a storage failure rolls back and returns `503`.

| DB column | Source |
|---|---|
| `id` | Database UUID primary key (`gen_random_uuid()`) |
| `timestamp` | `event.timestamp` |
| `service` | `web` → `backoffice`; `inventory-api`, `supply-directory-api`, and `analyzer-api` preserved |
| `event_type` | Exact catalogue identifier |
| `level` | Explicit mapping: `error` for `frontend_error_captured`, `network_request_failed`, `login_failed`, `password_reset_failed`; `warn` for validation, rejections, threshold, cost variance, and session expiry; otherwise `info` |
| `value` | Documented numeric property: `page_view.load_duration_ms`, `api_latency_recorded.duration_ms`, `incident_report_analyzed.duration_ms`, `kit_cost_variance_detected.variance_percent`, and `quantity` for the inventory order/threshold events; otherwise null |
| `message` | Sanitised `frontend_error_captured.message` only; every other event stores null |
| `tags` | Sanitised, allowlisted `properties` plus a reserved `_meta` object containing `eventId`, `sessionId`, `userId`, `schemaVersion`, and `requestId` |

`tags._meta` is storage metadata, not an event-property allowlist expansion. Reporting must ignore `_meta` and use the flat business dimensions. Query strings are stripped from `page_path`, `referrer_path`, and `target`; error messages have emails, URLs, and sensitive query values redacted before they reach either `message` or `tags.message`.

The table is append-only: no application UPDATE or DELETE operations. The three required indexes are `timestamp`, `event_type`, and a GIN index on `tags`. RLS is enabled and `anon`/`authenticated` are revoked; the backend connects with direct database credentials. The reproducible migration is `Inventory-API/migrations/002_telemetry_events.sql`, applied idempotently by `init_inventory_schema()`; SQLite tests create the equivalent table from SQLAlchemy metadata.

Duplicate delivery is accepted. Retries and Beacon can produce duplicate rows with the same `eventId`, and `stored` counts each row; Sprint 2 does not claim exactly-once storage and does not add a unique constraint. Future deduplication can use `tags._meta.eventId` without changing the envelope.

### 5.3 Shared property dictionary

| Property | Type | Rule |
|---|---|---|
| `office` | enum `valencia` \| `miami` | **Lowercase**, per the briefing. The backend stores `"Valencia"`/`"Miami"` (`schemas.py:19`); the emitter lowercases at emission (EC1 helper `lower_office()`). |
| `currency` | enum `EUR` \| `USD` | Derived from the office: Valencia → EUR, Miami → USD. **Never converted** at the telemetry layer — amounts stay in the office's local currency. |
| `product_category` | enum `training_kit` \| `certification` \| `onboarding_equipment` | Briefing taxonomy. Requires the EC7 literal migration before it can be emitted. |
| `programme_id` | string slug (`b2b-sales`, `basic-leadership`, …) | Requires the EC6 Programme entity. |
| `product_id` | integer | `Asset.id`. |
| `quantity` | integer | Event-specific semantics (received / delivered / current stock / requested) — documented per event. |

Interface language (Spanish/English) is an independent dimension from `office` and is **never captured** (briefing §6).

### 5.4 Per-event schemas and allowlists

The normative, machine-checkable definitions live in `event-schemas.json`: each event entry carries `description`, `hypothesis`, `decision`, `emitters`, `throttle`, and a `properties_schema` that is a valid draft-07 schema with `additionalProperties: false`. **The allowlist is the schema itself**: only keys declared under `properties` may appear, `required` marks mandatory keys, and nothing outside the allowlist can be included — this is what prevents accidental data leakage.

§4 of this document lists each event's allowlist in prose; `event-schemas.json` holds the full typing (types, enums, minimums, per-property descriptions) and the per-event PII block (`contains_pii` + `sanitisation`).

### 5.5 `event-schemas.json` structure

```text
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "meta":   { name: "nexova-telemetry", version, taxonomy: "entity_action",
              envelope_schema_version: "1.0", generated_at },
  "envelope": <draft-07 schema of §5.1>,
  "events": { "<event_type>": { event_type, category, classification, delivery,
              schema_version, description, hypothesis, decision, emitters,
              throttle, properties_schema: <draft-07, additionalProperties: false>,
              pii: { contains_pii, sanitisation } }, ... 22 entries },
  "definitions": { "eventEntry": <draft-07 shape every entry conforms to> }
}
```

**Validation story** (run from the repo root):

```bash
# 1. The file parses.
python -m json.tool event-schemas.json

# 2. The envelope, the entry shape, and every event's properties_schema compile as draft-07.
cd backrooms/services
uv run --with jsonschema python -c "import json, jsonschema; d = json.load(open('../../event-schemas.json', encoding='utf-8')); jsonschema.Draft7Validator.check_schema(d['envelope']); jsonschema.Draft7Validator.check_schema(d['definitions']['eventEntry']); [jsonschema.Draft7Validator.check_schema(e['properties_schema']) for e in d['events'].values()]; print('OK: envelope, eventEntry, and all', len(d['events']), 'properties_schema are valid draft-07')"

# 3. Internal consistency: every events key equals its event_type; the five
#    mandatory event_types exist with classification "mandatory"; 22 entries.
```

```bash
# 4. Cross-document consistency: every event_type appears in telemetry-plan.md;
#    hypothesis/decision wording matches (first letter adapted to sentence
#    position — see §1 conventions); the appendix sample events validate
#    against the envelope and their own properties_schema.
python -c "
import json, re
d = json.load(open('event-schemas.json', encoding='utf-8'))
md = open('telemetry-plan.md', encoding='utf-8').read()
for k, e in d['events'].items():
    assert k in md, k
    hyp = e['hypothesis']; dec = e['decision']
    assert hyp[0].lower() + hyp[1:].rstrip('.') in md, ('hyp', k)
    assert 'to ' + dec[0].lower() + dec[1:] in md, ('dec', k)
print('OK: all', len(d['events']), 'events consistent between JSON and MD')
"
```

---

## 6. Phase 3 — Delivery strategy

### 6.1 Stream vs batch — decided by business urgency

**Stream (real-time processing) — 10 events:**

| Event | Justification (urgency, not preference) |
|---|---|
| `inbound_order_created` | Elena's dashboard needs same-day stock visibility; volume is a few events per day, so urgency decides, not cost. |
| `outbound_order_created` | Restocking lead time (reprint/procurement) means consumption must be visible same-day. |
| `stock_threshold_triggered` | A run-out requires immediate reprint/production action. |
| `direct_stock_edit_rejected` | Governance/security signal; Patricia should react the same day. |
| `kit_cost_variance_detected` | Price changes should alert Elena and Laura when they happen, not days later. |
| `login_failed` | Credential-attack detection needs near-real-time. |
| `admin_role_changed` | Privilege escalation is a security anomaly; same-day audit. |
| `api_latency_recorded` | Slow APIs degrade operators during the working day. |
| `frontend_error_captured` | Broken pages block operators; fix today, not after the weekly review. |
| `network_request_failed` | Service-outage detection. |

**Batch (periodic batches) — 12 events:**

| Event | Justification |
|---|---|
| `product_created` | Catalogue-growth trend is a monthly/quarterly planning input. |
| `outbound_order_rejected` | Demand-vs-stock forecasting input; weekly cadence suffices. |
| `supplier_rate_edited` | Feeds Laura's weekly cost review. |
| `incident_report_analyzed` | Capacity planning is weekly. |
| `login_succeeded` | Inactive-account review is a periodic audit. |
| `session_expired` | Expiry-policy tuning is periodic. |
| `password_reset_requested` / `password_reset_failed` | Support-load trends are periodic. |
| `user_registered` | Onboarding-kit forecasting is weekly. |
| `page_view` | Most-visited-section analysis is daily/weekly. |
| `form_abandoned` | UX pattern analysis is periodic. |
| `validation_failed` | Form-redesign decisions are periodic; individual rejects have no urgency. |

Default batch window: **daily flush at 02:00 UTC**, kept configurable per event. Storage and retention policy belong to the later Storage milestone; this plan fixes only the delivery class.

### 6.2 Throttle / debounce strategy (high-frequency events)

| Event | Strategy |
|---|---|
| `page_view` | No dropping (visit counts are the point). Transport-level batching only: FE buffers and flushes no later than 10 s after the first pending event or at 20 events, whichever comes first, then uses `navigator.sendBeacon` on `visibilitychange` to hidden with a normal-send fallback when Beacon is refused. Delivery is best-effort; browser termination and offline periods are not guaranteed. |
| `api_latency_recorded` | Emit only ≥ 500 ms; debounce 1/(service, method, path)/60 s. Sub-threshold requests emit nothing (counter-only). |
| `frontend_error_captured` | Cap 10/min/session; identical (error_type, message) suppressed for 5 min. |
| `network_request_failed` | 1/(target, page_path)/60 s. |
| `stock_threshold_triggered` | Edge-triggered (only on crossing below `min_stock`); max 1/product_id/60 min. |
| `kit_cost_variance_detected` | Max 1/(product_id, supplier)/24 h (suppresses alert storms on multi-line orders). |
| `validation_failed` | Client: 1/(context, reason)/60 s per session. Server: cap 10/min/endpoint. |
| `login_failed` | Cap 60/min/service. |
| `form_abandoned` | Natural: 1/(sessionId, flow_id) at unmount time. |
| All others | No throttle — natural volume is low. |

---

## 7. PII and data-minimisation rules

**Never captured, anywhere:**

- Candidate, client, or consultant names — `assigned_to` is excluded from `outbound_order_created` entirely, not even as a presence flag (briefing §3).
- Emails — login and password events omit them completely; **no hashing** either, because the staff is small enough that hashes would be trivially re-identifiable.
- Passwords and password hashes; reset tokens and reset URLs.
- IP addresses.
- Raw user-agent strings. If device context is ever needed, a whitelist mapper emits only a generic bucket `{browser_family, device_class}`.
- Profile name / phone / address (`ProfileResponse` fields stay inside the API).
- Supplier `contact_email` and `notes`.
- Product free-text `name` (use `sku` / `product_id`).
- Full HTTP payloads, headers, and query strings — `page_path` and `target` always have the query stripped (kills `?token=` / `?next=` leaks).
- Incident CSV contents — counts only.
- Submitted form values — `validation_failed` carries field names and rule codes only.
- Interface language — independent dimension, not captured (briefing §6).

**Captured, with rules:**

- `userId` = stringified internal integer id — pseudonymous, for internal consumers only (Elena, Laura, Patricia). Never an email or the uuid.
- `supplier` = company name — business data.
- `message` in `frontend_error_captured` = truncated to 300 chars, emails/URLs stripped by regex; `stack_frame` = first frame only.
- `office`, `currency`, `programme_id`, `product_id`, `role`, `exit_type` = business data.

**Briefing rules encoded in the schemas:** no currency conversion at the telemetry layer; amounts stay in the office's local currency (EUR Valencia / USD Miami).

---

## 8. Risks and exclusions

### 8.1 Events considered and discarded

| Candidate event | Reason for discarding |
|---|---|
| `login_password_captured` (or any password content) | Security: passwords are never captured, full stop. |
| Per-keystroke / per-field input telemetry | Privacy + cost; no decision it would feed. |
| Mouse-movement / scroll / click heatmaps | No operations decision depends on them. |
| `supplier_created`, `supplier_deleted`, `supplier_status_toggled` | Supplier list churn is rare and low-value; rate edits are kept because they feed cost analysis. |
| `logout` | Derivable from login events + session expiry; a dedicated event adds nothing. |
| `password_changed` | Credential health is already visible via the `login_failed` trend. |
| `low_stock_observed` (FE badge, `app/inventory/products/page.tsx:103-117`) | Redundant with the authoritative backend `stock_threshold_triggered`. |
| `stock_restocked` | Redundant with `inbound_order_created`. |
| `token_refresh_failed` | The JWT architecture has no refresh tokens. |
| `cache_hit_miss` | Technical noise; no business decision. Cost not justified. |
| `order_list_loaded` / `products_list_viewed` | Covered by `page_view`. |
| `registration_duplicate_email` | Email-existence disclosure risk (409 reveals duplicates) + low decision value. |
| Role-change 403 attempts (in `admin_role_changed`'s route, `users.py:75-76`) | Rejected attempts are permission-denial cases, covered by `direct_stock_edit_rejected`-style governance where they matter; capturing them risks noise. |

### 8.2 Data not captured for privacy or cost

Everything in §7's "never captured" list, plus: exact failed-login timestamps per email (absent by design — no email captured), full stack traces (first frame only), and high-cardinality raw URL paths (route templates only).

### 8.3 Operational risks (and mitigations)

| Risk | Mitigation |
|---|---|
| FE/BE double counting of the same business fact | **Backend is canonical for business events.** The web app emits only UX/diagnostic events (navigation, client validation, client-detected expiry, errors, network failures). |
| Allowlist drift (new keys silently added) | Emitters enforce the allowlist with typed function signatures; schemas use `additionalProperties: false`. |
| Timestamp skew between emitters | All timestamps are emitter-UTC by contract (§5.1). |
| Null `userId` on unauthenticated endpoints | Expected and schema-legal; documented per event (analyzer, password flows, registration). |
| TinyDB int id (userId) vs `user_uuid` on orders | Documented join path via the admin `/users` lookup; `order_id` in inventory events lets reports resolve order → user_uuid → user id. |
| Category-literal migration ordering | EC7 must land **before** any telemetry activation, or events would emit the old literals. |
| `page_view` buffer loss on hard close | `visibilitychange` Beacon flush mitigates; residual loss is accepted for a batch navigation signal. |
| Frontend-generated ids (sessionId/requestId) are client-controlled | Accepted: they are correlation hints, not security boundaries; backend adopts but never trusts them for authorisation. |
| `assigned_to` regression | Schema-level ban: `outbound_order_created.properties_schema` has no such key, so any emitter adding it fails validation in the Capture milestone. |

### 8.4 Out of scope (this plan)

The website, talent-pipeline-tracker, and landing page are not instrumented — the briefing centers telemetry on the inventory system and its backoffice. They are noted as future work (§11), not silently ignored.

---

## 9. Enabling changes — prerequisites for the Capture milestone

These are net-new hooks without which the events above cannot fire. **They are described here, not implemented in this milestone** ("before writing a single line of instrumentation"). Each names the file it touches; the Capture milestone implements them in this dependency order.

- **EC1 — Telemetry receiver + shared emitter.** NEW `backrooms/services/telemetry/` package (importable as `services.telemetry`, next to `services.cache`): `models.py` defines the reusable `TelemetryEvent` envelope; `router.py` exposes `POST /telemetry/events` for format validation and returns `{ "received": N }` without persistence; `emitter.py` builds the full envelope (eventId, UTC timestamp, sessionId, userId from token `sub` when present, source, schemaVersion), adopts `X-Request-Id`/`X-Session-Id`, validates the event property allowlist, and batches inventory-origin events no later than 10 s after the first pending event or at 20 events. `OFFICE_CURRENCY = {"valencia": "EUR", "miami": "USD"}` and `lower_office()` live in `constants.py`. Register the router in the selected host, the Inventory API (`Inventory-API/main.py`). The backend reads `TELEMETRY_ENDPOINT`; the web client posts to `NEXT_PUBLIC_TELEMETRY_ENDPOINT` when set and silently no-ops otherwise. Sprint 1 uses the receiver as a validating stub; Sprint 2 replaces its internals with per-event validation and Supabase persistence.
- **EC2 — Token-expiry split.** `Supply_directory_API/auth/dependencies.py:13-21`: catch `jwt.ExpiredSignatureError` before the generic `(RuntimeError, ValueError)`, read `sub` via unverified decode, emit `session_expired` (server), then raise 401 with detail `"Session expired"`.
- **EC3 — Direct-stock-edit stub routes.** `Inventory-API/routers/inventory.py`: six stubs — `PUT`/`PATCH`/`DELETE` × `/products` and `/products/{asset_id}` — routing to `_reject_direct_stock_edit()`, which emits `direct_stock_edit_rejected` and raises 405. The stubs create the hook without creating an edit capability.
- **EC4 — `min_stock`.** `Inventory-API/models.py` `Asset`: `min_stock: int = 10`; `schemas.py` `AssetCreate`: optional `min_stock`; post-commit edge check in `create_outbound_order` using the pre-commit `available` (`inventory.py:138`).
- **EC5 — `unit_cost` + `currency` + variance.** `schemas.py` `AssetEntryCreate`: `unit_cost` (Decimal > 0) and `currency` (`EUR|USD`) with a validator that currency matches the office (mirroring the `SupplierBase` validator pattern, `Supply_directory_API/models.py:38-45`); `models.py` `AssetEntry`: the two columns; variance check in `create_inbound_order` after commit (history mean per `(asset_id, supplier)`, >10 % → emit).
- **EC6 — Programme entity.** `Inventory-API/models.py`: new `Programme` (id, unique slug, name); `Asset.programme_id` FK (nullable during migration); seed rows (≥3, including `b2b-sales`, `basic-leadership`); all inventory events read `programme_id` from the asset.
- **EC7 — Category literal migration.** `Inventory-API/schemas.py:13-18` → `training_kit | certification | onboarding_equipment`; FE mirror `uis/backoffice/lib/inventory.ts:9-13` and `CATEGORY_LABELS` (:86-91); existing seed rows rewritten in the seed milestone. Must land before telemetry activation.
- **EC8 — 422 handler.** `Inventory-API/main.py`: `RequestValidationError` handler emitting `validation_failed` (field names from `exc.errors()`, never values) and returning the standard 422 body.
- **EC9 — Auth/business emit points.** `routes/auth.py` (login :86 / :66-71 / :75-77 / :79-84; forgot-password :152 / :110-115 / :124-131 / :140-145; reset-password :157-163 / :165-169); `routes/users.py` (register :45; role-change pre-fetch + emit in `update_user_record` :68-84); `routes/suppliers.py` (old rate from :137, emit after :146); `APIs/analyzer-api.py` (emit after :111).
- **EC10 — FE telemetry client.** NEW `uis/backoffice/lib/telemetry/session.ts` (in-memory anonymous session; rotate on login; clear on logout/401; userId from token `sub`), `lib/telemetry/telemetry.ts` (single public `track(eventType, properties)`; envelope builder; 10 s / 20-event buffer with a first-pending timer; `visibilitychange` + `sendBeacon`; initial send plus three exponential-backoff retries; in-flight batch kept separate), `lib/telemetry/{constants,catalog,sanitize}.ts`, `components/telemetry/TelemetryBootstrap.tsx` + `PageViewTracker.tsx` + `lib/telemetry/error-listeners.ts` (mounted in `app/layout.tsx`), `X-Request-Id`/`X-Session-Id` headers in `lib/auth/client.ts` `buildHeaders` (:24-41), `network_request_failed` in the catch (:54-58), `validation_failed` (client) in the inbound and outbound validation branches. `form_abandoned`, authentication events, and Web Vitals are deferred opportunity work in Sprint 1.

---

## 10. Instrumentation implementation map

This is the section another developer instruments from, without clarification. Sprint 1 ownership follows §5.2.1: the Inventory API emits every mandatory business event (including `direct_stock_edit_rejected` and `outbound_order_rejected`), while the web app emits only the technical events marked `web`.

| event_type | Frontend (file:line) | Backend (file:line) | Requires |
|---|---|---|---|
| `inbound_order_created` | — (success branch `app/inventory/orders/inbound/page.tsx:106-107` is where the FE knows; the BE emits) | `Inventory-API/routers/inventory.py` after `:126` | EC5, EC6 |
| `outbound_order_created` | — (success branch `.../outbound/page.tsx:120-121`) | `inventory.py` after `:152` | EC6 |
| `stock_threshold_triggered` | — | `inventory.py` post-commit edge check in `create_outbound_order` (uses `available` at `:138`) | EC4, EC6 |
| `direct_stock_edit_rejected` | — (no UI offers direct edits) | `inventory.py` NEW stub routes | EC3 |
| `kit_cost_variance_detected` | — (inbound form has no unit-cost field today; EC5 adds it) | `inventory.py` post-commit check in `create_inbound_order` | EC5, EC6 |
| `product_created` | — | `inventory.py` after `:101` | EC4, EC6 |
| `outbound_order_rejected` | — | `inventory.py` `:139-147` before the 400 | EC6 |
| `supplier_rate_edited` | — | `Supply_directory_API/routes/suppliers.py` after `:146` (old rate from `:137`) | EC9 |
| `incident_report_analyzed` | — | `APIs/analyzer-api.py` after `:111` | EC9 |
| `login_succeeded` | — | `routes/auth.py` after `:86` | EC9 |
| `login_failed` | — | `routes/auth.py` `:66-71`, `:75-77`, `:79-84` | EC9 |
| `session_expired` | `components/auth/AuthGuard.tsx:22-39` | `auth/dependencies.py:13-21` | EC2, EC10 |
| `password_reset_requested` | — | `routes/auth.py` before `:152` | EC9 |
| `password_reset_failed` | — | `routes/auth.py` `:110-115`, `:124-131`, `:140-145`, `:157-163`, `:165-169` | EC9 |
| `user_registered` | — | `routes/users.py` after `:41`, before `:45` | EC9 |
| `admin_role_changed` | — | `routes/users.py` `:68-84` (pre-fetch before `:79`) | EC9 |
| `page_view` | NEW `components/telemetry/PageViewTracker.tsx` mounted in `app/layout.tsx` | — | EC10 |
| `form_abandoned` | NEW `lib/telemetry/useFormAbandonment.ts` on 4 forms | — | EC10 |
| `api_latency_recorded` | — | `TelemetryMiddleware` in all three APIs | EC1 |
| `frontend_error_captured` | NEW `lib/telemetry/error-listeners.ts` (+ optional `app/error.tsx`) | — | EC10 |
| `network_request_failed` | `lib/auth/client.ts:54-58` | — | EC10 |
| `validation_failed` | inbound `page.tsx:79-94`; outbound `page.tsx:91-106`; `SupplierRegistrationForm.tsx:44-58` | `Inventory-API/main.py` NEW 422 handler | EC8, EC10 |

---

## 11. Future work and out of scope

- **Elena's L&D dashboard and Laura's weekly executive report** (briefing §4) — this plan designs the metrics to be aggregated by `office` **and** `programme` from day one; every mandatory event carries both. Dashboard work is a later milestone.
- **Seed-data targets** (briefing §5) — the Capture milestone's seed work must reach: 6-8 products across all 3 categories, ≥3 programmes, 12-15 inbound + 12-15 outbound orders, ≥2 threshold cases, 1 cost-variance case. Today's seed (`Inventory-API/seed.py:22-45`) has 6 assets, 5 inbound, 3 outbound, no programmes, no threshold/variance cases.
- FE threshold badges (`app/inventory/products/page.tsx:103-117`) should read per-asset `min_stock` from EC4 instead of the hardcoded `LOW_STOCK_THRESHOLD` (`lib/inventory.ts:82`).
- Analyzer endpoint authentication (currently public — `userId` null on its events).
- User model `office` field, to correlate `user_registered` and auth events with offices.
- Telemetry for the website, talent-pipeline-tracker, and landing page — deliberately excluded here (§8.4).

---

## 12. Verification checklist (mapped to the evaluation criteria)

| Evaluation criterion | Where satisfied |
|---|---|
| Every mandatory metric from the briefing is present and correctly identified | §4.1 — the 5 events, verbatim event_types, briefing hypotheses and decisions, classified `mandatory` in §4.3 and in `event-schemas.json` |
| Covers technical (errors, performance, authentication, navigation) **and** business opportunities broadly | §4.2 — 17 opportunities across 6 categories, incl. `api_latency_recorded`, `frontend_error_captured`, `page_view`, `form_abandoned`, `validation_failed` |
| Every event has a hypothesis and a business/operational decision | §4 — every entry completes the "We capture … because … which allows us to make the decision …" sentence |
| Envelope is consistent and contains `eventId`, `timestamp` (ISO 8601), `sessionId`, `userId`, `event_type` (`entity_action`), `schemaVersion`, `requestId`, `properties` | §5.1 (all eight, plus `source` as the routing discriminator) — enforced by the `envelope` schema |
| Every event has a documented property allowlist | §4 allowlists + `properties_schema` with `additionalProperties: false` per event in `event-schemas.json` |
| `event-schemas.json` is valid and consistent with the Markdown plan | §5.5 validation commands; hypotheses/decisions byte-identical between the two files |
| Stream/batch decision justified by business/operational urgency | §6.1 — one urgency justification per event |
| Sensitive data / PII identified with anonymisation or sanitisation strategy | §4 per-event PII notes; §7 global rules; `pii` block per event in `event-schemas.json` |
| Risks and exclusions demonstrate critical thinking | §8 — 13 discarded events with reasons, never-captured data list, 9 operational risks with mitigations |
| Precise enough for another developer to instrument without clarification | §9 enabling changes EC1-EC10 with exact files; §10 instrumentation map with `file:line` per event (verified against the working tree on 2026-10-18) |
| Briefing minimum properties on inventory events; aggregatable by office and programme; lowercase offices; no names; no currency conversion | §5.3 shared dictionary; §4.1 mandatory allowlists; §7 PII rules |

---

## 13. Appendix — sample events (validate against `envelope` + the event's `properties_schema`)

**Business:** `inbound_order_created` (inventory-api)
```json
{
  "eventId": "6f2e1a4e-3b5d-4c7a-9e2b-1a8c0d3f5b6e",
  "timestamp": "2026-10-18T09:12:04.512Z",
  "sessionId": "7b3e1f2a-9c4d-4e5f-8a6b-2c0d1e3f4a5b",
  "userId": "3",
  "event_type": "inbound_order_created",
  "schemaVersion": "1.0",
  "requestId": "9a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d",
  "source": "inventory-api",
  "properties": {
    "office": "valencia",
    "product_id": 4,
    "product_category": "training_kit",
    "programme_id": "b2b-sales",
    "quantity": 40,
    "currency": "EUR",
    "supplier": "PrintWorks Valencia S.L.",
    "unit_cost": 12.5,
    "order_id": 118
  }
}
```

**Authentication:** `login_failed` (supply-directory-api)
```json
{
  "eventId": "d4e5f6a7-8b9c-4d0e-1f2a-3b4c5d6e7f8a",
  "timestamp": "2026-10-18T09:13:11.004Z",
  "sessionId": "7b3e1f2a-9c4d-4e5f-8a6b-2c0d1e3f4a5b",
  "userId": null,
  "event_type": "login_failed",
  "schemaVersion": "1.0",
  "requestId": "1b2c3d4e-5f6a-7b8c-9d0e-1f2a3b4c5d6e",
  "source": "supply-directory-api",
  "properties": { "failure_reason": "unknown_email" }
}
```

**Navigation:** `page_view` (web)
```json
{
  "eventId": "2c3d4e5f-6a7b-4c8d-9e0f-1a2b3c4d5e6f",
  "timestamp": "2026-10-18T09:14:22.318Z",
  "sessionId": "7b3e1f2a-9c4d-4e5f-8a6b-2c0d1e3f4a5b",
  "userId": "3",
  "event_type": "page_view",
  "schemaVersion": "1.0",
  "requestId": "3d4e5f6a-7b8c-4d9e-0f1a-2b3c4d5e6f7a",
  "source": "web",
  "properties": {
    "page_path": "/inventory/orders/outbound",
    "load_duration_ms": 742,
    "referrer_path": "/inventory/products"
  }
}
```

**Performance:** `api_latency_recorded` (inventory-api)
```json
{
  "eventId": "4e5f6a7b-8c9d-4e0f-1a2b-3c4d5e6f7a8b",
  "timestamp": "2026-10-18T09:15:01.876Z",
  "sessionId": "7b3e1f2a-9c4d-4e5f-8a6b-2c0d1e3f4a5b",
  "userId": "3",
  "event_type": "api_latency_recorded",
  "schemaVersion": "1.0",
  "requestId": "5f6a7b8c-9d0e-4f1a-2b3c-4d5e6f7a8b9c",
  "source": "inventory-api",
  "properties": {
    "service": "inventory-api",
    "method": "GET",
    "path": "/inventory/orders",
    "status_code": 200,
    "duration_ms": 812
  }
}
```

**Errors:** `frontend_error_captured` (web)
```json
{
  "eventId": "6a7b8c9d-0e1f-4a2b-3c4d-5e6f7a8b9c0d",
  "timestamp": "2026-10-18T09:16:40.129Z",
  "sessionId": "7b3e1f2a-9c4d-4e5f-8a6b-2c0d1e3f4a5b",
  "userId": "3",
  "event_type": "frontend_error_captured",
  "schemaVersion": "1.0",
  "requestId": "7b8c9d0e-1f2a-4b3c-4d5e-6f7a8b9c0d1e",
  "source": "web",
  "properties": {
    "error_type": "TypeError",
    "message": "Cannot read properties of undefined (reading 'map')",
    "page_path": "/inventory/products",
    "source": "window_onerror",
    "stack_frame": "inventory-products.tsx:104"
  }
}
```

**Validation:** `validation_failed` (web)
```json
{
  "eventId": "8b9c0d1e-2f3a-4b4c-5d6e-7f8a9b0c1d2e",
  "timestamp": "2026-10-18T09:17:03.451Z",
  "sessionId": "7b3e1f2a-9c4d-4e5f-8a6b-2c0d1e3f4a5b",
  "userId": "3",
  "event_type": "validation_failed",
  "schemaVersion": "1.0",
  "requestId": "9c0d1e2f-3a4b-4c5d-6e7f-8a9b0c1d2e3f",
  "source": "web",
  "properties": {
    "source": "client",
    "context": "outbound_order_form",
    "field": "assigned_to",
    "reason": "assigned_to_required",
    "page_path": "/inventory/orders/outbound"
  }
}
```

---

*Prepared as the RFI response for the Nexova operations team. Schema source of truth: `event-schemas.json`.*
