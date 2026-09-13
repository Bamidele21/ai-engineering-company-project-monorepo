# Nexova Authentication Delivery Plan

## Scope

Implement AUTH-01, AUTH-02, and AUTH-03 across the existing Nexova supplier API and internal Next.js applications. Keep `uis/website` fully public.

## Sprint 1: Secure API Foundation

### Goals

- Establish TinyDB-backed users and profiles.
- Implement signed JWT authentication.
- Protect existing sensitive API routes.

### Work

- Extend `backrooms/services/Supply_directory_API` with:
  - `User` and `Profile` schemas, including role validation (`admin`, `manager`, `user`).
  - TinyDB tables and services for user/profile CRUD.
  - Password hashing through `libpass[bcrypt]`; never persist plaintext passwords.
  - `/users` registration and protected management endpoints.
  - `/profiles/me` read/update endpoints.
  - `/auth/login` and `/auth/me`.
  - Reusable OAuth2 `get_current_user` dependency using `python-jose`.
- Configure JWT secret and expiry from environment variables.
- Apply authentication to all supplier-directory endpoints. This provides the required five existing protected routes:
  - `POST /suppliers`
  - `GET /suppliers`
  - `GET /suppliers/{id}`
  - `PATCH /suppliers/{id}/rate`
  - `PATCH /suppliers/{id}/status`
  - `DELETE /suppliers/{id}`
- Enforce `403` for ownership violations and admin-only role updates.
- Document required environment variables in `.env.example` or service documentation.

### Acceptance Criteria

- Registration creates a TinyDB user and linked profile.
- Login issues an expiring JWT carrying the TinyDB user ID.
- Missing, malformed, and expired tokens return `401`.
- Supplier routes reject unauthenticated access.
- Credentials and profiles remain isolated from PostgreSQL or external services.

### Validation

- API tests for registration, login, JWT decoding, profile ownership, role checks, and protected supplier endpoints.
- Manual `/docs` flow: register, login, authorise, access a protected route.

## Sprint 2: Internal Frontend Authentication

### Goals

- Restore authenticated access for internal Nexova applications.
- Provide complete login, registration, profile, and logout flows.

### Work

- Add shared, app-local authentication utilities to `uis/backoffice` and `uis/talent-pipeline-tracker`:
  - Token storage in `localStorage`.
  - Authorised fetch wrapper that sets `Authorization: Bearer <token>`.
  - Client-side session guard that redirects unauthenticated users to `/login`.
  - `401` handling that clears the token and redirects to login.
  - Logout control and redirect.
- Add routes to each internal application:
  - `/login`
  - `/register`
  - `/account/profile`
- Registration submits optional Nexova contact data, logs the user in immediately, stores the token, then redirects to the authenticated home view.
- Update Backoffice supplier requests to send the bearer token.
- Update talent-pipeline API client to attach tokens, subject to its external `PROJECT_API_URL` accepting the Nexova JWT.
- Exclude `uis/website` entirely from guards, auth routes, and token handling.

### Acceptance Criteria

- Login and registration store the token and reach authenticated views.
- Protected internal routes redirect to `/login` without a session.
- Profile displays email plus name, phone, and address, and saves updates through `/profiles/me`.
- Logout and API `401` responses clear the session.
- The public Nexova website remains publicly accessible.

### Validation

- Frontend lint and production builds for both internal Next.js apps.
- Browser checks for register, login, protected-route redirect, profile update, logout, and expired-token handling.

## Sprint 3: Password Recovery, Change, and Release Readiness

### Goals

- Deliver secure self-service password recovery.
- Verify the complete authentication lifecycle.

### Work

- Implement backend endpoints:
  - `POST /auth/forgot-password`
  - `POST /auth/reset-password`
  - `POST /auth/change-password`
- Use a short-lived reset JWT plus persisted TinyDB reset-token state so tokens are single-use.
- Always return `200` from forgot-password requests, whether or not the email exists.
- Integrate Resend for reset email delivery using environment-only credentials.
- Add frontend routes:
  - `/forgot-password`
  - `/reset-password?token=...`
  - `/account/change-password`
- Add the "Forgot your password?" link to login.
- Disable forgot-password submission after request completion.
- Show reset failures clearly and link back to forgot-password.
- Document email, frontend URL, JWT, and reset-expiry environment variables.
- Update project progress documentation with delivered scope, validation results, and residual risks.

### Acceptance Criteria

- Reset emails contain a functional, mobile-readable link.
- Reset tokens expire within 15 to 60 minutes and cannot be reused.
- Invalid, expired, and used tokens return `400`.
- Change-password requires a valid session and rejects an incorrect current password.
- No signing secrets or email keys are committed.

### Validation

- Automated API coverage for enumeration resistance, expiry, single use, password updates, and wrong-current-password rejection.
- End-to-end browser test: forgot password, email link, reset, new login, change password.
- Lint and production builds for all affected frontend apps.
- Final `/docs` verification of protected routes and auth endpoints.

## Dependencies and Risks

- The supplier-directory API is the only local backend with sufficient existing routes to meet AUTH-01 route-protection requirements.
- `uis/talent-pipeline-tracker` currently targets an external playground API; it must support the same JWT contract before its protected operations can work end-to-end.
- Resend requires a configured API key and sender identity.
- `.env` files and `infra/**` are protected paths; only `.env.example` and non-protected application code should be changed without further confirmation.
