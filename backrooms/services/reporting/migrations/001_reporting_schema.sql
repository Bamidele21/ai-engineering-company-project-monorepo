-- Nexova weekly performance reporting schema.
-- Applied idempotently by the Inventory API startup hook and by operators.

create schema if not exists reporting;

create table if not exists reporting.weekly_office_program_performance (
  id uuid primary key default gen_random_uuid(),
  office text not null,
  programme_id text not null,
  week_start date not null,
  total_material_cost numeric not null default 0,
  kits_delivered_count integer not null default 0,
  shortage_events_count integer not null default 0,
  cost_variance_events_count integer not null default 0,
  currency text not null,
  computed_at timestamptz not null default now(),
  unique (office, programme_id, week_start)
);

create index if not exists ix_weekly_performance_week_start
  on reporting.weekly_office_program_performance (week_start);

create table if not exists reporting.pipeline_runs (
  run_id uuid primary key default gen_random_uuid(),
  flow_run_id text null,
  pipeline_name text not null,
  trigger_type text not null check (
    trigger_type in ('scheduled', 'manual', 'backfill', 'recompute')
  ),
  triggered_by text null,
  status text not null check (
    status in (
      'queued',
      'running',
      'completed',
      'completed_with_warnings',
      'failed',
      'skipped_locked'
    )
  ),
  target_weeks jsonb not null default '[]'::jsonb,
  source_window_start timestamptz not null,
  source_window_end timestamptz not null,
  started_at timestamptz null,
  finished_at timestamptz null,
  heartbeat_at timestamptz null,
  checkpoint_stage text null check (
    checkpoint_stage in ('extract', 'validate', 'transform', 'load', 'complete')
  ),
  checkpoint_week date null,
  records_extracted integer not null default 0,
  records_deduplicated integer not null default 0,
  records_rejected integer not null default 0,
  records_loaded integer not null default 0,
  source_event_counts jsonb not null default '{}'::jsonb,
  office_counts jsonb not null default '{}'::jsonb,
  reconciliation jsonb not null default '{}'::jsonb,
  supersedes_run_id uuid null references reporting.pipeline_runs(run_id),
  error_code text null,
  error_message text null,
  retry_count integer not null default 0,
  created_at timestamptz not null default now()
);

create index if not exists ix_pipeline_runs_pipeline_started
  on reporting.pipeline_runs (pipeline_name, started_at desc);

create unique index if not exists ux_pipeline_runs_one_active
  on reporting.pipeline_runs (pipeline_name)
  where status in ('queued', 'running');

create table if not exists reporting.pipeline_rejected_events (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references reporting.pipeline_runs(run_id) on delete cascade,
  event_id text null,
  event_type text not null,
  reason text not null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists ix_rejected_events_run
  on reporting.pipeline_rejected_events (run_id);

-- A retry of the same run must not duplicate quarantine rows for the same
-- source event and reason.
create unique index if not exists ux_rejected_events_run_source_reason
  on reporting.pipeline_rejected_events (run_id, event_id, event_type, reason);

alter table reporting.weekly_office_program_performance enable row level security;
alter table reporting.pipeline_runs enable row level security;
alter table reporting.pipeline_rejected_events enable row level security;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke all on schema reporting from anon;
    revoke all on table reporting.weekly_office_program_performance from anon;
    revoke all on table reporting.pipeline_runs from anon;
    revoke all on table reporting.pipeline_rejected_events from anon;
  end if;
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    revoke all on schema reporting from authenticated;
    revoke all on table reporting.weekly_office_program_performance from authenticated;
    revoke all on table reporting.pipeline_runs from authenticated;
    revoke all on table reporting.pipeline_rejected_events from authenticated;
  end if;
end $$;
