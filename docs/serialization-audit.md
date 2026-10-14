# Backend Serialization Audit — Nexova

**Branch:** `backend-serialization-audit`
**Scope:** every FastAPI endpoint under `backrooms/services`
**Status:** Complete — Phase 1 audit and Phases 2–3 implementation done. Every
endpoint now has an explicit `response_model`; see §7 (checklist) and §10 (changes
applied).

This document audits the serialization state of every endpoint in Nexova's backend and
records the target contract for each route. The goal is a production-grade API where
every response has an explicit `response_model`, input and output schemas are separate,
list endpoints return only the fields their consumers use, and no endpoint leaks
credentials or internal identifiers.

## 1. Method

1. Enumerated every route decorator (`@app.*` / `@router.*`) across the three FastAPI
   applications.
2. Recorded the current response behaviour for each route (explicit `response_model`,
   a typed schema returned by hand, or an untyped `dict`/ORM dump).
3. Traced each consumer in `uis/backoffice` (`lib/inventory.ts`, `lib/auth/*`,
   `app/suppliers/page.tsx`, `app/account/profile/page.tsx`,
   `app/inventory/**`, `app/incidents/page.tsx`) to establish which fields the UI
   actually reads.
4. Selected a target schema per route and documented the field-level decisions.

Consumers used as evidence:

- Supplier directory UI reads: `id`, `name`, `country`, `categories`, `monthly_rate`,
  `currency`, `status`, `contract_renewal_date`, `contact_email`.
- Auth/profile UI (`fetchMe`, `saveProfile`) reads: `id`, `email`, `role`,
  `profile.{name,phone,address}`.
- Inventory UI reads: `Asset{id,name,sku,category,office,current_stock}` and
  `Order{...,user_uuid}` (the order history row renders `user_uuid`).
- Incident analyzer UI reads `total`, `valid`, `invalid`, `invalid_counts`,
  `category_counts`, `status_counts`, `closed_count`, `scored_count`, `average_score`.
- `GET /users` and `GET /users/{id}` have **no UI consumer** today; they exist for
  administrative use and tests.

## 2. Legend

| Mark | Meaning |
| --- | --- |
| ✅ Already serialized | Has an explicit `response_model` and the schema matches the consumer. |
| ⚠️ Partially serialized | Has a `response_model` but over-exposes fields, reuses a detail schema for a list, or lacks a dedicated input schema. |
| ❌ Not serialized | Returns a raw `dict`/ORM object with no declared response contract. |

## 3. Endpoint audit

### 3.1 `Supply_directory_API`

Source: `main.py`, `routes/{suppliers,users,auth,profiles}.py`, `models.py`.

| # | Method & path | Purpose | Today | State |
| --- | --- | --- | --- | --- |
| 1 | `GET /` | Liveness probe | bare `dict[str,str]`, no model | ❌ |
| 2 | `POST /suppliers` | Register a supplier | `response_model=SupplierRecord`; body reuses domain model `Supplier` | ⚠️ |
| 3 | `GET /suppliers` | List/filter suppliers | `list[SupplierRecord]` (full detail incl. `notes`) | ⚠️ |
| 4 | `GET /suppliers/{id}` | Supplier detail | `SupplierRecord` | ✅ |
| 5 | `PATCH /suppliers/{id}/rate` | Update monthly rate | `SupplierRecord` | ✅ |
| 6 | `PATCH /suppliers/{id}/status` | Activate/suspend | `SupplierRecord` | ✅ |
| 7 | `DELETE /suppliers/{id}` | Delete supplier | bare `dict {"detail": ...}`, no model | ❌ |
| 8 | `POST /auth/login` | Issue access token | `TokenResponse` | ✅ |
| 9 | `GET /auth/me` | Caller + profile | `UserWithProfile` (echoes `uuid`, `is_active`, `created_at`) | ⚠️ |
| 10 | `POST /auth/forgot-password` | Start reset | `MessageResponse` | ✅ |
| 11 | `POST /auth/reset-password` | Complete reset | `MessageResponse` | ✅ |
| 12 | `POST /auth/change-password` | Change own password | `MessageResponse` | ✅ |
| 13 | `POST /users` | Register account | `UserResponse` — **echoes `email` + `uuid`** | ❌ |
| 14 | `GET /users` | List users | `list[UserResponse]` (emails, `uuid`) | ⚠️ |
| 15 | `GET /users/{id}` | User detail | `UserResponse` (incl. `uuid`) | ⚠️ |
| 16 | `PUT /users/{id}` | Update user | `UserResponse` (incl. `uuid`) | ⚠️ |
| 17 | `DELETE /users/{id}` | Delete user | bare `dict {"detail": ...}`, no model | ❌ |
| 18 | `GET /profiles/me` | Read own profile | `ProfileResponse` (incl. internal `user_id` FK) | ⚠️ |
| 19 | `PUT /profiles/me` | Update own profile | `ProfileResponse` (incl. internal `user_id` FK) | ⚠️ |

