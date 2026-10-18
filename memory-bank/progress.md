# Progress

# parseApiError de-duplication (2026-10-18)

Scope changed:
1. `uis/backoffice/lib/api/errors.ts` (new) — shared `parseApiError`.
2. `uis/talent-pipeline-tracker/lib/api/errors.ts` (new) — shared `parseApiError`.
3. Removed the local copies from `backoffice/lib/inventory.ts`, `backoffice/lib/suppliers.ts`,
   `backoffice/lib/auth/session.ts`, and `talent-pipeline-tracker/lib/auth/session.ts`;
   all now import the shared module.
4. `backoffice/app/suppliers/page.tsx`, `backoffice/components/suppliers/SupplierRegistrationForm.tsx`
   — import `parseApiError` from `@/lib/api/errors`.
5. `backoffice/lib/__tests__/inventory.test.ts`, `talent-pipeline-tracker/__tests__/session.test.ts`
   — updated imports to the shared module.

What changed:
1. Four identical `parseApiError` copies collapsed to one per app (3 → 1 in backoffice,
   1 → 1 in tracker). No behaviour change.
2. `talent-pipeline-tracker/lib/api/client.ts` `parseApiErrorBody` left untouched: it is a
   distinct raw-body + status-fallback variant, not a duplicate of `parseApiError`.

Validation performed:
1. `npx jest` (repo root): 32 passed across 5 suites.
2. `npm run lint` + `npm run build`: passed for `uis/backoffice` and
   `uis/talent-pipeline-tracker` (all routes generated; no warnings).
3. No protected path modified.

Remaining risks / notes:
1. `parseApiErrorBody` in the tracker `lib/api/client.ts` still overlaps conceptually with the
   shared helper; merging would require reconciling the `trim()`/status-fallback behaviour.

# Caching & optimisation implementation (2026-10-18)

Implemented the recommendations from `CACHING_REPORT.md` §5.

Scope changed:
1. `backrooms/services/cache.py` (new) — thread-safe `TtlCache` (get/set/invalidate/clear).
2. `backrooms/services/Supply_directory_API/routes/suppliers.py` — cached `GET /suppliers`
   (key includes country/category, TTL 30s); invalidated on create/rate/status/delete.
3. `backrooms/services/Inventory-API/routers/inventory.py` — cached `GET /inventory/products`
   (TTL 15s); invalidated on product/inbound/outbound writes.
4. `backrooms/services/conftest.py`, `Inventory-API/tests/conftest.py` — per-test cache-clear
   fixtures wired into `client`/`inventory_client` (prevents cross-test cache leaks).
5. `backrooms/services/Supply_directory_API/tests/test_cache.py` (new) — `TtlCache`
   happy/edge/failure + supplier list invalidation test.
6. `backrooms/services/Inventory-API/tests/test_inventory.py` — added order-write
   invalidates-products-cache test.
7. `uis/backoffice/lib/suppliers.ts` (new) — shared supplier types/constants +
   `parseApiError` + `isRenewalWithin60Days`.
8. `uis/backoffice/components/incidents/IncidentReadout.tsx` (new) and
   `components/suppliers/SupplierRegistrationForm.tsx` (new) — extracted for lazy loading.
9. `uis/backoffice/app/incidents/page.tsx`, `app/suppliers/page.tsx` — `next/dynamic` imports;
   `suppliers` also gained the `renewalSoonById` useMemo and module-level `moneyFormatter`.
10. `uis/website/app/application/page.tsx`, `uis/talent-pipeline-tracker/app/candidates/[id]/page.tsx`
    — removed trivial `useMemo`s.
11. `uis/backoffice/lib/__tests__/suppliers.test.ts` (new) — `isRenewalWithin60Days`
    happy/edge/failure.
12. `CACHING_REPORT.md` — added "Implementation status" section.

What changed:
1. `GET /suppliers` and `GET /inventory/products` now serve from an in-memory TTL cache and
   are invalidated on every write route that mutates their underlying data.
2. Two heavy/conditional backoffice sections are code-split via `next/dynamic` with loading
   fallbacks; the supplier renewal-date computation is memoised on `[suppliers]`; three
   trivial memoisations removed.

Validation performed:
1. `uv run pytest` (backrooms/services): 148 passed (was 140; +8 cache/invalidation tests).
2. `npx jest` (repo root): 32 passed across 5 suites (+4 suppliers tests).
3. `npm run lint` + `npm run build` passed for `uis/backoffice`, `uis/website`, and
   `uis/talent-pipeline-tracker` (all routes generated).
4. No protected path modified (`.env`, `CONTEXT.md`, `infra/**`, `data/raw/**`, lockfiles
   untouched).

Remaining risks / notes:
1. Cache is process-local (single-worker dev model); multi-worker/Redis requires replacing
   `backrooms/services/cache.py` with a shared store.
2. RESOLVED — `parseApiError` was unified into `lib/api/errors.ts` per app (see the
   de-duplication entry above); only the tracker's distinct `parseApiErrorBody` variant remains.

# Caching & optimisation audit (2026-10-18)

Scope audited: `uis/` and `backrooms/services/` against `caching-optimization-context.md`.

What changed:
1. `CACHING_REPORT.md` (new, repo root) — evidence-based audit with the four required
   sections (frontend decisions, backend decisions, tradeoffs, what was not cached).

Findings (audit-only, no code changed):
1. Backend: no caching exists today. Recommended targets — `GET /suppliers` (TinyDB
   read-all + filter, TTL 30s) and `GET /inventory/products` (3 queries incl. grouped
   aggregates, TTL 15s), both invalidated on their write routes. Personalised/request-scoped
   endpoints (`login`, `me`, `profiles/me`, `users/{id}`) explicitly excluded.
2. Frontend: no `next/dynamic`/`React.lazy` anywhere. Recommended lazy-load targets —
   backoffice incident readout (`incidents/page.tsx:96-158`) and supplier registration form
   (`suppliers/page.tsx:558-716`). Real `useMemo` target — supplier renewal-date computation
   (`suppliers/page.tsx:116-135,477`) keyed on `[suppliers]`; three existing memoisations are
   trivial and flagged for removal.

