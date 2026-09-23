# TESTING.md — Nexova Supplier Directory API

Unit test coverage for the Nexova platform: the authentication API (AUTH-088),
the backoffice endpoint groups (API-042), and the frontend utility functions
(FE-019). The goal is confidence in the business logic — token generation and
expiry, password handling, account state, supplier/user management, and the
frontend helpers that parse and format that data — not HTTP serialisation.

## How to run the tests

The suite targets the FastAPI backend at `backrooms/services`. Dependencies
(`pytest`, `pytest-cov`, `httpx`) are declared in the `dev` group.

```bash
# from the repository root
cd backrooms/services

# install the dev dependencies (once)
uv sync

# run the whole suite
uv run pytest

# run with coverage (scoped to the authentication + backoffice modules)
uv run pytest --cov
```

The tests run against an isolated temporary TinyDB (see `conftest.py`), so the
tracked `suppliers_db.json` and the local `password_resets_db.json` are never
modified, and the Resend email sender is stubbed so no real email is sent.

### Frontend (Jest)

The frontend suite is separate and targets the `uis/talent-pipeline-tracker`
utilities. Jest, ts-jest, and `@types/jest` are declared in the root
`package.json`; the config lives in the root `jest.config.js`.

```bash
# from the repository root
npm test
# equivalent: npx jest --coverage
```

The tracker's `tsconfig.json` excludes `__tests__` so `next build` does not
type-check the Jest files.

## What each suite covers

| Module | Endpoint / unit under test |
| --- | --- |
| `test_security.py` | `hash_password`/`verify_password`, access-token create/decode/expiry, reset-token create/decode, expiry helpers |
| `test_register.py` | `POST /users` (registration) |
| `test_login.py` | `POST /auth/login` |
| `test_me.py` | `GET /auth/me` |
| `test_forgot_password.py` | `POST /auth/forgot-password` |
| `test_reset_password.py` | `POST /auth/reset-password` |
| `test_change_password.py` | `POST /auth/change-password` |
| `test_services.py` | service-layer functions: `create_user`, `consume_password_reset`, `set_password`, `change_password`, `update_user`, `update_profile`, `delete_user`, reset-token lookups |
| `test_suppliers.py` | `/suppliers` CRUD: create, list (country/category filters), get, rate update, status update, delete |
| `test_users.py` | user management: list, get, update (email/role), delete, with ownership/admin rules |

## Test plan — cases and rationale

Every endpoint is covered with at least one happy path, one edge case, and one
failure mode.

### `POST /users` (register)

- Happy: valid input returns `201`, defaults `role` to `user`, lowercases email,
  creates a linked profile, stores a bcrypt hash (never plaintext, never leaked).
- Edge: duplicate email (including case-insensitive) returns `409`; short
  password returns `422`.
- Failure: empty/missing password and invalid email return `422`.

### `POST /auth/login`

- Happy: valid credentials return a bearer token with a positive `expires_in`.
- Edge: inactive account returns `401`; empty password returns `401`.
- Failure: wrong password and unknown email both return `401` (no account
  enumeration); invalid email returns `422`.

### `GET /auth/me`

- Happy: valid token returns the user's email plus the linked profile, without
  the password hash.
- Edge: user with a missing profile returns `404`.
- Failure: missing, malformed, and expired tokens all return `401`.

### `POST /auth/forgot-password`

- Happy: registered address returns `200` and queues exactly one reset email
  whose token is decodable and expires within 15–60 minutes.
- Edge: unknown address returns `200` with no email (enumeration resistance);
  inactive user returns `200` with no email.
- Failure: unconfigured email service returns `503`; invalid email returns `422`.

### `POST /auth/reset-password`

- Happy: valid token resets the password (old one stops working, new one works).
- Edge: token is single-use (replay returns `400`); expired token returns `400`.
- Failure: malformed token and an access-token-used-as-reset-token return `400`;
  too-short new password returns `422`.

### `POST /auth/change-password`

- Happy: correct current password updates the password.
- Failure: wrong current password returns `400`; unauthenticated returns `401`.
- Edge: too-short new password returns `422`.

### Token & hashing primitives (`test_security.py`)

