# Caching & Optimisation Audit — Nexova

Scope audited: `uis/` (frontend) and `backrooms/services/` (backend), framed against
`caching-optimization-context.md`.

This report documents the concrete optimisation decisions identified during the audit.
It is evidence-based: every recommendation maps to a specific file and line, and every
caching decision states cost, frequency, stability, TTL, and invalidation strategy.

---

## 1. Frontend decisions

### 1.1 Lazy loading — candidates and rationale

No `next/dynamic` or `React.lazy` is used anywhere in `uis/`. Two components are strong
candidates because they are heavy, below the fold, and conditional on user action rather
than on first paint.

#### Candidate A — Backoffice incident readout (`uis/backoffice/app/incidents/page.tsx`)

- The "Report summary" block (`page.tsx:96-158`) renders only after a CSV has been
  uploaded and analysed (`{analysis ? … : …}`). It contains a four-tile metrics grid,
  an invalid-records breakdown, category bars, status rows, and a satisfaction summary —
  the largest chunk of JSX on the page.
- **Why defer:** the summary is dead weight on the initial `/incidents` bundle for every
  session that never uploads a file (the common case). The readout only becomes relevant
  after the `POST /api/incidents/analyze` round-trip completes, so there is no UX cost to
  loading it lazily at that point.
- **Recommendation:** wrap the readout in `next/dynamic` (with `loading` fallback) or a
  `React.lazy` + `Suspense` boundary, so its markup is split out of the initial route chunk.

#### Candidate B — Backoffice "Register new supplier" form (`uis/backoffice/app/suppliers/page.tsx`)

- The registration form card (`page.tsx:558-716`) is a below-the-fold, write-only path. The
  page's dominant, high-frequency job is the read-only directory table + filters
  (`page.tsx:382-556`).
- **Why defer:** consultants spend most sessions reviewing/filtering suppliers, not
  registering new ones. Deferring the form (which includes the large category checkbox
  group) trims the `/suppliers` route payload for the common read path.
- **Recommendation:** lazy-load the form card with `next/dynamic`; it only needs to appear
  once the user scrolls to it or opts to "Register supplier".

> Note: Next.js App Router already code-splits at the route level, so route-to-route
> splitting is free. These recommendations target **intra-route** components that are
> conditional or below the fold, which is where manual lazy loading still pays off.

### 1.2 `useMemo` — the real opportunity

#### Apply: supplier renewal-date computation (`uis/backoffice/app/suppliers/page.tsx`)

- `isRenewalWithin60Days` (`page.tsx:116-135`) does non-trivial work — string→`Date`
  parsing, a UTC midnight normalisation, and a day-delta — and is invoked per row inside
  the table render (`page.tsx:477`).
- The problem: it recomputes on **every** re-render, including unrelated state changes such
  as editing a rate draft (`rateDrafts`) or toggling a row's busy flag (`rowBusy`). Those
  edits re-run date parsing for the whole table even though the renewal data is unchanged.
- **Recommendation:** memoise the annotated supplier list (or a `renewalSoonById` map)
  with `useMemo(..., [suppliers])`. The dependency array is well-defined — the computation
  depends only on `suppliers`, not on the draft/busy state. Estimated benefit is small per
  row but scales linearly with directory size and is the one genuine, non-trivial memo
  target in the served frontend.

#### Remove / do not add: trivial memoisations already present

The context explicitly warns against memoising trivial calculations. Three existing
`useMemo`s fall into that category and are candidates for removal (not bugs, but noise):

1. `moneyFormatter` — `uis/backoffice/app/suppliers/page.tsx:152-159` (a single
   `Intl.NumberFormat` instance).
2. `commentsRemaining` — `uis/website/app/application/page.tsx:118`
   (`500 - values.comments.length`, a single subtraction).
3. `candidateName` — `uis/talent-pipeline-tracker/app/candidates/[id]/page.tsx:119-125`
   (a null-coalescing fallback).

These memoise values cheaper to recompute than to manage via a dependency array. Keeping
the audit honest: the value of `useMemo` here is in the **renewal** case above, not these.

---

## 2. Backend decisions

