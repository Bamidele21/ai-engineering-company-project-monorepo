CREATE TABLE IF NOT EXISTS public.telemetry_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp timestamptz NOT NULL,
    service text NOT NULL,
    event_type text NOT NULL,
    level text NOT NULL DEFAULT 'info',
    value numeric NULL,
    message text NULL,
    tags jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_telemetry_events_timestamp
    ON public.telemetry_events (timestamp);

CREATE INDEX IF NOT EXISTS ix_telemetry_events_event_type
    ON public.telemetry_events (event_type);

CREATE INDEX IF NOT EXISTS ix_telemetry_events_tags
    ON public.telemetry_events USING GIN (tags);

ALTER TABLE public.telemetry_events ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON TABLE public.telemetry_events FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON TABLE public.telemetry_events FROM authenticated;
    END IF;
END $$;