Direct coverage of the logic that regressed in the incident behind AUTH-088:
token creation/decode round-trips, expiry enforcement, malformed/missing-claim
rejection, and salted bcrypt verification.

## Backoffice endpoint groups (API-042)

### `test_suppliers.py` — `/suppliers`

- Happy: admin/manager creates a supplier (`201`); rate update refreshes
  `monthly_rate` and `updated_at`; status toggles to `suspended`.
- Edge: currency/country mismatch (`Spain` + `USD`) and empty categories return
  `422`; list filters by `country` and `category`.
- Failure: `user` role cannot create/update/delete (`403`); unauthenticated
  returns `401`; unknown supplier id returns `404`.

### `test_users.py` — user management

- Happy: owner reads/updates/deletes their own record; admin reads any record
  and changes roles.
- Edge: duplicate email on update returns `409`.
- Failure: non-owner, non-admin access returns `403` (the ownership check also
  hides whether a user id exists); non-admin role change returns `403`;
  unauthenticated returns `401`.

## Frontend utility functions (FE-019)

Located in `uis/talent-pipeline-tracker/__tests__/` and run with Jest.

### `labels.test.ts` — `toStatusLabel` / `toStageLabel`

- Happy: a known status/stage maps to its human label (`in_progress` →
  `In progress`, `offer_presented` → `Offer presented`).
- Failure: `undefined` returns `-`; an unknown value is passed through unchanged.

### `storage.test.ts` — `hasValidSession` + token storage

- Happy: a stored, unexpired JWT makes `hasValidSession()` return `true`, and
  `setToken`/`getToken` round-trip through `localStorage`.
- Failure: an expired token, a malformed token, and a missing token all return
  `false`; `getToken` returns `null` when `window` is unavailable.

### `session.test.ts` — `parseApiError`

- Happy: a string `detail` is returned as the message.
- Failure: an array `detail` is joined into one sentence; `null`, an empty
  object, and non-object payloads all fall back to the provided message.

Each function has at least one happy-path and one failure-mode test, per the
ticket. Coverage for the tested helpers is `lib/labels.ts` 100% and
`lib/auth/storage.ts` 88%; `lib/auth/session.ts` appears lower overall only
because the other exported functions in that module (login, register, etc.) are
async fetch flows outside FE-019's scope.

## Coverage results

Run with `uv run pytest --cov` (scoped to `auth/`, `routes/auth.py`,
`routes/suppliers.py`, and `routes/users.py`):

```
Name                                    Stmts   Miss  Cover
------------------------------------------------------------
auth/__init__.py                            0      0   100%
auth/dependencies.py                       17      1    94%
auth/email.py                              30     17    43%
auth/security.py                           68      5    93%
auth/services.py                          113      6    95%
routes/auth.py                             84     12    86%
routes/suppliers.py                        90      2    98%
routes/users.py                            55      1    98%
------------------------------------------------------------
TOTAL                                     457     44    90%
```

Authentication modules remain at or above 70%, and both backoffice endpoint
groups exceed the 60% target set by API-042. The lower `email.py` figure reflects
the intentional stubbing of the Resend sender in endpoint tests; the
deterministic helpers (`is_email_delivery_configured`, `build_password_reset_url`)
are covered, while the provider call is a third-party boundary.

## AI-assisted workflow notes

- The single-use, expiry, and type-confusion reset-token cases were identified
  with AI assistance while mapping the reset-token lifecycle to test scenarios;
  they surfaced directly from `auth/services.py::consume_password_reset` rather
  than from the happy path.
- While writing `test_services.py`, the suite caught a real discrepancy between
  the two token helpers: `security.create_password_reset_token` returns a
  `(token, jti, expires_in)` triple, whereas `services.create_password_reset`
  returns a `(token, expires_in)` pair. The tests were written to decode the JWT
  for the `jti` explicitly, documenting the boundary between the two layers.
- While writing `test_users.py`, the suite surfaced that `_require_owner_or_admin`
  runs before the record lookup, so a non-admin user requesting a non-existent
  id receives `403` rather than `404`. The unknown-id cases were therefore
  asserted through the admin path, documenting a deliberate authorization
  decision that hides record existence from unprivileged callers.
