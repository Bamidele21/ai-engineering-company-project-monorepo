# Sprint 3 — Technical Report Evidence

- **Date:** 2026-10-23
- **Endpoint:** `GET /telemetry/report` (Inventory API)
- **Dashboard:** `/telemetry` in `uis/backoffice`
- **Data source:** Supabase `telemetry_events`

## Metric definitions and questions

| Metric | Operational question | Population and aggregation |
|---|---|---|
| `events_per_day` | Which event types dominate, and how does volume change each day? | Catalogue event types in the resolved window, counted by UTC day and `event_type`. |
| `error_rate_by_type` | What share of captured activity is error-level, and which types contribute? | Full declared event population for the denominator; `error_count` uses stored `level='error'`; `error_rate = error_count / daily_total`. This is a captured-event error share, not a failed-request rate. |
| `page_load_latency_by_day` | How does observed document-load time vary by route and day? | `page_view` rows with `tags.page_path` and `tags.load_duration_ms`; mean milliseconds and sample count by UTC day/route after dropping missing/invalid measurements. |

All three functions filter the timestamp window and event type in SQL, refine dimensions in Pandas, and call `pd.to_datetime(..., utc=True)` before grouping.

## Data prerequisite

The live table held **64 rows** at the final check, with business, navigation, and error events:

- `inbound_order_created` (35)
- `outbound_order_created` (19)
- `stock_threshold_triggered` (3)
- `outbound_order_rejected` (2)
- `page_view` (3)
- `kit_cost_variance_detected` (1)
- `frontend_error_captured` (1)

The technical event was generated through the real backoffice: headless Chrome loaded `/login`, the existing `TelemetryBootstrap` listeners were active, and an uncaught `Error` was scheduled in the page. The browser emitted `frontend_error_captured` through the normal `track()` transport, and `POST /telemetry/events` returned `200`. The stored row has `level='error'`, `page_path='/login'`, `error_type='Error'`, and a sanitised `message`. No SQL row was fabricated.

## Live report response

The live endpoint returned HTTP `200`; the final pipeline result after the dashboard validation activity is this shape (abridged to representative rows):

```json
{
  "period": {
    "from": "2026-10-16T17:41:27.675969Z",
    "to": "2026-10-23T17:41:27.675969Z"
  },
  "metrics": {
    "events_per_day": [
      { "date": "2026-10-21", "event_type": "page_view", "count": 1 },
      { "date": "2026-10-22", "event_type": "inbound_order_created", "count": 35 },
      { "date": "2026-10-22", "event_type": "outbound_order_created", "count": 19 },
      { "date": "2026-10-22", "event_type": "outbound_order_rejected", "count": 2 },
      { "date": "2026-10-22", "event_type": "stock_threshold_triggered", "count": 3 },
      { "date": "2026-10-23", "event_type": "frontend_error_captured", "count": 1 },
      { "date": "2026-10-23", "event_type": "page_view", "count": 2 }
    ],
    "error_rate_by_type": [
      {
        "date": "2026-10-23",
        "event_type": "frontend_error_captured",
        "error_count": 1,
        "total_count": 1,
        "daily_total": 3,
        "error_rate": 0.3333333333333333
      },
      {
        "date": "2026-10-22",
        "event_type": "inbound_order_created",
        "error_count": 0,
        "total_count": 35,
        "daily_total": 60,
        "error_rate": 0.0
      }
    ],
    "page_load_latency_by_day": [
      {
        "date": "2026-10-21",
        "page_path": "/inventory/products",
        "average_load_duration_ms": 742.0,
        "sample_count": 1
      },
      {
        "date": "2026-10-23",
        "page_path": "/login",
        "average_load_duration_ms": 1298.0,
        "sample_count": 1
      },
      {
        "date": "2026-10-23",
        "page_path": "/telemetry",
        "average_load_duration_ms": 1725.0,
        "sample_count": 1
      }
    ]
  }
}
```

## Cache evidence

- Successful reports are cached by the resolved UTC `(start, end)` pair for 60 seconds.
- Omitted-date requests reuse the cached resolved default window, so consecutive live requests returned the same period.
- Automated tests verify: a repeated request does not call the pipeline again; a 61-second clock advance recomputes; different windows never share a cache entry; a database failure returns `503` and is not cached.
- The cache is process-local and reports may be up to 60 seconds stale.

## Dashboard

`uis/backoffice/app/telemetry/page.tsx` renders the three metrics as tables, displays the active `period`, accepts optional `from`/`to` dates, and shows loading, empty, and error states. The page reuses the existing backoffice inventory table/card styles and is linked from the shared backoffice navigation.

## Validation performed

1. `uv run pytest -q` from `backrooms/services`: **226 passed** (2 pre-existing deprecation warnings).
2. `npx jest --runInBand` from the repository root: **93 passed** across 14 suites.
3. `npm run lint` and `npm run build` in `uis/backoffice`: passed; `/telemetry` was generated with the other 16 routes.
4. Live Supabase report call: HTTP `200` with the JSON above.
5. Live technical-event check: one `frontend_error_captured` row stored at `level='error'`, plus the browser page views.
6. Dashboard browser check: the `/telemetry` page rendered the live period and metric tables.

## Limitations and deferred work

1. The report cache is process-local; multiple Uvicorn workers would each hold their own copy.
2. `error_rate_by_type` counts stored `level='error'` only. Warn-level business rejections remain visible in `events_per_day` but are not errors.
3. The live page-load population is small; the metric is honest but thin until more real page views accumulate.
4. The optional `auth_failure_rate` metric is not implemented because Sprint 1 deferred `login_succeeded` / `login_failed` capture.
5. Duplicate telemetry rows are still possible by design; metrics count stored rows, not unique `eventId` values.
6. The Docker image was not rebuilt because the Docker daemon was unavailable; `requirements.txt` was regenerated from the lockfile so the image includes Pandas and NumPy.
