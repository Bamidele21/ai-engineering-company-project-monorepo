# Error Handling Audit Report — Nexova Monorepo

**Scope:** `/backrooms` (2 Python services + tests), `/Scripts` (Python CLI + TS logic module), `/UIs` (2 Next.js apps, 1 Next.js marketing site, 1 static landing page). 82 source files reviewed; `backrooms/.env`, `.next`, `node_modules`, `__pycache__` excluded.

---

## CRITICAL

No CRITICAL findings. The highest-impact issue is HIGH-1 (silent password-reset failure across the full stack).

---

## HIGH

### HIGH-1 — Password-reset email failures are silently swallowed end-to-end; user is told an email was sent when none was
- **File:** `backrooms/services/Supply_directory_API/routes/auth.py:98-105`; `auth/email.py:59-60`; `UIs/backoffice/app/forgot-password/page.tsx:26-31`; `UIs/talent-pipeline-tracker/app/forgot-password/page.tsx` (same pattern)
- **Category:** 3 (silent failure), 2 (overly broad catch), 7 (no call to action)
- **Problem:** `except Exception` + `logger.exception` around the email send returns HTTP 200 regardless. This also swallows the `RuntimeError("RESEND_API_KEY must be configured")` from `email.py:59-60`, so a misconfiguration breaks password reset entirely. The UI additionally swallows **all** errors — including network failures where the request never reached the API — and shows "If that address is registered, you'll receive a reset link shortly." A user who lost their password gets a false confirmation and no recovery path; the failure is only visible in server logs.
- **Fix:** In the route, treat a missing API key as a hard config error (503, alerting) rather than catching it with the send failure; log send failures with metrics/alerting. In the UI, distinguish a network-level failure (show "Something went wrong — please try again", which reveals no enumeration information) from a completed 200 response.

### HIGH-2 — Raw API response bodies are thrown as `Error` and rendered verbatim in the UI
- **File:** `UIs/talent-pipeline-tracker/lib/api/client.ts:45-47` and `:73-75`; rendered in `components/candidates/CandidateForm.tsx:101-104`, `app/page.tsx:73-75`, `app/candidates/[id]/page.tsx:87-89` and `:141-143`
- **Category:** 4 (raw error exposure)
- **Problem:** `throw new Error(errorBody)` where `errorBody = await response.text()` passes the raw server body into React error states. JSON bodies (`{"detail":"..."}`) display as literal JSON strings; any non-JSON error page (reverse-proxy 502 HTML, backend stack-trace page) is shown to the user verbatim, potentially leaking internal infrastructure details.
- **Fix:** Parse `detail` from JSON like `lib/auth/session.ts:parseApiError` does; map unknown/non-JSON bodies to a generic fallback message; log the raw body server-side or to console instead of displaying it.

### HIGH-3 — Raw Python exception text (including internal temp-file paths) returned in API detail and surfaced in the UI
- **File:** `backrooms/services/APIs/analyzer-api.py:79-80`; passthrough at `UIs/backoffice/app/incidents/page.tsx:49`
- **Category:** 4 (raw error exposure), 5 (internal paths)
- **Problem:** `detail=f"Invalid CSV file: {error}"` interpolates `str(error)` for `OSError`/`csv.Error`/`ValueError`. `OSError` messages embed filesystem paths (e.g., the temp file created at `analyzer-api.py:53-55`), exposing internal path structure; any other exception text the CSV layer produces reaches the browser directly.
- **Fix:** Return a fixed client-safe message ("The uploaded file is not a valid CSV."); log the actual exception server-side with the traceback.

---

## MEDIUM

### MED-1 — Unguarded environment parsing in JWT config: startup crash or 500, and a swallowed misconfiguration in the reset flow
- **File:** `backrooms/services/Supply_directory_API/auth/security.py:12-15` (module level), `:26-27`, `:56-65`; caller at `routes/auth.py:95`
- **Category:** 1 (missing try/catch), 3 (silent failure)
- **Problem:** `int(os.getenv(...))` at import time (line 12) crashes the whole service on startup if the env value is non-numeric; `token_expiry_minutes()` raises unhandled `ValueError` per request (→ 500); `password_reset_expiry_minutes()` raises `RuntimeError` for out-of-range values, which in the `forgot-password` route happens **after** the user lookup, producing a 500 that the UI then swallows as success (compounding HIGH-1).
- **Fix:** Validate all env-derived config once at startup (fail fast with a clear message); catch `ValueError`/`RuntimeError` at the route boundary and return 503 with alerting.

