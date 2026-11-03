-- Nexova nightly orchestration job log.
-- Applied idempotently by the Inventory API startup hook and by the nightly
-- export script itself, so the cron job works even if the API has not started.

create schema if not exists reporting;

create table if not exists reporting.job_runs (
  id uuid primary key default gen_random_uuid(),
  job_name text not null,
  target_date date not null,
  status text not null check (
    status in ('pending', 'processing', 'completed', 'failed')
  ),
  started_at timestamptz null,
  finished_at timestamptz null,
  error_message text null,
  created_at timestamptz not null default now()
);

create index if not exists ix_job_runs_job_target
  on reporting.job_runs (job_name, target_date);

-- The distributed lock: at most one processing row per job. The nightly
-- script's "processing" status is the lock; this index enforces it atomically
-- so two simultaneous instances cannot both claim the same job.
create unique index if not exists ux_job_runs_one_processing
  on reporting.job_runs (job_name)
  where status = 'processing';

alter table reporting.job_runs enable row level security;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke all on table reporting.job_runs from anon;
  end if;
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    revoke all on table reporting.job_runs from authenticated;
  end if;
end $$;