### 2.1 Endpoint inventory

A full cost / frequency / stability assessment was performed. No caching exists today
(verified: no `functools.lru_cache`, `cachetools`, `@cache`, or TTL logic anywhere in
`backrooms/services/`).

**Supply Directory API** (`backrooms/services/Supply_directory_API/`, TinyDB JSON store):

| Endpoint | Cost | Frequency | Stability | Cache? |
|---|---|---|---|---|
| `GET /` (health) | trivial | low | n/a | no |
| `POST /auth/login` | bcrypt verify (highest CPU op) | high | per-user, fresh | **no — personalised** |
| `GET /auth/me` | TinyDB read | high | per-user | **no — personalised** |
| `POST /auth/forgot-password` | email send | low | n/a | no |
| `POST /auth/reset-password` | token consume + write | low | n/a | no |
| `POST /auth/change-password` | bcrypt + write | low | per-user | **no — personalised** |
| `POST /users` (register) | write | low | n/a | no |
| `GET /users` | TinyDB read | low (admin) | low | no (tiny, admin-only) |
| `GET /users/{id}` | TinyDB read | low | per-user | **no — ownership-scoped** |
| `PUT /users/{id}` | write | low | n/a | no |
| `DELETE /users/{id}` | write | low | n/a | no |
| `POST /suppliers` | write | low | n/a | no (invalidates) |
| `GET /suppliers` | TinyDB read-all + filter | **high** | **high** | **yes** |
| `GET /suppliers/{id}` | TinyDB read | low | high | optional (covered by list) |
| `PATCH /suppliers/{id}/rate` | write | low | n/a | no (invalidates) |
| `PATCH /suppliers/{id}/status` | write | low | n/a | no (invalidates) |
| `DELETE /suppliers/{id}` | write | low | n/a | no (invalidates) |
| `GET /profiles/me` | TinyDB read | high | per-user | **no — personalised** |
| `PUT /profiles/me` | write | low | per-user | **no — personalised** |

**Inventory API** (`backrooms/services/Inventory-API/`, Supabase Postgres via SQLModel):

| Endpoint | Cost | Frequency | Stability | Cache? |
|---|---|---|---|---|
| `GET /` (health) | trivial | low | n/a | no |
| `GET /inventory/products` | 1 asset query + 2 grouped aggregates | **high** | **high** | **yes** |
| `POST /inventory/products` | write | low | n/a | no (invalidates) |
| `GET /inventory/products/{id}` | 1 asset + 2 aggregates | low | high | optional |
| `POST /inventory/orders/inbound` | write | medium | n/a | no (invalidates) |
| `POST /inventory/orders/outbound` | write | medium | n/a | no (invalidates) |
| `GET /inventory/orders` | 3 queries + in-memory join/sort | medium | high | optional |

**Analyzer API** (`backrooms/services/APIs/analyzer-api.py`):

| Endpoint | Cost | Frequency | Stability | Cache? |
|---|---|---|---|---|
| `POST /api/incidents/analyze` | CSV parse + full analysis | low | per-upload | **no** |
| `GET /api/incidents/results/export` | streams `_last_metrics` | low | per-session | **no** |

### 2.2 Cached endpoints (the two selected)

Both selections meet the cost + frequency + stability test, and both are shared (not
personalised) so a process-wide cache key is safe.

#### Endpoint 1 — `GET /suppliers`

- **Operation cost:** `list_suppliers` (`routes/suppliers.py:78-96`) opens the TinyDB JSON
  file and loads every document (`table.all()`), then filters in Python. Repeated file
  opens + deserialisation on each call.
- **Call frequency:** high — the backoffice `/suppliers` page re-fetches on every
  country/category filter change (`app/suppliers/page.tsx:161-208`), and again after every
  write (`loadSuppliers` is re-invoked on create/rate/status).
- **Data stability:** high — the directory changes only via the four write routes
  (`POST`, two `PATCH`, `DELETE`). Supplier contracts are monthly/quarterly artefacts, not
  per-request.
- **Cache key:** not personalised — `SupplierListItem` (`id, name, country, categories,
  monthly_rate, currency, status, contract_renewal_date, contact_email`) is the same for
  every authenticated user; `notes`/`updated_at` are already stripped from the list
  projection. A shared key is a performance gain, not a data leak.
