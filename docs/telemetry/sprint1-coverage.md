# Sprint 1 capture coverage checklist

Contract source: `telemetry1-context.md`, `telemetry-sprint-plan.md`, `telemetry-plan.md` §5.2.1, and `event-schemas.json`.

Host API: Inventory API (`POST /telemetry/events`).

| Event | Classification | Emitter | Hook | Sprint 1 status |
|---|---|---|---|---|
| `inbound_order_created` | mandatory | inventory-api | `routers/inventory.py` after a committed inbound order | implemented |
| `outbound_order_created` | mandatory | inventory-api | `routers/inventory.py` after a committed outbound order | implemented |
| `stock_threshold_triggered` | mandatory | inventory-api | outbound post-commit edge check | implemented |
| `direct_stock_edit_rejected` | mandatory | inventory-api | PUT/PATCH/DELETE 405 stubs on `/inventory/products*` | implemented |
| `kit_cost_variance_detected` | mandatory | inventory-api | inbound post-commit historical variance check | implemented |
| `outbound_order_rejected` | opportunity | inventory-api | insufficient-stock 400 branch | implemented |
| `page_view` | opportunity | web | `PageViewTracker` mounted in `app/layout.tsx` | implemented |
| `frontend_error_captured` | opportunity | web | `error-listeners.ts` mounted in `TelemetryBootstrap` | implemented |
| `network_request_failed` | opportunity | web | `authorizedFetch` catch branch | implemented |
| `validation_failed` | opportunity | web | inbound/outbound client validation branches | implemented |

Deferred in Sprint 1, documented rather than silently omitted:

| Event / activity | Reason |
|---|---|
| `login_succeeded`, `login_failed`, `session_expired` | Optional authentication activity; deferred with Web Vitals |
| `form_abandoned` | Optional navigation opportunity; needs unmount hooks on four forms |
| `product_created`, `supplier_rate_edited`, `incident_report_analyzed`, `password_reset_requested`, `password_reset_failed`, `user_registered`, `admin_role_changed` | Opportunity backlog after required coverage |
| Web Vitals | Requires an explicit schema addition before capture |
| `api_latency_recorded` | Backend middleware is not required for the Sprint 1 exit gate; page-load timing covers the performance baseline |

PII checks:

- No emails, passwords, names, reset tokens, submitted form values, query strings, or `assigned_to` values are emitted.
- `frontend_error_captured` messages are sanitised (emails/URLs stripped, sensitive query values redacted, 300-character cap).
- `page_path`, `path`, and `target` are query-stripped route/path forms.

Automated evidence:

- `uv run pytest` from `backrooms/services`: 181 passed.
- `npx jest --runInBand` from the repository root: 85 passed across 13 suites.
- `npm run lint` and `npm run build` in `uis/backoffice`: passed.
- `docs/telemetry/event-schemas.json`: valid draft-07 and consistent with `telemetry-plan.md`.

Manual evidence still required (browser):

1. Set `NEXT_PUBLIC_TELEMETRY_ENDPOINT=http://localhost:8001/telemetry/events` in the root `.env` and restart the UI.
2. Set `TELEMETRY_ENDPOINT=http://localhost:8001/telemetry/events` in the Inventory API environment and restart it.
3. Sign in, visit overview/inventory/suppliers/incidents, submit one inbound and one outbound order, and trigger one client validation error.
4. In DevTools → Network, filter `telemetry/events` and capture a batch with a `200` response plus `{ "received": N }`.
5. Save the redacted screenshot and representative payloads with the PR evidence.