### MED-2 — Raw browser network error messages displayed to users
- **File:** `UIs/backoffice/lib/auth/session.ts` (all fetch functions, e.g. `:46-51`); `UIs/talent-pipeline-tracker/lib/auth/session.ts` (same); rendered in `app/login/page.tsx:34-39`, `app/register/page.tsx:59-64`, `app/account/profile/page.tsx:32-37` (both apps)
- **Category:** 4 (raw error exposure)
- **Problem:** Network failures (`TypeError: Failed to fetch`, DNS errors) are not caught at the lib layer, so `error.message` in the page catch shows the raw browser error string instead of a friendly message.
- **Fix:** Wrap fetch calls in the lib with `try/catch` and rethrow a friendly `Error` (keeping parsed API `detail`); pages then only ever render curated messages.

### MED-3 — CSV analyzer CLI crashes with a traceback on export failure or closed stdin
- **File:** `Scripts/CSV_analyzer/analyze.py:248-252`
- **Category:** 1 (missing try/catch)
- **Problem:** After a successful analysis, `input()` raises an unhandled `EOFError` when stdin is closed (piped input, CI, subprocess use — exactly how `analyzer-api.py` style automation might call it), and `export_results()` has no `OSError` handling for an unwritable output path. Both end in a raw traceback despite the analysis having succeeded.
- **Fix:** Wrap `export_results` in `try/except OSError` (message to stderr, `return 1`); catch `EOFError` around `input()` and skip the prompt.

### MED-4 — Potential PII/reset-token leak into logs via exception logging
- **File:** `backrooms/services/Supply_directory_API/routes/auth.py:104`
- **Category:** 5 (sensitive data in logs)
- **Problem:** `logger.exception("Unable to send password reset email")` logs the full traceback of the Resend SDK exception, which can echo the request payload — user email and the reset URL containing the live reset token — depending on what the SDK embeds in the exception message.
- **Fix:** Log a sanitized message (no payload, no token, no URL); never attach the exception object to logs that include the email payload; add an alert/metric instead.

---

## LOW

### LOW-1 — Unguarded upload read; no size limit
- **File:** `backrooms/services/APIs/analyzer-api.py:70`
- **Category:** 1 (missing try/catch)
- **Problem:** `await file.read()` can raise on client disconnect (→ 500) and reads unbounded content into memory.
- **Fix:** Read inside a try/except; enforce a max upload size (e.g., reject > 10 MB with 413).

### LOW-2 — Email SDK call has no local error handling
- **File:** `backrooms/services/Supply_directory_API/auth/email.py:67`
- **Category:** 1 (missing try/catch)
- **Problem:** `resend.Emails.send(...)` failures rely entirely on the route's broad catch, which cannot distinguish SDK errors from configuration errors (see HIGH-1).
- **Fix:** Catch SDK exceptions here and raise a typed `EmailDeliveryError`; let config errors propagate separately.

### LOW-3 — Broad `except Exception` rollback (defensible, worth narrowing)
- **File:** `backrooms/services/Supply_directory_API/auth/services.py:70-72`
- **Category:** 2 (overly broad catch)
- **Problem:** Catches everything around the profile insert; acceptable because it cleans up and re-raises, but it would also roll back for non-DB failures and masks the failure mode.
- **Fix:** Catch the specific exceptions TinyDB/file I/O can raise.

### LOW-4 — Unhandled invariant `RuntimeError` in profile update
- **File:** `backrooms/services/Supply_directory_API/auth/services.py:92-93`; route `routes/profiles.py:26-33`
- **Category:** 1 (missing try/catch)
- **Problem:** "Profile disappeared while updating" propagates uncaught to a generic 500; the route has no error mapping.
- **Fix:** Catch in the route and map to a 404/500 with a generic message plus a log entry.

### LOW-5 — Supplier routes have no DB error handling; possible `TypeError` on missing post-update read
- **File:** `backrooms/services/Supply_directory_API/routes/suppliers.py:50-146` (all endpoints); notably `:113-115` and `:129-131`
- **Category:** 1 (missing try/catch)
- **Problem:** TinyDB I/O failures surface as opaque 500s with no logging; `_attach_id(updated)` would raise `TypeError` (→ 500) if the row read after `table.update` unexpectedly returned `None`.
- **Fix:** Wrap DB operations with logging; guard the `None` case and raise a clean 404/500.

### LOW-6 — Malformed stored password hash causes unhandled 500 at login
- **File:** `backrooms/services/Supply_directory_API/routes/auth.py:65`
- **Category:** 1 (missing try/catch)
- **Problem:** `passlib`'s `verify_password` raises `ValueError` on a corrupt/invalid stored hash, producing an unhandled 500.
- **Fix:** Catch `ValueError` around verification; log the data-integrity issue and return 401.