- **TTL chosen:** **30 seconds**.
- **Invalidation:** clear the cache on `POST /suppliers`, `PATCH /suppliers/{id}/rate`,
  `PATCH /suppliers/{id}/status`, and `DELETE /suppliers/{id}`. Writes are also immediately
  re-read by the client, so the UI never shows a stale row after a mutation.

#### Endpoint 2 — `GET /inventory/products`

- **Operation cost:** `list_products` (`routers/inventory.py:63-67`) runs one `SELECT`
  over `assets` plus `_stock_map` (`inventory.py:36-42`), which issues two grouped
  aggregate queries (one per order table). Three queries per call.
- **Call frequency:** high — hit by the products page (`app/inventory/products/page.tsx`)
  **and** by both order forms (`inbound/page.tsx` and `outbound/page.tsx` each call
  `listAssets()` to populate the asset selector). Three distinct screens share this cost.
- **Data stability:** high — stock is derived solely from order rows; it changes only when
  an inbound/outbound order (or a product) is written.
- **Cache key:** `GET /inventory/products` is a public read (no `Depends(get_current_user)`),
  returning a flat asset list with `current_stock`. Fully shareable.
- **TTL chosen:** **15 seconds** (shorter than suppliers because stock is an operational
  signal the outbound form reads to reject over-allocation client-side).
- **Invalidation:** clear on `POST /inventory/products`, `POST /inventory/orders/inbound`,
  and `POST /inventory/orders/outbound`.

#### Optional third — `GET /inventory/orders`

Read-only ledger (`inventory.py:139-181`), same write-invalidation surface as products. Left
as a documented follow-up; the two endpoints above already satisfy the milestone and orders
is lower-frequency than products.

### 2.3 Caching mechanism

The services run single-process (one Uvicorn worker in dev, see `memory-bank/techContext.md`),
with no Redis wired into the stack. The recommended mechanism is an **in-memory TTL cache
module** shared by both apps:

- A small `cache` helper (a `dict` keyed by route + query, storing `(expires_at, value)`)
  with `get_or_set(key, ttl, compute_fn)` and `invalidate(key)`.
- `functools.lru_cache` alone is insufficient here because it lacks TTL-based expiry and
  explicit invalidation, which the freshness tradeoff (section 3) requires.
- Each write route calls `invalidate(...)` after a successful commit — mirroring the
  inventory service's existing "recompute stock from a single grouped aggregate" philosophy.

> ⚠️ Personalisation guard (per the context warning): nothing below uses a shared cache key
> for private data. `login`, `me`, `profiles/me`, and `users/{id}` are explicitly **not**
> cached (section 4). A future `GET /suppliers` variant that returned per-user data (e.g.
> private notes) would need a user-scoped key or must stay uncached.

---

## 3. Tradeoffs acknowledged

### 3.1 Supplier directory — 30s staleness

Choosing a 30s TTL means a supplier's rate/status change is invisible to *other* users'
cached responses for up to 30 seconds. This is acceptable because:

1. The **acting user always sees the fresh row** — every write route invalidates the cache,
   and the backoffice client re-fetches immediately after a mutation (`app/suppliers/page.tsx:277`
   calls `loadSuppliers()` after create; rate/status updates patch state directly).
2. Supplier contracts are low-churn (monthly/quarterly renewals), so a 30s window has a
   negligible probability of racing a genuine contract edit.
3. The cost saved (a JSON file open + full deserialise per filtered request) is incurred on
   the highest-frequency read path in the directory.

The tradeoff is explicitly **not** zero-staleness: if Nexova later makes rate edits
realtime-critical across concurrent users, TTL should drop to a few seconds or move to
write-through/Redis — at higher infrastructure cost.

### 3.2 Inventory products — 15s staleness on stock