Validation performed:
1. Exemption declared: documentation/markdown only, no functional behaviour
   (`.agents/rules/test-coverage.md` exception #1), so no tests are required.
2. No protected path modified (`.env`, `CONTEXT.md`, `infra/**`, `data/raw/**` untouched).

Remaining risks / notes:
1. Report is a plan, not an implementation; §5 lists the six next actions (cache module +
   invalidation wiring, two lazy-loads, one useMemo + trivial-memo cleanup, tests).
2. TTLs (30s/15s) and the single-worker in-memory cache assumption depend on the dev
   deployment model; revisit for multi-worker/Redis before production.

# Backend serialization audit + refactor (2026-10-14)

Scope changed:
1. `docs/serialization-audit.md` (new) — full endpoint audit and target contract.
2. `backrooms/services/Supply_directory_API/models.py` — new/changed schemas.
3. `backrooms/services/Supply_directory_API/routes/{suppliers,users,auth,profiles}.py`,
   `main.py` — response_model wiring and slim projections.
4. `backrooms/services/Inventory-API/schemas.py`, `main.py` — `HealthResponse` + typed root.
5. `backrooms/services/APIs/analyzer-api.py` — `IncidentAnalysisResponse` + documented export.
6. `backrooms/services/pyproject.toml` — added `APIs/tests` to pytest `testpaths`.
7. Tests: `Supply_directory_API/tests/test_serialization.py` (new, 11),
   `APIs/tests/test_analyzer_serialization.py` (new, 5);
   updated `test_register.py` (2), `test_users.py` (1), `Inventory-API/tests/test_inventory.py` (1).
8. `uis/backoffice/lib/auth/types.ts`, `uis/backoffice/app/suppliers/page.tsx` — type sync.

What changed (all 28 endpoints; branch `backend-serialization-audit`):
1. Every endpoint now declares an explicit `response_model`. The two `GET /` probes return
   typed `HealthResponse`; the two `DELETE` routes return `MessageResponse`; the analyzer
   `analyze` route returns `IncidentAnalysisResponse`.
2. `POST /suppliers` now takes a dedicated input schema `SupplierCreate` (no client-supplied
   `updated_at`); `Supplier` was split into `SupplierBase` + `SupplierCreate`/`Supplier`, with
   `SupplierRecord`/`SupplierListItem` projections.
3. List endpoints slimmed to consumer fields: `GET /suppliers` → `SupplierListItem` (drops
   `notes`, `updated_at`); `GET /users` → `UserListItem{id,role,is_active}` (drops email/uuid).
4. Sensitive/internal field removal: `POST /users` returns `UserRegistrationResponse{id}`
   (no email/uuid/password); `GET /auth/me` returns `CurrentUserWithProfile`
   (`id,email,role,profile` only); `GET/PUT /users/{id}` return `UserDetail` (no uuid);
   `ProfileResponse` drops the internal `user_id` FK. `email` remains on `GET /auth/me` only.
5. Analyzer response drops internal `score_counts`; the CSV export is documented as a
   `response_model` exception with `response_class`/`responses` metadata.
6. Inventory-API was already correctly serialized (dedicated create/read schemas + flat
   `OrderRead`); only its root probe needed a model. `user_uuid` stays on order responses
   because the orders UI renders it (documented decision).

Validation performed:
1. `uv run pytest` from `backrooms/services` passed 140/140 (was 124; +16 new/updated across
   the serializer contract suites and the analyzer suite). Py-compile and import smoke passed
   for all three apps.
2. Response schemas confirmed against generated OpenAPI for all three apps (list endpoints
   return arrays of the slim item schemas; `/` → `HealthResponse`; export → `text/csv`).
3. `npm run lint` and `npm run build` in `uis/backoffice` passed; all 16 routes generated.
4. No protected path modified (`.env`, `CONTEXT.md`, `infra/**` untouched). Tests run against
   isolated temp TinyDB and in-memory SQLite.

Remaining risks / notes:
1. `GET /users` and `GET /users/{id}` have no current UI consumer; their schemas are shaped for
   admin use and tests. Revisit if an admin screen is added.
2. `POST /users` no longer echoes `email`; this is an intentional API-contract change per the
   audit. The backoffice `register()` already discarded the body and logs in next, so no
   frontend change was needed.
3. The analyzer `results/export` route intentionally has no `response_model` (CSV stream);
   documented in the audit and covered by a test.
4. Inventory order responses still expose `user_uuid`/`asset_id`; kept because the orders UI
   displays the UUID and the flat projection is deliberate. Confirm before removing.

# Frontend performance refactor — website + backoffice (2026-10-13)

Scope changed:
1. `uis/website/app/page.tsx`, `app/application/page.tsx`, `app/globals.css`.
2. `uis/website/components/SiteHeader.tsx` (new), `components/SiteFooter.tsx` (new); removed
   `components/Header.tsx`.
3. `uis/website/hooks/useApplicationForm.ts` (new), `lib/applicationValidation.ts` (new),
   `lib/__tests__/applicationValidation.test.ts` (new).
4. `uis/website/public/robots.txt`, `public/sitemap.xml` (new).
5. `uis/backoffice/components/auth/AuthGuard.tsx`, `app/globals.css`.
6. `uis/backoffice/components/auth/AuthCard.tsx` (new), `hooks/useAuthSubmit.ts` (new).
7. `uis/backoffice/lib/api/errors.ts` (new), `lib/api/__tests__/errors.test.ts` (new);
   `lib/auth/session.ts`, `lib/inventory.ts`, `app/suppliers/page.tsx` now import the shared
   helper.
8. `uis/backoffice/app/{login,register,forgot-password,reset-password,account/change-password}/page.tsx`.
9. `jest.config.js` (added `uis/website` to `roots`), `uis/backoffice/lib/__tests__/inventory.test.ts`
   (import moved to the shared module).
10. `memory-bank/techContext.md`, `memory-bank/progress.md`.

What changed (performance, audit §4):
1. Website hero (audit §4.3): replaced the inline `background-image` of the 2.7 MB `bphoto1.png`
   with `next/image` (`fill`, `preload`, `fetchPriority="high"`, `sizes="100vw"`,
   `object-cover`). Next 16 deprecates `priority` in favour of `preload`, verified in
   `node_modules/next/dist/docs`. The `.hero-motion` keyframes were repointed from
   `background-position` to `object-position` so the pan animation is preserved; reduced-motion
   still disables it.
2. Service/why images (audit §4.4): added per-breakpoint `sizes` so mobile no longer requests
   `w=1920` for a 339 px slot.
3. Backoffice render gating (audit §4.2): `AuthGuard` no longer replaces the route with a
   full-screen "Checking session..." placeholder. It renders `children` immediately (so the LCP
   text paints pre-hydration) and keeps the redirect plus a non-blocking status pill.
4. Contrast (audit §4.6): website white-on-`rose-500` CTAs/modal buttons moved to `rose-600`
   (~4.70:1, AA); backoffice `.nav-icon` `#6f8889` → `#7f9a9b` (~5.2:1 on `#14262e`, AA at 10 px).
5. SEO (audit §4.8): added `public/robots.txt` (with sitemap reference) and `public/sitemap.xml`.

What changed (refactors, audit §5 — all five):
1. §5.1 `parseApiError` de-duplicated into `lib/api/errors.ts`; the three copies (auth session,
   inventory lib, suppliers page) now import it. Existing test coverage moved with the module.
2. §5.2 `SiteFooter` extracted from the two website pages.
3. §5.3 `SiteHeader` extracted with a `linkMode: "anchor" | "route"` prop replacing both the
   anchor-only `Header.tsx` and the route-prefixed inline header on the application page.
4. §5.4 `AuthCard` (+ `AuthAlert`, shared `AUTH_INPUT_CLASS`/`AUTH_SUBMIT_CLASS`) and
   `useAuthSubmit` extracted across the five backoffice auth pages, preserving per-page copy,
   field errors, redirects, and the forgot-password "generic error only" behaviour.
5. §5.5 `useApplicationForm` hook extracted over the pure `validateField`/`validateAll` module;
   the application page is now mostly JSX.

Out of scope (dev-build artefacts, per audit §4.1/§4.5/§4.7): the unminified dev bundle,
`webpack.js`, source maps, and render-blocking CSS. Per the developer's instruction the served
build stays on `next dev`, so these cannot be addressed and are documented rather than "fixed".

Validation performed:
1. `npx jest` from the repo root passed 37/37 across 6 suites (existing 28 + 9 new across the
   shared `parseApiError` and website validation modules).
2. `npm run lint` and `npm run build` passed in `uis/website` (routes `/` and `/application`) and
   `uis/backoffice` (all 14 routes generated).
3. Two pre-existing validation quirks were confirmed and preserved (not fixed) while writing
   tests: the phone regex rejects space-separated digit groups, and an empty `experience` field
   passes because `Number("") === 0`.
4. No live browser/API run was performed (dev servers were not running in this session); the
   changes were validated via typecheck, lint, build, and unit tests only.

Remaining risks / notes:
1. The `performance-audit/before/*` numbers are from `next dev`; the post-refactor Lighthouse
   run also used the dev build, so the comparison is like-for-like. `performance-audit/after/REPORT.md`
   now records the results: Performance rose website 72→83 / 53→66 and backoffice 60→80 / 46→69
   (desktop/mobile), website Accessibility 96→100 and SEO 92→100. Backoffice Accessibility stayed
   95: the cited `.nav-icon` failure was fixed (5 nodes removed) but ~50 other sub-AA dashboard
   tokens remain. Website bytes fell 6,369 → ~3,600 KiB via the hero `next/image`; backoffice LCP
   fell 3.6→0.6 s / 20.1→2.7 s at unchanged bytes via the removed render gate. Dev-bundle TBT/TTI
   are unchanged and remain the reason scores stay below 90.
2. `AuthGuard` now renders protected route content optimistically (one tick before the token
   check resolves). The backoffice overview data is non-sensitive sample data, matching the
   audit's recommended trade-off; if protected data becomes sensitive, revisit this.
3. `memory-bank/projectbrief.md` remains stale (still describes `uis/landing_page` +
   `uis/talent-pipeline-tracker`); `techContext.md` was updated to reflect the current
   website/backoffice stack.
4. The website source images (`bphoto1.png`, `bphoto5.jpg`) remain large on disk; only the
   delivered bytes are optimised by `next/image`.

# Monorepo Docker containerization for development (2026-10-09)

Scope changed:
1. `docker-compose.yml` (root, new) — `ui`, `suppliers-api`, `inventory-api` on an explicit `nexova-net`.
2. `.env` (root, new, gitignored, developer-approved protected path) + `.env.example` (root, new).
3. `uis/Dockerfile`, `uis/.dockerignore`, `uis/start.sh` (new).
4. `backrooms/services/Dockerfile`, `backrooms/services/.dockerignore` (new).
5. `backrooms/services/requirements.txt` (new, generated by `uv export`).
6. `memory-bank/progress.md`.

What changed:
1. UI image `node:22-alpine` installs `uis/website` and `uis/backoffice` deps separately (`npm ci`) and runs both via `start.sh` on 3000 (website) and 3001 (backoffice). Covered by `.dockerignore` (`node_modules`, `.next`, `.env*`, `*.log`). Compose bind-mounts `./uis:/app/uis` plus a read-only `./scripts:/app/scripts` (the backoffice overview imports the repo-root `../../../scripts/src/sample-usage`, which lies outside the `./uis` build context; Turbopack/webpack root is `/app`). Anonymous volumes mask host `node_modules` from the container's.
2. Backend image `python:3.13-slim` installs `uv` (official image) and runs `uv pip install --system -r requirements.txt`. `requirements.txt` was generated from the existing lock with `uv export --frozen --no-dev --no-emit-project --no-hashes --format requirements-txt` (lockfiles untouched, per the ticket wording). Covered by `.dockerignore` (`__pycache__`, `*.pyc`, `.env*`, `tests/`, `*.log`, `.venv`, caches).
3. Two sibling Compose services share that image: `suppliers-api` (Supply_directory_API, 8000, `--reload`, default CMD) and `inventory-api` (Inventory-API, 8001, `--reload`, Compose `command` override). Both bind-mount `./backrooms/services`.
4. All configuration comes from the root `.env` (`env_file` for the APIs; `${...}` interpolation for the UI's `NEXT_PUBLIC_*` values), so nothing is hardcoded in YAML/Dockerfiles. `NEXT_PUBLIC_*` stay `http://localhost:8000/8001` because the browser runs on the host, outside the Docker network.
5. Dev servers run as `next dev --webpack` rather than the Next 16 Turbopack default: Turbopack did not detect host file edits over the Docker Desktop Windows/OneDrive bind mount. Webpack honours `WATCHPACK_POLLING`/`CHOKIDAR_USEPOLLING`, and Uvicorn uses `WATCHFILES_FORCE_POLLING`.

Validation performed:
1. Exemption: containerization is configuration/infrastructure with no application logic, so no unit tests are required (`.agents/rules/test-coverage.md` documented exception #3).
2. `docker compose config -q` passed; root `.env` interpolated into the UI service and confirmed gitignored.
3. `docker compose build` succeeded for all three images (first attempt hit a transient registry EOF pulling `node:22-alpine`; a retry succeeded).
4. `docker compose up -d` started all three containers; health: `GET :8000/` = `{"status":"ok","service":"supplier-directory"}`, `GET :8001/openapi.json` = 200 (Inventory lifespan `create_all` reached Supabase), website `:3000` = 200, backoffice `:3001` = 200.
5. Bind mounts verified host→container for both `uis` and `backrooms/services` via marker files.
6. Service-name DNS verified: the `ui` container resolved `suppliers-api` (172.19.0.2) and `inventory-api` (172.19.0.3); `suppliers-api`→`inventory-api` and `inventory-api`→`suppliers-api` both returned HTTP 200 by service name.
7. Hot reload verified: Uvicorn logged `WatchFiles detected changes ... Reloading` after a host edit to `main.py`; Next/webpack served a host-side existing-file edit and a newly added route file (probe reverted, temp route removed — `git diff` clean).
8. No secrets present in `docker-compose.yml` or either `Dockerfile` (grep). Lockfiles untouched; the tracked recompiled `__pycache__/main.cpython-313.pyc` was restored.

Remaining risks / notes:
1. The ticket's "service name, not localhost" criterion is verified at the network layer but not exercised by app code: every frontend fetch is client-side, so the host browser must use the published `localhost` ports. Documented in `.env.example`.
2. Webpack dev (not Turbopack) is required for reliable watching over Windows/OneDrive bind mounts; polling adds some overhead and Turbopack's `turbopack.root` config is inert in this mode (`experimental.externalDir` covers the cross-directory import instead).
3. The UI image itself does not contain `/app/scripts` (outside the `./uis` build context); the running UI depends on the compose `./scripts` bind mount. Building the image standalone would miss that import.
4. `inventory-api` requires a reachable `DATABASE_URL` at startup; if Supabase is unavailable only that service fails, while `suppliers-api` stays up.
5. Docker Desktop had to be started manually before the daemon was available in this session.

# Backoffice shell CSS cleanup (2026-10-08)

Scope changed:
1. `uis/backoffice/app/globals.css`
2. `memory-bank/progress.md`.

What changed:
1. Removed the now-dead supplier and incident shell rules that the shared `BackofficeShell` (`.bo-*`) replaced: `.supplier-nav`/`.supplier-brand*`/`.supplier-nav-link*`/`.supplier-connected`/`.supplier-main`/`.supplier-header*`/`.supplier-content` and the equivalent `.incident-*` shell rules, along with their responsive overrides.
2. Trimmed `.supplier-page`/`.incident-page` to only their CSS custom properties (the `.bo-shell` now owns layout, background, and typography). Repointed the incident footer rule from `.incident-main footer` to `.incident-page footer`.
3. Kept all content-specific rules (heroes, tables, forms, filters, badges, and the inventory views).

Validation performed:
1. Exemption: CSS-only presentation change with no functional behaviour (per `.agents/rules/test-coverage.md`), so no new tests are required.
2. `npm run lint` in `uis/backoffice` passed.
3. `npm run build` in `uis/backoffice` passed; all routes generated (supplier, incident, and the four inventory views).

Remaining risks / notes:
1. None functional. The supplier/incident views depend on the `--supplier-*`/`--incident-*` variables inherited from their page root class; removing those page classes would break the theme.

# Backoffice inventory order labels (2026-10-08)

Scope changed:
1. `uis/backoffice/app/inventory/products/page.tsx`
2. `uis/backoffice/app/inventory/orders/page.tsx`
3. `uis/backoffice/app/inventory/orders/inbound/page.tsx`
4. `uis/backoffice/app/inventory/orders/outbound/page.tsx`
5. `memory-bank/progress.md`.

What changed:
1. Renamed the user-facing inventory vocabulary from "asset entry"/"asset exit" to "inbound order"/"outbound order" across the four views: page titles, hero copy, action links/buttons, card headings, success/error messages, the order-history type badges, the empty state, and the loading fallbacks.
2. Left the API/domain identifiers untouched (`exit_type`/`Exit type`, the `inbound`/`outbound` kind values, and the routes). No data or behavior change.

Validation performed:
1. Exemption: this is a copy-only change with no functional behaviour (per `.agents/rules/test-coverage.md`), so no new tests are required.
2. `npm run lint` in `uis/backoffice` passed.
3. `npm run build` in `uis/backoffice` passed; all four `/inventory/*` routes generated.

Remaining risks / notes:
1. The CONTEXT document names the entities `AssetEntry`/`AssetExit`; the UI now uses the inbound/outbound order vocabulary requested by the developer. The underlying entity/route names are unchanged.

# Supply Directory API launch path fix (2026-10-08)

Scope changed:
1. `backrooms/services/Supply_directory_API/main.py` — added a `sys.path` bootstrap that puts `backrooms/` on the path before the absolute `services.*` imports.
2. `memory-bank/progress.md`.

What changed:
1. `main.py` and every internal module import via `services.Supply_directory_API.*`, which requires the `backrooms/` directory on `sys.path`. Launching `uvicorn main:app` from inside `Supply_directory_API/` (or any cwd that is not `backrooms/`) raised `ModuleNotFoundError: No module named 'services'` because only the service folder was importable.
2. Added a bootstrap mirroring `Inventory-API/main.py`: `BACKROOMS_ROOT = Path(__file__).resolve().parent.parent.parent` is inserted into `sys.path` before the `services.*` imports. This lets the app be launched directly with `python -m uvicorn main:app` from the service folder while preserving the `services.Supply_directory_API.main` import path used by pytest. No behavior change.

Validation performed:
1. `uv run python -m py_compile Supply_directory_API/main.py` passed.
2. Import smoke from `backrooms/`: `from services.Supply_directory_API.main import app` printed `Nexova Supplier Directory API`.
3. Top-level launch import from the service folder: `python -c "import main"` (outer venv) printed `Nexova Supplier Directory API`.
4. Live server on port 8123: `GET /` returned `{"status":"ok","service":"supplier-directory"}` and `/openapi.json` listed every route (`/auth/*`, `/users*`, `/profiles/me`, `/suppliers*`).
5. `uv run pytest` passed 124/124.

Remaining risks / notes:
1. Recommended launch command uses the project venv that contains uvicorn: from `backrooms/services` run `uv run uvicorn services.Supply_directory_API.main:app --reload --app-dir ..`. The inner `backrooms/services/Supply_directory_API/.venv` exists but lacks `uvicorn`, so `uv run` from inside the service folder picks an incomplete environment — use the shared `backrooms/services` venv.
2. The Supplier Directory API and the Inventory API both default to port 8000; run the Inventory service with `--port 8001` to match the backoffice `NEXT_PUBLIC_INVENTORY_API_URL`.

# Milestone 5 Nexova inventory management UI (2026-10-08)

Scope changed:
1. `uis/backoffice/lib/inventory.ts` (new) — typed integration module for every `/inventory` call.
2. `uis/backoffice/components/backoffice/BackofficeShell.tsx` (new) — shared nav/header/content shell.
3. `uis/backoffice/app/inventory/products/page.tsx`, `app/inventory/orders/page.tsx`, `app/inventory/orders/inbound/page.tsx`, `app/inventory/orders/outbound/page.tsx` (new).
4. `uis/backoffice/app/globals.css` — added `.bo-*` shell styles and `.inventory-*` view styles.
5. `uis/backoffice/app/suppliers/page.tsx`, `app/incidents/page.tsx` — migrated to `BackofficeShell`.
6. `uis/backoffice/app/page.tsx` — added an Inventory link to the overview sidebar.
7. `uis/backoffice/.env.example` — added `NEXT_PUBLIC_INVENTORY_API_URL`.
8. `jest.config.js` (roots now include `uis/backoffice`), `uis/backoffice/tsconfig.json` (exclude `__tests__`).
9. `uis/backoffice/lib/__tests__/inventory.test.ts` (new).
10. `memory-bank/progress.md`.

What changed:
1. `lib/inventory.ts` centralises all API access (no component calls `fetch`). It reuses `authorizedFetch` for the bearer token and 401 redirect, exposes `listAssets`, `listOrders`, `createInboundOrder`, `createOutboundOrder`, a `parseApiError` helper for `detail` string/array payloads, and a pure `stockLevel` helper with documented thresholds (0 = out, 1–9 = low, ≥10 = healthy).
2. Built the four context-mandated views with Nexova domain labels (Asset, asset entry, asset exit, SKU, office): products with colour-coded stock indicators and per-row entry/exit links; inbound form (asset selector by name, success clears + confirms, visible errors); outbound form (reactive available-stock readout, client over-stock warning, inline `400` message near quantity); read-only order history with inbound/outbound distinction, quantity, date, and `user_uuid`.
3. Extracted `BackofficeShell` (brand, numbered nav with `usePathname` active state, connected-status line, page header, content slot) and migrated the supplier and incident pages onto it. The home dashboard keeps its distinct metrics layout and only gained an Inventory link.
4. Route protection is unchanged: the existing global `AuthGuard` already redirects unauthenticated users on all non-public paths, so no per-page guard was added.
5. Added the backoffice to the root Jest `roots` and a happy/edge/failure suite for the integration module (stock thresholds, error parsing, and mocked-fetch happy + `400` failure paths). Used `@jest/globals` imports to stay lint/type-safe; `__tests__` is excluded from the Next build typecheck.

Validation performed:
1. `npx jest` from the repo root passed 28/28 across 4 suites (17 existing tracker tests + 11 new inventory tests).
2. `npm run lint` in `uis/backoffice` passed with no errors or warnings.
3. `npm run build` in `uis/backoffice` passed and generated `/inventory/products`, `/inventory/orders`, `/inventory/orders/inbound`, and `/inventory/orders/outbound` alongside the existing routes.

Remaining risks / notes:
1. The Inventory API is a separate service from the auth/supplier API, so the backoffice needs `NEXT_PUBLIC_INVENTORY_API_URL` (default `http://localhost:8001`). The service's `INVENTORY_ALLOWED_ORIGINS` already allows `localhost:3000/3001`, and the Inventory API shares `JWT_SECRET_KEY` with the Supply Directory auth so the same login token authorises writes.
2. The old `.supplier-nav`/`.incident-nav` shell rules remain in `globals.css` but are now unused (the shell owns that markup); removing them is a low-risk cleanup follow-up.
3. `parseApiError` is now duplicated in `lib/inventory.ts` (also present in `lib/auth/session.ts` and `app/suppliers/page.tsx`); extracting one shared helper remains a candidate.
4. No live API or browser end-to-end run was performed in this session — the pages were validated via typecheck, lint, build, and unit tests only.


# Milestone 5 Nexova inventory API with SQLModel + Supabase (2026-10-07)

Scope changed:
1. `backrooms/services/Inventory-API/` (new) — `main.py`, `database.py`, `models.py`, `schemas.py`, `routers/inventory.py`, `seed.py`, `.env.example`, `tests/`.
2. `backrooms/services/Inventory-API/.env` — replaced the loose `SUPABASE_URL` with the CONTEXT-required `DATABASE_URL` (Transaction pooler URI). Developer approved editing this protected file.
3. `backrooms/services/pyproject.toml` — added `Inventory-API/tests` to pytest `testpaths` and `Inventory-API` to coverage `source`.
4. `backrooms/services/Supply_directory_API/models.py` — added a `uuid` field to `User`/`UserResponse` (inherited by `AuthenticatedUser`).
5. `backrooms/services/Supply_directory_API/auth/services.py` — `get_user_by_id`/`get_user_by_email`/`get_user_entry_by_email` now lazily backfill a UUID for legacy user documents.
6. `testing.md`, `memory-bank/progress.md`.

What changed:
1. Standalone FastAPI service (the folder name has a hyphen, so it runs as an app root rather than an importable package) registering one `APIRouter(prefix="/inventory")` with the six CONTEXT endpoints: list/create/get assets and inbound/outbound/orders.
2. `Asset`, `AssetEntry`, `AssetExit` SQLModel models; `asset_id` is a database-level FK to `assets.id`. `current_stock` is never stored — it is computed with a single grouped aggregate per order table (no N+1) as `SUM(entries) − SUM(exits)`.
3. Separate Pydantic schemas (`schemas.py`); endpoints never return raw ORM objects. `AssetExitCreate` enforces allocation⇒`assigned_to` and consumption⇒null.
4. Outbound orders that would exceed stock are rejected with `HTTP 400` and the exact CONTEXT message before any row is written. Every order stores `current_user.uuid` sourced from TinyDB.
5. Dual DB in one app: it reuses `services.Supply_directory_API.auth.dependencies.get_current_user` (TinyDB) and a per-request SQLModel `Session` via `Depends(get_sql_session)` (Supabase). `SQLModel.metadata.create_all(engine)` runs in the FastAPI lifespan.
6. `database.py` pins `postgresql+psycopg2` because SQLAlchemy 2.1 otherwise resolves a bare `postgresql://` URL to psycopg v3, which is not installed.
7. `seed.py` seeds 6 assets, 5 entries, and 3 exits (idempotent) matching the CONTEXT tables.
8. Reads are public; writes require the TinyDB bearer token, per the milestone rule and the Nexova CONTEXT.

Validation performed:
1. `uv run pytest --cov` from `backrooms/services` passed 124/124 (108 existing + 16 new). Inventory coverage: `routers/inventory.py` 100%, `schemas.py` 100%, `models.py` 100%, `database.py` 90%, `main.py` 92%, `seed.py` 86%; suite total 94%.
2. `uv run python -m py_compile` passed for every new module.
3. Existing authentication suites still pass after the `User.uuid` change.
4. `git diff --check` passed (only benign LF→CRLF notices); recompiled tracked `Supply_directory_API/**/__pycache__/*.pyc` restored; `.env` confirmed gitignored.
5. Live Supabase validation (transaction pooler): `DATABASE_URL` connected, `uv run python seed.py` created the schema and inserted 6 assets / 5 entries / 3 exits, and an end-to-end `TestClient` smoke returned `GET /inventory/products` net stock `NXV-IT-001=12, NXV-PER-001=15, NXV-PER-002=15, NXV-OFF-001=38` with `GET /inventory/orders` = 8, matching the CONTEXT seed math. `inspect(engine)` confirmed `assets`, `asset_entries`, `asset_exits` exist with `asset_entries.asset_id` FK → `assets`.

Remaining risks / notes:
1. RESOLVED — the initial `password authentication failed for user "postgres"` was caused by stray square brackets around the password in `DATABASE_URL` (`[Gannendorf777]`). Stripping them fixed the connection; the corrected value is now in `Inventory-API/.env`.
2. The connected Supabase MCP points at a different project (`lawkjzjxxtxxmsnakazx`) than the one in `.env` (`jrznvxqznekzvwcqwycu`); no MCP DDL was applied to avoid writing to the wrong project.
3. `create_all` is dev-only per the milestone warning; adopt Alembic before production.
4. Tests run on SQLite rather than Postgres; FK/unique semantics are asserted at route level plus the DB constraints created by `create_all`.

# Test-coverage rule for functional changes (2026-10-07)

Scope changed:
1. `.agents/rules/test-coverage.md` (new) — always-active rule requiring happy, edge, and failure tests for every functional code change, with documented exemptions and anti-patterns.
2. `AGENTS.md` — added the rule to the commit workflow (new step 4, steps renumbered) and to the section 5 required rule discovery list.

What changed:
1. Added a monorepo-wide rule mandating that functional code changes (business logic, API routes, utilities, components, data transforms) ship add-or-update automated tests in the same change, each with a happy case, an edge case, and a failure case, asserting business behaviour rather than serialisation. Tests follow existing conventions (pytest in `backrooms/services`, Jest in `uis/talent-pipeline-tracker/__tests__`), and the targeted suite must be run and its result captured before the progress update and commit.
2. Documented exemptions (docs/markdown, CSS/styling, config/static markup with no logic, trivial copy changes) that must be stated in the progress entry when used.
3. Wired the rule into `AGENTS.md` section 2 (step 4, renumbering the later steps) and section 5 (required read list).

Validation performed:
1. Exemption declared: this change is governance-only (markdown docs plus one contract file), adding no functional behaviour, so under the new rule itself no tests are required.
2. `git diff --check` on the changed files (to be run at commit time) — no whitespace errors expected.

Remaining risks / notes:
1. `scripts/` and `uis/landing_page` currently have no test harness. Future functional changes there will trigger the rule and require either a harness or a documented exemption; no harness was added in this pass.
2. The rule is a policy contract, not an automated gate; enforcement relies on agents following `AGENTS.md` and reviewers checking.

# FE-019 frontend utility test suite (2026-09-22)

Scope changed:
1. `jest.config.js` (new, repo root) — ts-jest transform (inline `module: commonjs`, `isolatedModules: true`, `ignoreDeprecations: "6.0"`), node test environment, `roots` scoped to `uis/talent-pipeline-tracker`, `@/*` moduleNameMapper.
2. `uis/talent-pipeline-tracker/__tests__/` (new) — `labels.test.ts`, `storage.test.ts`, `session.test.ts`.
3. `uis/talent-pipeline-tracker/lib/auth/session.ts` — exported the previously private `parseApiError` helper so it can be unit-tested.
4. `package.json` (root) — added a `test` script (`jest --coverage`).
5. `uis/talent-pipeline-tracker/tsconfig.json` — excluded `__tests__` so `next build` does not type-check Jest files.
6. `.gitignore` — added `coverage/`.
7. `testing.md` (repo root) — added the FE-019 section and frontend run instructions.

What changed:
1. Added 17 Jest tests covering three utility functions (each with happy-path + failure-mode): `toStatusLabel`/`toStageLabel` (formatters), `hasValidSession` + token storage round-trip (token helper), and `parseApiError` (response parser). The token helper is exercised against real base64url JWTs in a mocked `window.localStorage` (node environment, no jsdom dependency).

Validation performed:
1. `npx jest --coverage` from the repo root passed 17/17 (3 suites).
2. `npm run build` in `uis/talent-pipeline-tracker` passed after the tsconfig exclusion.
3. Coverage: `lib/labels.ts` 100%, `lib/auth/storage.ts` 88%; the remaining files in the report (`client.ts`, `session.ts`) are pulled in transitively and not part of FE-019 scope.

Remaining risks / notes:
1. ts-jest 29.4.12 is paired with jest 30.5.2 (compatible per peer deps) and TypeScript 6.0.3, which required `ignoreDeprecations: "6.0"` for the deprecated `moduleResolution: node10` used by the CommonJS transform.
2. No `jest-environment-jsdom` is installed; the storage tests use a minimal in-memory `window`/`localStorage` stand-in, which is sufficient for the token helper logic but would not exercise real browser storage quirks.

# API-042 backoffice endpoint test suite (2026-09-22)

Scope changed:
1. `backrooms/services/Supply_directory_API/tests/test_suppliers.py` (new) — three-tier coverage of the `/suppliers` directory CRUD.
2. `backrooms/services/Supply_directory_API/tests/test_users.py` (new) — user management endpoints (`GET /users`, `GET/PUT/DELETE /users/{id}`) with ownership/admin authorization.
3. `backrooms/services/conftest.py` — added `admin_user`/`admin_headers` and `manager_user`/`manager_headers` fixtures (register then promote via the service layer).
4. `backrooms/services/pyproject.toml` — broadened `[tool.coverage.run] source` to include `routes/suppliers.py` and `routes/users.py`.
5. `testing.md` (repo root) — added the API-042 test plan, updated the combined coverage results, and documented the authorization-ordering finding.

What changed:
1. Added 35 backoffice tests: 21 for `/suppliers` and 14 for `/users`. Each endpoint has happy-path, edge-case, and failure-mode coverage asserting business decisions (currency/country matching, category requirements, rate-update `updated_at` refresh, non-writer `403`, ownership rules, admin-only role changes).
2. Coverage is now a single combined report across the authentication and backoffice modules via `uv run pytest --cov`.

Validation performed:
1. `uv run pytest` from `backrooms/services` passed 108/108.
2. `uv run pytest --cov` reported 90% total: `routes/suppliers.py` 98%, `routes/users.py` 98%, auth modules unchanged (auth 86–95%). Both backoffice groups exceed API-042's 60% target and auth remains above AUTH-088's 70%.
3. Confirmed the tracked `suppliers_db.json` is unmodified.

Remaining risks / notes:
1. A non-admin requesting a non-existent user id returns `403` (not `404`) because `_require_owner_or_admin` runs before the record lookup — a deliberate decision that hides record existence. The unknown-id tests therefore exercise the admin path.
2. `auth/email.py` remains at 43% by design (Resend provider call stubbed in tests).

# AUTH-088 authentication unit test suite (2026-09-22)

Scope changed:
1. `backrooms/services/conftest.py` (new) — pytest bootstrap (adds `backrooms/` to `sys.path`, sets auth env vars before import, temp-TinyDB + client + auth-header + email-stub fixtures).
2. `backrooms/services/Supply_directory_API/tests/` — eight new pytest modules: `test_security.py`, `test_register.py`, `test_login.py`, `test_me.py`, `test_forgot_password.py`, `test_reset_password.py`, `test_change_password.py`, `test_services.py`.
3. `backrooms/services/pyproject.toml` — added `[tool.pytest.ini_options]` (`testpaths`) and `[tool.coverage.run]` (`source` scoped to `auth/` + `routes/auth.py`).
4. `testing.md` (repo root) — test plan, run instructions, coverage results, and AI-assisted-workflow notes.
5. `.gitignore` — added `.coverage` and `.pytest_cache/`.

What changed:
1. Wrote 73 pytest tests covering every authentication endpoint (`POST /users`, `POST /auth/login`, `GET /auth/me`, `POST /auth/forgot-password`, `POST /auth/reset-password`, `POST /auth/change-password`) plus the token/password primitives in `auth/security.py` and the auth service layer in `auth/services.py`.
2. Each endpoint has happy-path, edge-case, and failure-mode coverage, asserting business decisions (bcrypt storage, role defaulting, enumeration resistance, single-use/expiry reset tokens, inactive-account rejection, wrong-current-password rejection) rather than response serialisation.
3. Coverage is scoped to the authentication module via `[tool.coverage.run] source` so a bare `uv run pytest --cov` reports auth-only numbers instead of the whole package.

Validation performed:
1. `uv run pytest` from `backrooms/services` passed 73/73.
2. `uv run pytest --cov` reported 87% across the authentication module (312 statements): security 93%, services 95%, dependencies 94%, routes/auth 86%, email 43% (provider call intentionally stubbed).
3. Confirmed the tracked `suppliers_db.json` is unmodified and `password_resets_db.json` is not created in the repo (tests use a temp TinyDB).

Remaining risks / notes:
1. `auth/email.py` sits at 43% because `send_password_reset_email` (the Resend HTTP call) is stubbed in endpoint tests; only the deterministic helpers (`is_email_delivery_configured`, `build_password_reset_url`) are covered. Acceptable for a unit suite — the provider boundary is not meaningful to exercise here.
2. The pre-existing standalone script `tests/test_password_recovery.py` is retained unchanged; it is not collected by pytest (no `test_*` functions) but still exercises the full reset flow when run directly.
3. Tracking of the pre-existing `__pycache__/*.pyc` files: test runs recompile them (diff noise). They are restored after validation, consistent with prior sessions; fully untracking them remains a separate cleanup needing approval.

# Error handling LOW-severity remediation (2026-09-21)

Scope changed:
1. `backrooms/services/APIs/analyzer-api.py`
2. `backrooms/services/Supply_directory_API/auth/services.py`
3. `backrooms/services/Supply_directory_API/routes/{auth,profiles,suppliers}.py`
4. `scripts/src/sample-usage.ts`
5. `uis/backoffice/app/page.tsx`, `app/incidents/page.tsx`, `app/suppliers/page.tsx`, `app/account/profile/page.tsx`
6. `uis/talent-pipeline-tracker/lib/api/notes.ts`, `app/page.tsx`, `app/candidates/[id]/page.tsx`, `app/candidates/[id]/edit/page.tsx`

What changed:
1. LOW-1 (`analyzer-api.py`): upload read now happens inside `try/except` (client disconnect/IO → clean `400`) and enforces a 10 MB limit via `file.read(MAX_UPLOAD_BYTES + 1)` → `413` for oversized files.
2. LOW-2 (`auth/email.py`): already resolved in the HIGH pass (SDK send wrapped in `EmailDeliveryError`); no change needed.
3. LOW-3 (`auth/services.py`): the compensating rollback in `create_user` now catches `(OSError, ValueError)` instead of the broad `except Exception`, so only file-I/O/validation failures trigger cleanup.
4. LOW-4 (`routes/profiles.py`): `update_profile`'s "Profile disappeared while updating" `RuntimeError` is caught at the route and mapped to a logged `500` with a generic message.
5. LOW-5 (`routes/suppliers.py`): added `_get_after_write` helper that re-reads a row after `insert`/`update` and raises a logged `500` (instead of an unhandled `TypeError`) when the row is unexpectedly missing; used by create, rate-update, and status-update.
6. LOW-6 (`routes/auth.py`): login now catches `ValueError` from `verify_password` (corrupt/malformed stored hash), logs the data-integrity issue, and returns `401` instead of a `500`.
7. LOW-7: added "Try again" buttons that re-invoke the load function on load-error states in the backoffice profile and suppliers pages, and the tracker list, candidate detail (candidate + notes), and edit pages. Loaders were extracted into `useCallback` so the retry button and effect share the same function; files gained the `/* eslint-disable react-hooks/set-state-in-effect */` directive (matching the existing suppliers page convention).
8. LOW-8 (`lib/auth/storage.ts`): no action — the silent `localStorage` catches are documented and deliberate.
9. LOW-9 (`lib/api/notes.ts`): `normalizeNotes` now throws `"Received an unexpected notes response."` instead of returning `[]`, so a malformed payload surfaces the existing notes error state rather than a false "No internal notes yet."
10. LOW-10 (`app/incidents/page.tsx`): the "Download results ↓" link is only rendered after a local analysis completes (`{analysis ? <a …> : null}`), removing the fresh-load `404`/raw-JSON path.
11. LOW-11 (`scripts/src/sample-usage.ts` + `uis/backoffice/app/page.tsx`): `sampleUsageResults` is computed inside a `try/catch` (returns `null` on failure and logs to console), and the backoffice overview guards against `null` with a friendly error panel instead of crashing the whole dashboard.

Validation performed:
1. `uv run python -m py_compile` passed for `auth/services.py`, `routes/{auth,profiles,suppliers}.py`, and `APIs/analyzer-api.py`.
2. `uv run --with httpx2 python Supply_directory_API/tests/test_password_recovery.py` passed 19/19 (unchanged).
3. `npm run lint` and `npm run build` passed in both `uis/backoffice` and `uis/talent-pipeline-tracker`.
4. `git diff --check` passed (only benign LF→CRLF notices); recompiled tracked `__pycache__/*.pyc` files restored.

Remaining risks / notes:
1. LOW-1 adds a 10 MB upload cap (returning `413`); the incidents frontend does not yet special-case `413`, so it renders the generic analyzer error text. Acceptable for this pass.
2. The React Compiler lint rule (`react-hooks/set-state-in-effect`) required the same file-level disable directive already used by `suppliers/page.tsx`; the data-fetching pattern itself is unchanged from the original code.
3. The audit's "Observations outside the 8 categories" (shared `_last_metrics` across users, unauthenticated export, un-debounced search) remain open for a separate pass.

# Error handling MEDIUM-severity remediation (2026-09-21)

Scope changed:
1. `backrooms/services/Supply_directory_API/auth/security.py`
2. `backrooms/services/Supply_directory_API/routes/auth.py`
3. `scripts/CSV_analyzer/analyze.py`
4. `uis/backoffice/lib/auth/client.ts`, `uis/backoffice/lib/auth/session.ts`
5. `uis/talent-pipeline-tracker/lib/auth/client.ts`, `uis/talent-pipeline-tracker/lib/auth/session.ts`

What changed (MED-1 — unguarded JWT env parsing):
1. `auth/security.py` now parses and validates `JWT_EXPIRY_MINUTES` and `PASSWORD_RESET_EXPIRY_MINUTES` once at import via a `_read_int_env` helper that raises a clear `RuntimeError` (e.g. "JWT_EXPIRY_MINUTES must be an integer, got 'abc'"; "PASSWORD_RESET_EXPIRY_MINUTES must be at least 15, got 5") instead of a raw `ValueError`/`RuntimeError` mid-request.
2. `token_expiry_minutes()` and `password_reset_expiry_minutes()` now return the precomputed, validated constants, so no per-request parse/validation can 500 the login or reset flows.
3. `routes/auth.py` wraps the `create_password_reset` call in `try/except (RuntimeError, ValueError)` mapping to `503` with alerting, so a config problem after the user lookup no longer surfaces as a 500 the UI used to swallow.

What changed (MED-2 — raw network errors shown to users):
1. `authorizedFetch` in both `lib/auth/client.ts` files and a new `request` helper in both `lib/auth/session.ts` files wrap `fetch` in `try/catch` and rethrow a friendly "Network error — unable to reach the server. Please check your connection and try again." instead of the browser's raw `TypeError: Failed to fetch`/DNS message. Parsed API `detail` is still preserved for non-2xx responses. All four unauthenticated calls (login, register, forgot-password, reset-password) now go through `request`; authorized calls (me, profile, change-password) are covered by `authorizedFetch`.

What changed (MED-3 — CSV analyzer CLI traceback):
1. `scripts/CSV_analyzer/analyze.py` catches `EOFError` around `input()` (closed stdin/CI/automation) and skips the export prompt, and wraps `export_results` in `try/except OSError` writing a message to stderr and returning exit code 1 (the analysis itself already succeeded).

What changed (MED-4 — PII/token leak into logs):
1. Already resolved in the HIGH pass: the reset send failure is logged with a sanitized `logger.error("... failed for an active account")` and no exception object/recipient/URL/token. Verified no `logger.exception` remains in the Supply Directory service.

Validation performed:
1. `uv run python -m py_compile` passed for `auth/security.py` and `routes/auth.py`.
2. `uv run --with httpx2 python Supply_directory_API/tests/test_password_recovery.py` passed 19/19.
3. Fail-fast checks confirmed clear `RuntimeError` messages for non-numeric `JWT_EXPIRY_MINUTES` and out-of-range `PASSWORD_RESET_EXPIRY_MINUTES`.
4. `python -m py_compile analyze.py` passed; `python analyze.py incidents-nexova.csv < /dev/null` exited `0` with no traceback (EOFError handled).
5. `npm run lint` and `npm run build` passed in both `uis/backoffice` and `uis/talent-pipeline-tracker`.
6. `git diff --check` passed (only benign LF→CRLF notices); recompiled tracked `__pycache__/*.pyc` files restored.

Remaining risks / notes:
1. MED-1 validates config at import; a deliberately malformed `JWT_EXPIRY_MINUTES`/`PASSWORD_RESET_EXPIRY_MINUTES` now fails the whole service at startup with a clear message rather than returning 500s per request — the intended fail-fast behavior.
2. The friendly network-error wrapper was applied to the auth layer only. The tracker candidate client (`lib/api/client.ts`) still lets a raw `TypeError` propagate from `fetch`; wrapping it is a candidate follow-up (noted in the audit's broader network-error theme but outside the listed MEDIUM items).
3. Remaining LOW-severity findings (upload size limit, retry CTAs, notes parse fallback, export download handling, sample-usage error boundary) are intentionally deferred.

# Error handling HIGH-severity remediation (2026-09-20)

Scope changed:
1. `backrooms/services/Supply_directory_API/auth/email.py`
2. `backrooms/services/Supply_directory_API/routes/auth.py`
3. `backrooms/services/Supply_directory_API/tests/test_password_recovery.py`
4. `backrooms/services/APIs/analyzer-api.py`
5. `uis/backoffice/app/forgot-password/page.tsx`
6. `uis/talent-pipeline-tracker/app/forgot-password/page.tsx`
7. `uis/talent-pipeline-tracker/lib/api/client.ts`

What changed (HIGH-1 — silent password-reset failures):
1. `auth/email.py` now exposes typed `EmailConfigurationError` and `EmailDeliveryError`, plus `is_email_delivery_configured()`.
2. `send_password_reset_email` raises `EmailConfigurationError` for a missing `RESEND_API_KEY` and wraps provider failures in `EmailDeliveryError` instead of leaking the raw SDK exception.
3. `routes/auth.py` checks `is_email_delivery_configured()` **before** the user lookup, so a misconfigured service returns `503` for every address (no enumeration) instead of silently returning `200`.
4. The broad `except Exception` around the send is gone. `EmailConfigurationError` maps to `503`; `EmailDeliveryError` is logged with a sanitized message (no recipient, reset URL, or token) while still returning the generic `200` so delivery failures cannot be used to enumerate registered accounts. This also removes the PII/token traceback leak flagged as MED-4.
5. Both forgot-password pages now set the confirmation only on a resolved (2xx) request and show a neutral "Something went wrong — please try again." on network or server failure, so users are no longer told an email was sent when the request failed.

What changed (HIGH-2 — raw API bodies rendered in the tracker UI):
1. `uis/talent-pipeline-tracker/lib/api/client.ts` parses FastAPI `detail` (string or validation array) into a friendly message, falls back to `Request failed with status <code>` for non-JSON/HTML bodies, and logs the raw body to the console instead of throwing it into React error state.

What changed (HIGH-3 — raw exception/temp-path in analyzer detail):
1. `backrooms/services/APIs/analyzer-api.py` logs the real exception with `logger.exception` server-side and returns the fixed client-safe `400` detail "The uploaded file is not a valid CSV.", removing the interpolated `OSError` temp-file path.

Validation performed:
1. `uv run python -m py_compile` passed for `routes/auth.py`, `auth/email.py`, and `APIs/analyzer-api.py`.
2. `uv run --with httpx2 python Supply_directory_API/tests/test_password_recovery.py` passed 19/19 checks (unknown-address `200`, known-address send, expiry, single-use, malformed/expired/type-confusion `400`, change-password, bcrypt storage). The test now sets a dummy `RESEND_API_KEY` to satisfy the new configuration pre-check while still stubbing the sender.
3. `npm run lint` and `npm run build` passed in `uis/talent-pipeline-tracker`; `npm run lint` and `npm run build` passed in `uis/backoffice`.
4. `git diff --check` passed (only benign LF→CRLF notices); the inadvertently recompiled tracked `__pycache__/auth.cpython-313.pyc` was restored.

Remaining risks / notes:
1. Per the audit's stated tradeoff, a genuine provider send failure still returns `200` to avoid account enumeration; the alerting hook is the sanitized `logger.error`, so a delivery outage is visible in logs rather than to the user.
2. MED-1 (unguarded env parsing at startup / per request) and MED-2 (raw network errors in `lib/auth/session.ts`) remain open; they were intentionally out of scope for the HIGH-only pass.
3. `parseApiError` is now duplicated between `lib/api/client.ts` and `lib/auth/session.ts`; extracting a shared helper is a candidate for the MEDIUM hardening sprint.

# Error handling audit (2026-09-19)

Scope audited:
1. `backrooms` — analyzer FastAPI + Supply Directory API (routes, auth, services, email, security, database, tests)
2. `scripts` — CSV analyzer CLI + TypeScript business logic module
3. `UIs` — backoffice, talent-pipeline-tracker, website, landing page (82 source files total; build artifacts and virtualenvs excluded)

What changed: no code changes — audit-only pass. Full findings saved to root `error-handling-audit-report.md`.

Summary of findings (by severity):
1. No CRITICAL findings.
2. HIGH (3): password-reset email failures swallowed end-to-end so users are told an email was sent when none was (`routes/auth.py` + both forgot-password pages); tracker API client throws raw response bodies into UI error states (`lib/api/client.ts`); analyzer API returns raw exception text with temp-file paths in 400 details (`analyzer-api.py`).
3. MEDIUM (4): unguarded env parsing in `auth/security.py` (startup crash / 500 / swallowed reset misconfiguration); raw browser network errors shown via `lib/auth/session.ts`; CLI analyzer unguarded export/`input()` (EOFError under automation); potential PII + reset token in logs via `logger.exception` in `routes/auth.py`.
4. LOW (11): unguarded upload read, email SDK call, broad rollback except, profile invariant error, supplier route DB errors, malformed-hash login 500, missing retry CTAs on load errors, documented localStorage swallows, notes normalize-to-`[]` fallback, export download link, import-time `runSampleUsage()` with no error boundary.
5. Exit codes (category 8): no violations — `analyze.py` and the password-recovery test script return distinct codes.

Recommended next steps:
1. Fix HIGH-1 (reset email) first: distinguish config errors (503 + alerting) from send failures; the UI should show the generic confirmation only after a real 200.
2. Fix HIGH-2/HIGH-3: stop rendering raw server/exception text in the UI; parse `detail` like the backoffice `parseApiError`; return fixed messages server-side.
3. Then the MEDIUM items plus retry CTAs (LOW-7) in a follow-up hardening sprint.

# Sprint 3 Password recovery, change, and release readiness (2026-09-16)

Scope changed:
1. `backrooms/services/Supply_directory_API/models.py`
2. `backrooms/services/Supply_directory_API/database.py`
3. `backrooms/services/Supply_directory_API/auth/security.py`
4. `backrooms/services/Supply_directory_API/auth/services.py`
5. `backrooms/services/Supply_directory_API/auth/email.py` (new)
6. `backrooms/services/Supply_directory_API/routes/auth.py`
7. `backrooms/services/Supply_directory_API/tests/test_password_recovery.py` (new) + `tests/__init__.py`
8. `backrooms/services/Supply_directory_API/.env.example`, `backrooms/services/pyproject.toml`, `backrooms/services/uv.lock`
9. `uis/backoffice/lib/auth/{types,session}.ts`, `app/{login,forgot-password,reset-password,account/change-password}/page.tsx`, `components/auth/{AuthGuard,AccountBar}.tsx`
10. `uis/talent-pipeline-tracker/lib/auth/{types,session}.ts`, `app/{login,forgot-password,reset-password,account/change-password}/page.tsx`, `components/auth/{AuthGuard,AccountBar}.tsx`
11. Root `.gitignore`

What changed:
1. Added `POST /auth/forgot-password`. It always returns `200` with a generic message whether or not the address is registered, so it cannot be used to enumerate accounts. A reset email is only generated for existing active users.
2. Added `POST /auth/reset-password`. It decodes a dedicated reset JWT (`type="password_reset"`, `sub`, `exp`, `jti`), verifies the persisted TokenState is unused and unexpired, marks it used, and only then writes the new bcrypt hash. Invalid, expired, malformed, wrong-type, and already-used tokens all return `400`.
3. Added `POST /auth/change-password`. It requires a bearer session and returns `400` when the current password is wrong, otherwise stores a new bcrypt hash.
4. Introduced a separate TinyDB file for reset-token state (`password_resets_db.json`) so the tracked `suppliers_db.json` seed data is never dirtied at runtime. The file is gitignored.
5. Reset-token expiry is configurable through `PASSWORD_RESET_EXPIRY_MINUTES` and validated to the required 15-60 minute window.
6. Integrated Resend through `auth/email.py` using env-only credentials (`RESEND_API_KEY`, `RESEND_FROM_EMAIL`). The message includes a styled, mobile-readable HTML body plus a plain-text fallback and the reset link built from `PASSWORD_RESET_URL`.
7. Added the three frontend routes to both internal apps with per-app wording: `/forgot-password` (disables the form after submission and shows the generic confirmation), `/reset-password` (reads `?token=`, validates matching passwords, redirects to `/login?reset=success`, and shows an error plus a link back to forgot-password on failure), and `/account/change-password` (guarded, validates match, shows success or error).
8. Added a visible "Forgot your password?" link to both login pages plus a reset-success banner driven by the `reset=success` query parameter.
9. Made `/forgot-password` and `/reset-password` public in both `AuthGuard` components and hidden from `AccountBar`.
10. Documented every Sprint 3 environment variable in the service `.env.example`. `.env`, `password_resets_db.json`, `__pycache__/`, and `*.pyc` are excluded from version control.

Validation performed:
1. `uv run python -m py_compile` passed for all changed backend modules.
2. `uv run python Supply_directory_API/tests/test_password_recovery.py` passed all 19 checks against an isolated temporary TinyDB with the Resend call stubbed: registration, unknown-address `200` with no send, known-address `200` with one send, 15-60 minute expiry, access-token-as-reset-token rejection, successful reset, old-password rejection, new-password login, single-use replay `400`, expired-token `400`, malformed-token `400`, unauthenticated `401`, wrong-current-password `400`, successful change, and bcrypt (non-plaintext) storage.
3. Live Resend send succeeded from the service context (`onboarding@resend.dev` -> `delivered@resend.dev`), confirming the API key, sender, and HTML/text payload are accepted.
4. `npm run lint` and `npm run build` passed in `uis/backoffice` and `uis/talent-pipeline-tracker`. Both builds emit `/forgot-password`, `/reset-password`, and `/account/change-password`.
5. `git diff --check` passed (only benign CRLF notices).
6. Confirmed `suppliers_db.json` is unmodified, `password_resets_db.json` is not created in the repo by the test run, and `.env` remains untracked.

Remaining risks / notes:
1. The Resend sandbox sender (`onboarding@resend.dev`) only delivers to the account owner's inbox. Sending to arbitrary recipients in a real evaluation requires a domain-verified sender in `RESEND_FROM_EMAIL`.
2. The service `.env` originally contained a typo (`onboarding@resend.com`); it was corrected to `onboarding@resend.dev` in this session with developer approval to edit the protected `.env`.
3. TinyDB has no transactions. Reset consumption marks the token used before the password write; a crash between the two leaves a spent token with the old password, which is an acceptable failure mode because the user can request a fresh link.
4. Pre-existing tracked `__pycache__/*.pyc` files remain in version control. They were restored to avoid diff noise, and new `__pycache__/` and `*.pyc` entries were added to `.gitignore`; fully untracking the existing files is a separate cleanup that needs approval.
5. Browser end-to-end verification (forgot -> email link -> reset -> new login -> change password) still needs a running API with the corrected `.env` and a real recipient address.

# Sprint 2 Internal frontend authentication (2026-09-15)

Scope changed:
1. `uis/backoffice/lib/auth/` (new): `types.ts`, `storage.ts`, `client.ts`, `session.ts`.
2. `uis/backoffice/components/auth/` (new): `AuthGuard.tsx`, `AccountBar.tsx`.
3. `uis/backoffice/app/login/page.tsx`, `app/register/page.tsx`, `app/account/profile/page.tsx` (new).
4. `uis/backoffice/app/layout.tsx`, `app/suppliers/page.tsx`, `.gitignore`, `.env.example`.
5. `uis/talent-pipeline-tracker/lib/auth/` (new): `types.ts`, `storage.ts`, `client.ts`, `session.ts`.
6. `uis/talent-pipeline-tracker/components/auth/` (new): `AuthGuard.tsx`, `AccountBar.tsx`.
7. `uis/talent-pipeline-tracker/app/login/page.tsx`, `app/register/page.tsx`, `app/account/profile/page.tsx` (new).
8. `uis/talent-pipeline-tracker/app/layout.tsx`, `lib/api/client.ts`, `.gitignore`, `.env.example`.

What changed:
1. Added app-local auth utilities to both internal apps: token storage in `localStorage` (`nexova.auth.token`), client-side JWT `exp` validity check, an authorized fetch wrapper that sets `Authorization: Bearer <token>`, and automatic session clearing plus `/login` redirect on any `401`.
2. Added a client `AuthGuard` mounted in each root layout. It redirects unauthenticated users to `/login` (preserving a `next` return path) and treats `/login` and `/register` as public. Next.js middleware was deliberately not used, per AUTH-02.
3. Added `AccountBar` (profile link + logout) rendered globally on authenticated views in both apps.
4. Added `/login`, `/register`, and `/account/profile` routes to both apps. Registration submits `email`, `password`, and optional `name`/`phone`/`address` to `POST /users`, then immediately `POST /auth/login`, stores the token, and redirects to the authenticated home view. Registration shows field-level validation errors.
5. Profile pages read `GET /auth/me` and display account email plus profile name/phone/address, saving changes through `PUT /profiles/me`.
6. Backoffice supplier requests (`GET`/`POST`/`PATCH`) now go through the authorized wrapper. Tracker's shared API client attaches the token to `PROJECT_API_URL` requests and clears the session on `401`.
7. Backoffice auth routes use the existing `NEXT_PUBLIC_SUPPLIERS_API_URL`. Tracker auth/profile routes use a new `NEXT_PUBLIC_AUTH_API_URL` (default `http://localhost:8000`), while `PROJECT_API_URL` continues to serve candidate records.
8. Documented env variables in both `.env.example` files and added a `!.env.example` negation to both `.gitignore` files so the examples are committable.
9. `uis/website` was left fully public and untouched.

Validation performed:
1. `npm run lint` inside `uis/backoffice` passed with zero errors and zero warnings.
2. `npm run lint` inside `uis/talent-pipeline-tracker` passed with zero errors and zero warnings.
3. `npm run build` inside `uis/backoffice` passed; generated `/`, `/account/profile`, `/incidents`, `/login`, `/register`, `/suppliers`.
4. `npm run build` inside `uis/talent-pipeline-tracker` passed; generated `/`, `/account/profile`, `/candidates/new`, `/login`, `/register`, plus the dynamic `/candidates/[id]` and `/candidates/[id]/edit` routes.
5. `git diff --check` passed (only a benign CRLF warning for `uis/talent-pipeline-tracker/lib/api/client.ts`).
6. In-process FastAPI `TestClient` smoke test ran against an isolated temporary TinyDB and passed all 20 checks: register `201` with `user` role and no password leakage, short-password `422`, login `200` with bearer token, authorised `GET /auth/me` with linked profile, `PUT /profiles/me` persisted, protected `GET /suppliers` `401` without token and `200` with token, malformed and expired tokens `401`, duplicate registration `409`, wrong password `401`, CORS preflight allowed for `http://localhost:3000`, and cleanup delete `200` followed by token `401`. The tracked `suppliers_db.json` was not modified.

Remaining risks / notes:
1. Tokens are stored in `localStorage` as required by AUTH-02, so they are readable by any script on the origin; XSS exposure is inherent to that contract.
2. `uis/talent-pipeline-tracker` now sends the Nexova JWT to its external `PROJECT_API_URL`. If that external API rejects the token with `401`, the shared client clears the session and redirects to `/login`. The external API must accept the JWT for protected record operations to work end-to-end.
3. `uis/backoffice` incident analyzer routes are session-guarded in the UI, but the analyzer FastAPI endpoints have no JWT support, so those requests remain unauthenticated.
4. Browser end-to-end checks (register, login, redirect, profile update, logout, expired token) still need a running supplier-directory API with `JWT_SECRET_KEY` configured and matching CORS origins.

## Supplier directory API CORS enablement (2026-08-30)

Scope changed:
1. `backrooms/services/Supply_directory_API/main.py`

What changed:
1. Added FastAPI `CORSMiddleware` to the Supplier Directory API entrypoint.
2. Added configurable `SUPPLIERS_ALLOWED_ORIGINS` environment variable with defaults for local backoffice origins (`http://localhost:3000,http://localhost:3001`).
3. Enabled browser preflight compatibility for supplier CRUD endpoints by allowing all methods and headers.

Validation performed:
1. `python -m py_compile main.py` from `backrooms/services/Supply_directory_API` passed.

Remaining risks / notes:
1. If the frontend runs on a different origin, it must be included in `SUPPLIERS_ALLOWED_ORIGINS` before launching the API.

# Sprint 1 API authentication (2026-09-12)

Scope changed:
1. `backrooms/services/Supply_directory_API/models.py`
2. `backrooms/services/Supply_directory_API/database.py`
3. `backrooms/services/Supply_directory_API/auth/`
4. `backrooms/services/Supply_directory_API/routes/auth.py`
5. `backrooms/services/Supply_directory_API/routes/users.py`
6. `backrooms/services/Supply_directory_API/routes/profiles.py`
7. `backrooms/services/Supply_directory_API/routes/suppliers.py`
8. `backrooms/services/Supply_directory_API/main.py`
9. `backrooms/services/Supply_directory_API/.env.example`
10. `backrooms/services/pyproject.toml`

What changed:
1. Added TinyDB-backed users and profiles with role validation for `admin`, `manager`, and `user`.
2. Added bcrypt password hashing, configurable JWT signing/expiry, bearer-token decoding, and reusable `get_current_user` dependency.
3. Added full user routes under `/users`, authentication routes under `/auth`, and profile routes under `/profiles`.
4. Added owner/admin authorization for individual user credentials, admin-only role changes, linked profile deletion, and profile ownership through `/profiles/me`.
5. Protected all six supplier routes. Authenticated users can read; only admins and managers can create, update, or delete supplier records.
6. Added non-secret JWT and CORS configuration documentation in `.env.example`.

Validation performed:
1. `uv run python -m py_compile` passed for all changed API, auth, and route modules.
2. `uv sync --project backrooms/services` completed and runtime imports for `passlib` and `jose` passed.
3. OpenAPI inspection confirmed `/users`, `/auth`, `/profiles/me`, and all supplier routes are mounted.
4. `PYTHONPATH=.. uv run python -m services.Supply_directory_API.routes.seed` passed with `Inserted records: 0`.
5. Bcrypt/JWT primitive smoke test passed, including token subject decoding.
6. HTTP smoke test passed for registration, login, profile update, unauthenticated `401`, malformed-token `401`, and cleanup.
7. Authorization/expiry smoke test passed for cross-user `403`, regular-user supplier write denial, authenticated supplier reads, and expired-token `401`.
8. `git diff --check` passed.

Remaining risks / notes:
1. Editor diagnostics may report `passlib` and `jose` as unresolved when Pylance is pointed at a different interpreter; the synchronized service interpreter imports both successfully.
2. HTTP tests required ephemeral `httpx2` because the installed Starlette TestClient expects that optional package; it was supplied with `uv run --with httpx2` without changing project metadata.
3. TinyDB user/profile creation uses compensating cleanup if profile insertion fails; TinyDB does not provide a multi-table transaction.

## Backoffice supplier directory route (2026-08-30)

Scope changed:
1. `uis/backoffice/app/suppliers/page.tsx`
2. `uis/backoffice/app/globals.css`
3. `uis/backoffice/app/page.tsx`
4. `uis/backoffice/app/incidents/page.tsx`

What changed:
1. Added new Next.js route page at `/suppliers` to manage Nexova supplier directory records using the Supply Directory API.
2. Implemented full supplier list UI with required fields from context: name, country, categories, monthly rate, and status.
3. Added client-side country and category filters that call `GET /suppliers` with query parameters and update list results without page reload.
4. Added new supplier registration form wired to `POST /suppliers`, with client-side required-field checks and API error message handling.
5. Added per-row rate update controls wired to `PATCH /suppliers/{id}/rate` and status toggle controls wired to `PATCH /suppliers/{id}/status`, with immediate row updates after API responses.
6. Added status badges to visually distinguish active vs suspended suppliers and renewal-date highlighting for contracts due within 60 days.
7. Updated backoffice navigation menus so Supplier Directory is reachable from the main overview sidebar and incidents page sidebar.

Validation performed:
1. `npm run lint` inside `uis/backoffice` passed.
2. `npm run build` inside `uis/backoffice` passed and generated `/suppliers` route.

Remaining risks / notes:
1. Route requires `NEXT_PUBLIC_SUPPLIERS_API_URL` (defaults to `http://localhost:8000`) and a running Supplier Directory API with CORS allowed for the backoffice origin.


## Supply directory seed migration to routes module (2026-08-30)

Scope changed:
1. `backrooms/services/Supply_directory_API/routes/seed.py`
2. `backrooms/services/Supply_directory_API/seed.py`

What changed:
1. Moved TinyDB seeding execution logic (`supplier_exists` and `main`) into `routes/seed.py` so seed data and seeding behavior live in one module.
2. Kept root `seed.py` as a compatibility wrapper that imports and delegates to `routes.seed.main`.

Follow-up cleanup:
1. Updated `pyproject.toml` script entry from `seed:main` to `routes.seed:main`.
2. Removed obsolete root `seed.py` wrapper from `backrooms/services/Supply_directory_API`.
3. Removed `seed.py` from Hatch wheel include list.

Validation performed:
1. `python -m py_compile backrooms/services/Supply_directory_API/routes/seed.py backrooms/services/Supply_directory_API/seed.py` passed.
2. `uv run seed` from `backrooms/services/Supply_directory_API` passed (`Inserted records: 0`).

Remaining risks / notes:
1. If future packaging changes remove top-level module resolution, imports may need to switch to package-relative style.

## Supply directory TinyDB routes (2026-08-28)

Scope changed:
1. `backrooms/services/Supply_directory_API/routes/suppliers.py`

What changed:
1. Added full FastAPI router for supplier directory management backed by local TinyDB file storage (`suppliers_db.json`).
2. Implemented required endpoints: create, list (with optional `country` and `category` filters), get by ID, update monthly rate, update status, and delete by ID.
3. Enforced API behavior aligned to context constraints:
   - invalid input types/values handled by FastAPI/Pydantic validation (`422`)
   - missing supplier IDs return `404`
   - rate updates automatically refresh `updated_at` timestamp
4. Route responses include the TinyDB-assigned document ID as `id`.

Validation performed:
1. `python -m py_compile backrooms/services/Supply_directory_API/routes/suppliers.py` passed.
2. Editor diagnostics for the route module reported no errors.

Remaining risks / notes:
1. Follow-up HTTP integration tests can be added once local test-client dependency chain is standardized.

## Supply directory app wiring and seeder (2026-08-28)

Scope changed:
1. `backrooms/services/Supply_directory_API/main.py`
2. `backrooms/services/Supply_directory_API/seed.py`
3. `backrooms/services/Supply_directory_API/routes/suppliers.py`
4. `backrooms/services/Supply_directory_API/pyproject.toml`

What changed:
1. Wired the FastAPI app entrypoint in `main.py` and mounted the supplier router.
2. Added root `seed.py` that validates all seed suppliers through Pydantic, inserts only missing records into TinyDB, and prints inserted-record totals.
3. Made route imports compatible with service-local execution (`from models import ...`).
4. Added local `pyproject.toml` with dependencies and console script mapping so `uv run seed` executes directly.

Validation performed:
1. `python -m py_compile` passed for `main.py`, `seed.py`, and `routes/suppliers.py`.
2. Seeder direct execution passed:
   - first run inserted 15 records
   - second run inserted 0 records (duplicate-safe)
3. `uv run seed` passed and executed the configured seed command (`Inserted records: 0` on current DB state).
4. Direct route-function smoke test passed for create/list/get/rate-update/status-update/delete.
5. Editor diagnostics reported no errors in changed Python files.

Remaining risks / notes:
1. FastAPI `TestClient`-based HTTP smoke testing in this environment is currently blocked by missing optional package `httpx2` from the local Starlette test dependency chain.

## Supply directory DB init centralization (2026-08-30)

Scope changed:
1. `backrooms/services/Supply_directory_API/database.py`
2. `backrooms/services/Supply_directory_API/routes/suppliers.py`
3. `backrooms/services/Supply_directory_API/routes/seed.py`

What changed:
1. Moved TinyDB initialization and suppliers table accessor into `database.py`.
2. Updated supplier routes and seeder to use the shared database helpers.
3. Removed duplicated DB path/table initialization from route and seed modules.

Validation performed:
1. `uv run python -m py_compile database.py routes/suppliers.py routes/seed.py main.py` passed.
2. `uv run seed` passed (`Inserted records: 0` with current seeded DB state).
3. Editor diagnostics reported no errors in changed files.

## Incident analyzer CORS fix (2026-08-23)

Updated `backrooms/services/APIs/analyzer-api.py` with explicit CORS support for the local backoffice origins on ports `3000` and `3001`. Additional origins can be supplied through `ANALYZER_ALLOWED_ORIGINS` as a comma-separated list.

Validation performed:
1. Python syntax compilation passed.
2. FastAPI CORS preflight for `http://localhost:3000` returned `200` with the expected `Access-Control-Allow-Origin` header.

Remaining risk: deployed frontend origins must be included in `ANALYZER_ALLOWED_ORIGINS`.

## Dedicated incident analyzer route (2026-08-23)

Added `uis/backoffice/app/incidents/page.tsx` as a separate Nexova backoffice page for incident CSV intake and analysis. The page supports file selection and drag/drop, calls the FastAPI analyzer through `NEXT_PUBLIC_ANALYZER_API_URL` (default `http://localhost:8000`), shows loading, validation error, completion, quality, category, status, and satisfaction states, and links to the aggregate `results.csv` export. Added route-specific responsive styling to `uis/backoffice/app/globals.css`.

Validation performed:
1. `npm run lint` inside `uis/backoffice` passed.
2. `npm run build` inside `uis/backoffice` passed and generated `/` plus `/incidents`.
3. Pylance diagnostics reported no errors for either route.

Remaining risk: the browser needs the FastAPI analyzer running and, when hosted on another origin, matching CORS configuration and `NEXT_PUBLIC_ANALYZER_API_URL`.

## Nexova incident analyzer API (2026-08-21)

Added `backrooms/services/APIs/api.py` with FastAPI endpoints for multipart CSV analysis and aggregate CSV export. The API reuses `scripts/CSV_analyzer/analyze.py`, returns JSON-safe metrics, keeps the latest successful result in memory, rejects empty or invalid UTF-8/CSV uploads with descriptive `400` responses, and returns `404` when no result is available to export.

Validation performed:
1. `python -m py_compile backrooms/services/APIs/api.py` passed.
2. Pylance diagnostics for the API file reported no errors.
3. In-process route smoke test passed for valid analysis, downloadable export, and empty-file rejection.
4. Added repository-root path bootstrap after FastAPI CLI reported `ModuleNotFoundError: No module named 'scripts'` when launched with `fastapi dev api.py`.

Remaining risk: the latest analysis is process-local and will be lost on restart or split across workers until persistent storage is introduced.

## Backend architecture proposal (2026-08-17)

Added `docs/Backend-Architecture-Proposal.md` as a Nexova-specific proposal for a modular layered FastAPI monolith. The document covers domain and module boundaries, candidate and notes routers, future vacancy and selection-process domains, persistence and API contract decisions, frontend/backend separation, environment configuration, CORS, security, observability, risks, and an evolution path. It cites official FastAPI and MDN CORS guidance and anchors decisions in the current tracker API consumer and selection models.

Validation performed:
1. `git diff --check -- docs/Backend-Architecture-Proposal.md` passed.
2. Required proposal sections were confirmed with a targeted text search.
3. No backend code, UI code, infrastructure, secrets, or lockfiles were modified.

## Scoped website Home-page rule (2026-08-11)

Added `.agents/rules/website-home-page.md` with an explicit scope limited to `uis/website/app/page.tsx`. The rule preserves Nexova Home-page context and boundaries the application route, other UIs, shared styles, and assets from implicit changes.

Validation performed:
1. `git diff --check` passed for the rule change.
2. Repository status confirmed the new rule is present; unrelated existing changes were left untouched.

## Reusable UI components skill (2026-08-10)

Added `.agents/skills/reusable-ui-components/SKILL.md` to guide detection and extraction of recurring UI layouts into focused, typed, accessible components. The skill covers component boundaries, composition, anti-patterns, consumer replacement, and responsive validation.

Validation performed:
1. Skill frontmatter inspected successfully.
2. `git diff --check` passed for the new skill file.

## Backoffice business logic integration (2026-08-05)

Scope changed:
1. `scripts/src/sample-usage.ts`
2. `uis/backoffice/app/page.tsx`
3. `uis/backoffice/app/globals.css`
4. `uis/backoffice/app/layout.tsx`
5. `uis/backoffice/next.config.ts`

What changed:
1. Replaced the default Next.js starter route at `uis/backoffice/` with a dedicated Nexova talent operations dashboard.
2. Imported the existing sample data and calculated results directly from `scripts/src/sample-usage.ts`; no business logic was copied into the UI.
3. Rendered visible business-logic output for vacancy details, candidate ranking, validation status, average salary, vacancy fill rate, seniority distribution, top skills, status counts, and normalized email search.
4. Removed the import-time `console.log` from `scripts/src/sample-usage.ts` so it can be safely consumed by the Next.js application.
5. Configured Turbopack to use the monorepo root and allow the backoffice to bundle the original shared `scripts` directory.
6. Made the backoffice navigation persist during scrolling with a viewport-sticky desktop sidebar and sticky mobile top navigation.

Validation performed:
1. `npm run lint` inside `uis/backoffice` (passed).
2. `npm run build` inside `uis/backoffice` (passed; static `/` route generated).
3. Manual runtime verification at `http://localhost:3000/` (passed; dashboard rendered shared script results).
4. Browser scroll verification (passed; sidebar retained `position: sticky` at the viewport edge while viewing the reports section).

Remaining risks / notes:
1. The dashboard currently uses the repository sample data and has no API, authentication, or CRUD integration.

## Website migration update (2026-08-03)

Scope changed:
1. `uis/website/app/page.tsx`
2. `uis/website/app/globals.css`
3. `uis/website/app/layout.tsx`
4. `uis/website/app/application/page.tsx`
5. `uis/website/public/assets/*` (copied from `uis/landing_page/assets/*`)

What changed:
1. Replaced default Next starter home with a Nexova landing page recreation that mirrors the static `uis/landing_page/index.html` structure:
   - sticky header and anchor navigation
   - hero section with CTA
   - services cards (3 columns)
   - why-Nexova section
   - contact section and branded footer
2. Ported interaction and animation behavior to Next styles:
   - hero background pan
   - CTA pulse and hover transitions
   - service-card hover lift/zoom
   - reveal-on-scroll with IntersectionObserver
   - reduced-motion accessibility fallback
3. Added Organization JSON-LD markup on the Next home page.
4. Updated site metadata in the Next layout to reflect Nexova SEO context.
5. Fully migrated `uis/landing_page/application.html` + `validation.js` behavior to Next route `uis/website/app/application/page.tsx`:
   - complete form fields
   - all required validation rules and exact error messages
   - live validation events (input/blur/change)
   - comments remaining counter with over-limit warning
   - policy checkbox enforcement
   - success modal with close/backdrop/escape behavior
   - reset handling and scroll-to-top on successful simulated submit

Validation performed:
1. `npm run lint` inside `uis/website` (passed).
2. `npm run build` inside `uis/website` (passed, static routes `/` and `/application` generated).

Remaining risks / notes:
1. Form submission is currently simulated client-side (no API integration), matching the original static milestone behavior.

## Audit summary (2026-08-03)

Audited folders:
1. `uis/landing_page`
2. `scripts`
3. `uis/talent-pipeline-tracker`

## Current status by area

### `uis/landing_page`

Status: Functional for milestone-style static delivery.

Completed:
1. Company-aligned landing structure with required sections and CTA.
2. Separate application page with required candidate intake fields.
3. Client-side validation for key constraints and expected messages.
4. Company-service redirection message for non-candidate inquiries.
5. Organization schema markup included.

Gaps and risks:
1. No automated test coverage for validation logic.
2. Tailwind CDN approach is simple but not optimized for production bundling.
3. Language mode is currently single-language (English), while bilingual support is recommended.

### `scripts`

Status: Core TypeScript logic implemented and organized.

Completed:
1. Domain models for candidate, vacancy, and process entities.
2. Filtering, sorting, and searching utilities.
3. Candidate scoring, ranking, grouping, and reporting functions.
4. Validation utilities for candidate and vacancy constraints.
5. Sample usage file that exercises main utilities.

Gaps and risks:
1. No formal automated tests were found.
2. README is generic and does not yet document concrete script execution workflows.
3. No dedicated scripts package configuration was identified in this folder.

### `uis/talent-pipeline-tracker`

Status: Major milestone requirements are implemented.

Completed:
1. Candidate list route with async fetch, loading/error states, filters, search, and pagination behavior.
2. Candidate detail route with full field display plus status/stage updates.
3. Notes workflow: list, add, and delete.
4. Candidate create route and candidate edit route.
5. API abstraction layer and TypeScript types for payloads and records.

Gaps and risks:
1. No automated test suite found for pages, components, or API integration.
2. Workspace currently includes `.next/` and `node_modules/` inside this app path; this can hide real diffs and slow audits.
3. Environment setup depends on `PROJECT_API_URL`; missing variable causes runtime failure by design.

## Nexova CSV analyzer implementation (2026-08-19)

Added `scripts/CSV_analyzer/analyze.py` to process the Nexova support incident CSV export. The script validates the documented record rules, reports valid/invalid totals and breakdowns, calculates category/status/satisfaction metrics from valid records, prompts for optional aggregate export to `results.csv`, and never includes customer email values in output.

Validation performed:
1. `python -m py_compile scripts/CSV_analyzer/analyze.py` passed.
2. Exact synthetic distribution check passed for 100 total rows, 96 valid rows, 4 invalid rows, all category/status counts, score histogram, and 3.84 average satisfaction.
3. Generator-input check passed after making the analyzer materialize its input once.
4. The provided `scripts/CSV_analyzer/incidents-nexova.csv` produced the exact documented totals and metric values.
5. The real CSV export branch passed and produced aggregate-only output without email fields or addresses.

Remaining risk: no known functional risk remains for the documented CSV input. The generated `results.csv` was created in a temporary directory for validation and removed afterward.

## Recommended next steps

1. Replace root `CONTEXT.md` placeholder with the canonical company context to reduce ambiguity across folders.
2. Add minimal automated coverage:
   - unit tests for `scripts/src/utils/*`
   - integration/UI tests for tracker critical flows
   - validation tests for landing form rules.
3. Add lightweight runbooks to each audited folder describing install/run/test commands and expected env vars.
4. Ensure build artifacts and dependency directories are excluded from version-control workflows and audit scopes.
5. Create a short acceptance checklist that maps each milestone requirement to concrete file evidence for faster final review.

## Governance setup completed (2026-08-03)

1. Added root agent contract at `AGENTS.md` with required memory-bank read order, mandatory pre-commit workflow, and protected paths requiring explicit confirmation.
2. Added always-active development rule at `.agents/rules/context-and-change-control.md`.
3. Added reusable audit skill at `.agents/skills/nexova-milestone-audit/SKILL.md` with documented inputs and verifiable acceptance criteria.