### LOW-7 — Load-error states offer no retry action
- **File:** `UIs/backoffice/app/account/profile/page.tsx:101-108`; `UIs/backoffice/app/suppliers/page.tsx:469-473`; `UIs/talent-pipeline-tracker/app/page.tsx:129-131`; `app/candidates/[id]/page.tsx:240-242`; `app/candidates/[id]/edit/page.tsx:78-80`
- **Category:** 7 (no user call to action)
- **Problem:** Error banners are rendered but the only way to recover is a full browser reload (or changing filters).
- **Fix:** Add a "Try again" button that re-invokes the load function.

### LOW-8 — Silent `localStorage` catches (documented, acceptable)
- **File:** `UIs/backoffice/lib/auth/storage.ts:8-12, 20-24, 32-36`; `UIs/talent-pipeline-tracker/lib/auth/storage.ts` (same)
- **Category:** 3 (silent failure)
- **Problem:** Storage failures are swallowed with comments. This is a deliberate, defensible pattern; flagged only for completeness.
- **Fix:** None required; optionally surface a one-time notice when the session cannot be persisted.

### LOW-9 — Malformed notes payload silently renders as "No internal notes yet"
- **File:** `UIs/talent-pipeline-tracker/lib/api/notes.ts:4-22`
- **Category:** 3 (silent failure)
- **Problem:** `normalizeNotes` returns `[]` for any unparseable payload, so a server bug or unexpected shape displays as an empty state instead of an error.
- **Fix:** Return a discriminated result (data vs. parse failure) so the page can show an error state.

### LOW-10 — Export download link has no failure handling
- **File:** `UIs/backoffice/app/incidents/page.tsx:55`
- **Category:** 6/7 (no error state or call to action)
- **Problem:** The "Download results" anchor hits the export endpoint directly; a 404 (no analysis on the server, e.g., another session's state) or a network failure shows the browser's default error/raw JSON, outside the app's UI.
- **Fix:** Fetch the export as a blob with error handling, or disable the link until a local analysis has completed in this session.

### LOW-11 — Shared logic module executes at import time; any throw crashes the dashboard with no error boundary
- **File:** `Scripts/src/sample-usage.ts:194` (`export const sampleUsageResults = runSampleUsage()`); imported by `UIs/backoffice/app/page.tsx:2`
- **Category:** 6 (missing error UI state)
- **Problem:** `runSampleUsage()` runs at module scope, so any thrown error (bad sample data, a broken utility) breaks the entire backoffice overview with the Next error page; no error boundary exists.
- **Fix:** Compute lazily (useEffect/useMemo) with a try/catch fallback, or add a React error boundary around the dashboard.

---

## Category 8 coverage — exit codes

No violations found. `Scripts/CSV_analyzer/analyze.py:256-257` uses `SystemExit(main())` with distinct codes (2 for usage, 1 for load errors); `tests/test_password_recovery.py:247-248` does the same; `routes/seed.py:196-197` exits nonzero via the unhandled exception path. None of the scripts catch a critical error and exit 0.

## Well-handled areas (for reference)

- `auth/dependencies.py:13-31` — clean decode-error → 401 mapping with `WWW-Authenticate`.
- `UIs/backoffice` + tracker `lib/auth/session.ts:41-43` — `readJson` guards malformed bodies; `parseApiError` handles both string and FastAPI validation-array `detail` formats.
- `app/reset-password/page.tsx` (both apps) — error state includes a "Request a new reset link" CTA.
- `analyzer-api.py:74-80` — catches `UnicodeDecodeError`/`OSError`/`csv.Error`/`ValueError` and maps them to 400s (apart from HIGH-3's message issue).
- Login/register/change-password forms (both apps) — consistent `isSubmitting`/`try`/`finally` pattern with disabled buttons.

## Observations outside the 8 categories (worth a separate look)

- `UIs/landing_page/application.html` + `validation.js`, and `UIs/website/app/application/page.tsx` show a success modal ("We have received your information") but never send the form data anywhere — no fetch/submission exists. Users are told data was received when nothing was transmitted.
- `backrooms/services/APIs/analyzer-api.py:31, 65, 76` — the `_last_metrics` module global is shared across all users/requests and the `/api/incidents/results/export` endpoint is unauthenticated, so one user can download another user's analysis.
- Talent tracker `app/page.tsx:84-89` — search triggers a full API refetch on every keystroke (no debounce); a slow API produces overlapping requests/errors, though not a correctness bug by itself.