### 3.2 `Inventory-API`

Source: `main.py`, `routers/inventory.py`, `schemas.py`.

The inventory service already follows the target pattern: dedicated create schemas
(`AssetCreate`, `AssetEntryCreate`, `AssetExitCreate`) and dedicated read schemas
(`AssetRead`, `AssetEntryRead`, `AssetExitRead`, `OrderRead`), with `OrderRead` as a
flat join projection (no nested asset object).

| # | Method & path | Purpose | Today | State |
| --- | --- | --- | --- | --- |
| 20 | `GET /` | Liveness probe | bare `dict[str,str]`, no model | ❌ |
| 21 | `GET /inventory/products` | List assets + stock | `list[AssetRead]` | ✅ |
| 22 | `POST /inventory/products` | Create asset | `AssetRead` (input `AssetCreate`) | ✅ |
| 23 | `GET /inventory/products/{id}` | Asset detail | `AssetRead` | ✅ |
| 24 | `POST /inventory/orders/inbound` | Record inbound order | `AssetEntryRead` (input `AssetEntryCreate`) | ✅ |
| 25 | `POST /inventory/orders/outbound` | Record outbound order | `AssetExitRead` (input `AssetExitCreate`) | ✅ |
| 26 | `GET /inventory/orders` | Order history | `list[OrderRead]` (flat projection) | ✅ |

### 3.3 `APIs/analyzer-api.py`

| # | Method & path | Purpose | Today | State |
| --- | --- | --- | --- | --- |
| 27 | `POST /api/incidents/analyze` | Analyze an incident CSV | `dict[str, Any]`, no model | ❌ |
| 28 | `GET /api/incidents/results/export` | Download metrics CSV | `StreamingResponse`, no model | ❌ |

## 4. Target schemas and field lists

### 4.1 `Supply_directory_API` (`models.py`)

| Schema | Direction | Fields | Notes |
| --- | --- | --- | --- |
| `HealthResponse` | out | `status`, `service` | Used by `GET /` in both APIs. |
| `SupplierCreate` | in | `name`, `country`, `categories`, `monthly_rate`, `currency`, `status`, `contract_renewal_date`, `contact_email`, `notes` | Dedicated write schema; `updated_at` is system-generated, not accepted. |
| `SupplierListItem` | out (list) | `id`, `name`, `country`, `categories`, `monthly_rate`, `currency`, `status`, `contract_renewal_date`, `contact_email` | Drops `notes` (potentially long, unused in the table) and `updated_at` (unused in the list). |
| `SupplierRecord` | out (detail/write) | `id` + all `Supplier` fields | Kept for detail, create, rate/status updates. |
| `UserRegistrationResponse` | out (`POST /users`) | `id` | No `email`, no `password`, no `uuid`. Client immediately calls `/auth/login`. |
| `UserListItem` | out (list) | `id`, `role`, `is_active` | No `email`/`uuid`/`created_at`; no UI consumer needs them. |
| `UserDetail` | out (detail/update) | `id`, `email`, `role`, `is_active`, `created_at` | `uuid` is internal — dropped. |
| `CurrentUserWithProfile` | out (`GET /auth/me`) | `id`, `email`, `role`, `profile` | `email` allowed for the caller only. Drops `uuid`, `is_active`, `created_at`. |
| `ProfileResponse` | out | `id`, `name`, `phone`, `address` | Drops `user_id` (internal FK; the profile is already scoped to the caller). |
| `MessageResponse` | out | `detail` | Reused by the two `DELETE` routes and password flows. |

