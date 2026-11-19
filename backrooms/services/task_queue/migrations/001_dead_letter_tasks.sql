-- Nexova async task queue dead letter storage.
-- Applied idempotently by the Celery worker startup hook and the analyzer
-- API lifespan, so the DLQ exists even if one of them starts first.

create schema if not exists task_queue;

create table if not exists task_queue.dead_letter_tasks (
  id uuid primary key default gen_random_uuid(),
  task_id text not null,
  task_name text not null,
  attempt integer not null,
  error_message text not null,
  created_at timestamptz not null default now()
);

create index if not exists ix_dead_letter_tasks_created_at
  on task_queue.dead_letter_tasks (created_at desc);

alter table task_queue.dead_letter_tasks enable row level security;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke all on table task_queue.dead_letter_tasks from anon;
  end if;
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    revoke all on table task_queue.dead_letter_tasks from authenticated;
  end if;
end $$;
