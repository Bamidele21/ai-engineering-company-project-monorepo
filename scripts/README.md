# `scripts` folder

This folder contains **helper scripts** for the monorepo: development automation, maintenance utilities, repetitive tasks (setup, lint, migrations, data generation, etc.), and internal tooling.

- **Main purpose**: group support tools that do not belong to a specific app, agent, or pipeline but make the team’s work easier.
- **Recommendation**: document each script (what it does, parameters, requirements, usage examples) and keep them reproducible (and safe) across environments.

> _Spanish version: [README.es.md](./README.es.md)._

## `nightly_export.py`

Standalone nightly telemetry job (ticket DEV-53). For the previous UTC calendar
day it:

1. exports `telemetry_events` rows to `data/raw/telemetry_YYYY-MM-DD.csv`
   (only when the file does not exist yet — the CSV is an audit backup, the ETL
   reads from the database);
2. triggers the weekly ETL pipeline as a subprocess
   (`python data/pipelines/pipeline.py`);
3. records the execution in `reporting.job_runs` with the state machine
   `pending → processing → completed | failed`. The `processing` status is the
   distributed lock (a second simultaneous instance aborts silently) and a
   `completed` row for the same `(job_name, target_date)` makes the run
   idempotent.

Usage (from the repository root):

```bash
python scripts/nightly_export.py
TARGET_DATE=2026-10-25 python scripts/nightly_export.py   # backfill a date
```

`TARGET_DATE=YYYY-MM-DD` overrides the target date for testing. The script is
an independent process — it never runs inside the FastAPI app.

**Trigger:** the `nightly-scheduler` Docker compose service runs
`scripts/nightly-crontab` under supercronic with the cron expression
`0 3 * * *` (daily 03:00 UTC). Logs stream to
`docker compose logs nightly-scheduler`.