`TokenResponse`, `LoginRequest`, `ForgotPasswordRequest`, `ResetPasswordRequest`,
`ChangePasswordRequest`, `UserCreate`, `UserUpdate`, `ProfileUpdate` are unchanged.

### 4.2 `Inventory-API` (`schemas.py`)

| Schema | Direction | Fields | Notes |
| --- | --- | --- | --- |
| `HealthResponse` | out | `status`, `service` | Used by `GET /`. |

All other schemas are unchanged. `AssetEntryRead`/`AssetExitRead` keep `user_uuid`
because the order-history UI renders it; `OrderRead` keeps `asset_id` and `user_uuid`
as an intentional flat projection (documented in §5).

### 4.3 `analyzer-api.py`

| Schema | Direction | Fields | Notes |
| --- | --- | --- | --- |
| `IncidentAnalysisResponse` | out | `total`, `valid`, `invalid`, `invalid_counts`, `category_counts`, `status_counts`, `closed_count`, `scored_count`, `average_score` | Drops `score_counts` — the analyzer UI never reads it (the CSV export still uses the raw metrics internally). |

## 5. Serialization decisions

1. **`GET /suppliers` vs `GET /suppliers/{id}`** — the list gets a slimmer
   `SupplierListItem`; the detail route keeps the full `SupplierRecord`. `notes` and
   `updated_at` are omitted from the list because the directory table never renders them.
2. **`updated_at` is never an accepted input** — it stays server-generated by
   `Supplier`/`_as_storable`, so `SupplierCreate` excludes it.
3. **Auth flows do not echo email.** `POST /users` returns only `{id}`. `login`,
   `forgot-password`, and `reset-password` already return tokens/messages only.
   `GET /auth/me` **does** return the caller's own `email` because the profile view
   depends on it.
4. **`uuid` is internal.** It is required server-side to stamp inventory orders
   (`user_uuid`) but is never returned by the user/profile schemas.
5. **`user_id` is internal.** `ProfileResponse` exposes the profile fields the client
   renders; the owning FK is dropped.
6. **Inventory order history stays flat.** `OrderRead` is a deliberate flat projection
   (asset name/SKU denormalised instead of embedding the asset object) and keeps
   `user_uuid` because the UI displays it. No nesting is introduced.
7. **Inventory write endpoints keep dedicated input schemas** (`AssetCreate`,
   `AssetEntryCreate`, `AssetExitCreate`) and never accept the read schema.
8. **`GET /api/incidents/results/export` is a documented `response_model` exception.**
   It streams a CSV file (`StreamingResponse`, `text/csv`), so a Pydantic body model
   does not apply. It will declare `response_class=StreamingResponse` plus explicit
   `responses` metadata instead.
9. **Liveness routes (`GET /` in both services) get a typed `HealthResponse`** so no
   endpoint returns an untyped dict.

## 6. Cross-cutting findings

| # | Finding | Location | Impact |
| --- | --- | --- | --- |
| F1 | `POST /users` echoes `email` and `uuid` | `routes/users.py` | Auth-flow data exposure; contract includes fields the client discards. |
| F2 | User list returns `email`/`uuid` for every account | `routes/users.py` | Over-fetch; no consumer needs it. |
| F3 | Supplier list reuses the full detail schema | `routes/suppliers.py` | Larger payloads (`notes`) than the table uses. |
| F4 | `ProfileResponse` leaks the `user_id` FK | `models.py` | Internal relational detail in the public contract. |
| F5 | `GET /auth/me` returns `uuid`/`is_active`/`created_at` | `routes/auth.py` | Over-exposure; the UI reads only `id`, `email`, `role`, `profile`. |
| F6 | Two `DELETE` routes return untyped dicts | `routes/{suppliers,users}.py` | Undefined contract for a 200 body. |
| F7 | Analyzer returns `score_counts` the UI never reads | `analyzer-api.py` | Unnecessary payload; also lacks a declared model. |
| F8 | `POST /suppliers` uses the domain model `Supplier` as its request body | `routes/suppliers.py` | Input/output concerns not separated; `updated_at` is client-suppliable. |
| F9 | Both `GET /` probes return untyped dicts | `main.py` (x2) | No response contract for a documented endpoint. |

No endpoint in the application currently returns a raw ORM object with `hashed_password`.
The provider does filter responses via existing `response_model`s, so the exposure is
limited to the fields listed above rather than the full ORM columns.