A 15s TTL means the products table can lag an order write by up to 15s. This is acceptable
because the **write path is authoritative regardless of cache**: `create_outbound_order`
(`inventory.py:114-136`) recomputes `_stock_map` from the database inside the request, so it
can never approve an over-allocation from a stale cache. The cache only affects read
rendering, and every order write invalidates it, so post-write navigation shows correct stock
immediately. The residual staleness applies only to a second viewer in the 0–15s window
after another user's write.

---

## 4. What was not cached and why

1. **`POST /auth/login`** — the single most expensive operation (bcrypt `verify_password`,
   `routes/auth.py:74`), but it is inherently personalised and request-scoped. A shared cache
   key would be a credential-confusion/leak bug, not a performance win. Left uncached.
2. **`GET /auth/me`, `GET /profiles/me`, `PUT /profiles/me`, `GET /users/{id}`** — return
   per-user data. The context's personalisation warning applies directly; caching these
   without a user-scoped key (and `me` responses are per-token anyway) is unsafe.
3. **`POST /api/incidents/analyze`** — compute-heavy, but every request is a *different*
   uploaded CSV. There is no reusable key (content-hashing uploads would store sensitive
   customer data, contradicting the privacy-first framing already used by the incidents UI).
4. **`GET /api/incidents/results/export`** — streams the in-memory `_last_metrics` global
   (`analyzer-api.py:34`), which is already effectively "cached" as a side effect of the last
   analysis; adding a TTL cache would add a second, conflicting source of truth.
5. **`GET /users`** — admin-only, tiny document set, low frequency. Caching would add
   invalidation complexity for no measurable gain.
6. **`GET /suppliers/{id}`** — low frequency (single-record read); its data is already covered
   by the `GET /suppliers` list cache for the list view, and a per-id cache would duplicate
   invalidation surface. Left uncached; revisit only if a supplier detail screen is added.

---

## Summary of next actions (for implementation)

1. Add a shared in-memory TTL cache module under `backrooms/services/` and wire it into both
   `GET /suppliers` and `GET /inventory/products` (TTLs 30s / 15s).
2. Add `invalidate(...)` calls to the six write routes listed in §2.2.
3. Lazy-load the incident readout and the supplier registration form via `next/dynamic`.
4. Add the `useMemo` for the supplier renewal computation (`[suppliers]` dependency), and
   remove the three trivial memoisations noted in §1.2.
5. Add/update tests per `.agents/rules/test-coverage.md` (happy / edge / failure) for the
   cache module and its invalidation, and run the targeted suites before commit.

---

## Implementation status (2026-10-18)

All five actions above are implemented and validated.

1. **Cache module** — `backrooms/services/cache.py` (new): thread-safe `TtlCache`
   (`get`/`set`/`invalidate`/`clear`, `time.monotonic` TTL).
2. **Caching + invalidation wired** — `Supply_directory_API/routes/suppliers.py`
   (`GET /suppliers`, 30s, invalidated on create/rate/status/delete) and
   `Inventory-API/routers/inventory.py` (`GET /inventory/products`, 15s, invalidated on
   product/inbound/outbound writes).
3. **Lazy loading** — `components/incidents/IncidentReadout.tsx` and
   `components/suppliers/SupplierRegistrationForm.tsx` (new), imported via `next/dynamic`
   with `loading` fallbacks from `incidents/page.tsx` and `suppliers/page.tsx`.
4. **`useMemo` + memo cleanup** — `lib/suppliers.ts` (new) holds `isRenewalWithin60Days`;
   `suppliers/page.tsx` memoizes `renewalSoonById` on `[suppliers]`; removed the trivial
   `moneyFormatter`, `commentsRemaining`, and `candidateName` memoisations.
5. **Tests** — `Supply_directory_API/tests/test_cache.py` (new, `TtlCache` happy/edge/failure
   + route invalidation), `Inventory-API/tests/test_inventory.py` (order-write invalidation),
   `uis/backoffice/lib/__tests__/suppliers.test.ts` (new, `isRenewalWithin60Days`).

Validation results:
- `uv run pytest` (backrooms/services): **148 passed** (was 140).
- `npx jest` (repo root): **32 passed** across 5 suites.
- `npm run lint` + `npm run build`: passed for `uis/backoffice`, `uis/website`, and
  `uis/talent-pipeline-tracker` (all routes generated).

