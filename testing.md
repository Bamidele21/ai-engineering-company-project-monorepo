# TESTING.md — Nexova Authentication API (AUTH-088)

Unit test coverage for the authentication API built in the previous milestone.
The goal is confidence in the business logic — token generation and expiry,
password handling, and account state decisions — not HTTP serialisation.

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

# run with coverage (scoped to the authentication modules)
uv run pytest --cov
```

The tests run against an isolated temporary TinyDB (see `conftest.py`), so the
tracked `suppliers_db.json` and the local `password_resets_db.json` are never
modified, and the Resend email sender is stubbed so no real email is sent.

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

## Coverage results

Run with `uv run pytest --cov` (scoped to `auth/` and `routes/auth.py`):

```
Name                                    Stmts   Miss  Cover
------------------------------------------------------------
auth/__init__.py                            0      0   100%
auth/dependencies.py                       17      1    94%
auth/email.py                              30     17    43%
auth/security.py                           68      5    93%
auth/services.py                          113      6    95%
routes/auth.py                             84     12    86%
------------------------------------------------------------
TOTAL                                     312     41    87%
```

The lower `email.py` figure reflects the intentional stubbing of the Resend
sender in endpoint tests; the deterministic, testable pieces (`is_email_delivery_configured`,
`build_password_reset_url`) are covered, while the provider call itself is a
third-party boundary that is not meaningful to exercise in unit tests.

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