## 7. Implementation checklist (Phases 2–3)

- [x] Add the schemas in §4 to `Supply_directory_API/models.py`, `Inventory-API/schemas.py`, and `analyzer-api.py`.
- [x] Declare `response_model` on every route marked ⚠️/❌ (routes: 1–19, 20, 27).
- [x] Introduce `SupplierCreate` so `POST /suppliers` no longer reuses `Supplier`.
- [x] Slim list endpoints (`GET /suppliers`, `GET /users`) to their `*ListItem` schemas.
- [x] Return `UserRegistrationResponse` from `POST /users` (no email/password/uuid).
- [x] Update `uis/backoffice` types to match (§8).
- [x] Update affected tests and add happy/edge/failure serializer tests; run `uv run pytest` (140 passed).
- [x] Spot-check ≥3 endpoints in `/docs`.
- [x] Mark every row ✅ once implemented (see §10).

## 8. Frontend contract updates required

| File | Change |
| --- | --- |
| `uis/backoffice/lib/auth/types.ts` | Drop `Profile.user_id`; align `AuthUser`/`UserWithProfile` with `CurrentUserWithProfile`. |
| `uis/backoffice/app/suppliers/page.tsx` | `SupplierRecord` list type drops `notes`/`updated_at` (detail/update responses still carry them). |
| `uis/backoffice/app/incidents/page.tsx` | No change — already omits `score_counts`. |

## 9. Out of scope

- No authentication, persistence, or routing refactors.
- No change to TinyDB/Supabase storage.
- The CSV export route keeps its streaming behaviour.
- `uis/talent-pipeline-tracker` targets a separate external API and is not part of this
  backend's surface area.

## 10. Changes applied (final state — all endpoints ✅)

| Endpoint(s) | Change applied | Final |
| --- | --- | --- |
| `GET /` (both services) | `response_model=HealthResponse` | ✅ |
| `POST /suppliers` | dedicated input `SupplierCreate` (no client `updated_at`); output `SupplierRecord` | ✅ |
| `GET /suppliers` | `list[SupplierListItem]` — drops `notes`, `updated_at` | ✅ |
| `GET /suppliers/{id}`, `PATCH .../rate`, `PATCH .../status` | `SupplierRecord` detail (unchanged) | ✅ |
| `DELETE /suppliers/{id}` | `response_model=MessageResponse` | ✅ |
| `POST /auth/login` | `TokenResponse` (unchanged) | ✅ |
| `GET /auth/me` | `CurrentUserWithProfile` — `id`, `email`, `role`, `profile`; drops `uuid`, `is_active`, `created_at` | ✅ |
| `POST /auth/{forgot,reset,change}-password` | `MessageResponse` (unchanged) | ✅ |
| `POST /users` | `UserRegistrationResponse{id}` — no `email`/`password`/`uuid` | ✅ |
| `GET /users` | `list[UserListItem]{id,role,is_active}` | ✅ |
| `GET /users/{id}`, `PUT /users/{id}` | `UserDetail` — drops `uuid` | ✅ |
| `DELETE /users/{id}` | `response_model=MessageResponse` | ✅ |
| `GET/PUT /profiles/me` | `ProfileResponse` — drops internal `user_id` | ✅ |
| `GET /inventory/**` (all) | already serialized (dedicated create/read schemas, flat `OrderRead`) | ✅ |
| `POST /api/incidents/analyze` | `response_model=IncidentAnalysisResponse` — drops internal `score_counts` | ✅ |
| `GET /api/incidents/results/export` | documented `response_model` exception; `response_class=StreamingResponse` + `responses` metadata | ✅ |

**Tests:** `uv run pytest` (backrooms/services) → 140 passed. New suites:
`Supply_directory_API/tests/test_serialization.py` (11 contract tests) and
`APIs/tests/test_analyzer_serialization.py` (5 tests); the four existing tests that
asserted the old shapes were updated.

**Frontend:** `uis/backoffice/lib/auth/types.ts` and `app/suppliers/page.tsx` types
aligned (§8). `npm run lint` and `npm run build` pass (16 routes generated).

**Manual `/docs` spot-check:** `GET /` → `HealthResponse`; `GET /users` → array of
`UserListItem`; `POST /users` → `UserRegistrationResponse`. Response schemas confirmed
against the generated OpenAPI document.
