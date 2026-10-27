"""PostgreSQL integration tests for extraction, locking, load, and rollback.

These tests require a disposable database:

    TEST_DATABASE_URL=postgresql+psycopg2://... pytest -m postgres

They are skipped when the variable is absent, so the default suite remains
database-free.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from data.pipelines.weekly_office_program_performance import db, extract, load, run_log
from data.pipelines.weekly_office_program_performance.schema import (
    ensure_reporting_schema,
)

pytestmark = pytest.mark.postgres

WEEK = date(2026, 10, 19)
WINDOW_START = datetime(2026, 10, 19, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 10, 26, tzinfo=timezone.utc)
MIGRATION_PATH = (
    Path(__file__).resolve().parents[4]
    / "backrooms"
    / "services"
    / "reporting"
    / "migrations"
    / "001_reporting_schema.sql"
)


@pytest.fixture(scope="module")
def pg_engine():
    database_url = __import__("os").getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA IF EXISTS reporting CASCADE")
        connection.exec_driver_sql("DROP TABLE IF EXISTS public.telemetry_events")
        connection.exec_driver_sql("DROP TABLE IF EXISTS public.assets")
        connection.exec_driver_sql("DROP TABLE IF EXISTS public.programmes")
        connection.exec_driver_sql(
            """
            CREATE TABLE public.programmes (
                id integer primary key,
                slug text not null unique,
                name text not null
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE public.assets (
                id integer primary key,
                office text not null,
                programme_id integer references public.programmes(id)
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TABLE public.telemetry_events (
                id uuid primary key,
                timestamp timestamptz not null,
                service text not null,
                event_type text not null,
                level text not null default 'info',
                value numeric null,
                message text null,
                tags jsonb not null default '{}'::jsonb
            )
            """
        )
        connection.execute(
            text(
                "INSERT INTO public.programmes (id, slug, name) "
                "VALUES (1, 'b2b-sales', 'B2B Sales'), "
                "(2, 'basic-leadership', 'Basic Leadership')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO public.assets (id, office, programme_id) "
                "VALUES (1, 'Valencia', 1), (2, 'Miami', 1), (3, 'Valencia', 2)"
            )
        )
    ensure_reporting_schema(engine)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables(pg_engine):
    with pg_engine.begin() as connection:
        connection.exec_driver_sql("DELETE FROM public.telemetry_events")
        connection.exec_driver_sql("DELETE FROM reporting.pipeline_rejected_events")
        connection.exec_driver_sql("DELETE FROM reporting.pipeline_runs")
        connection.exec_driver_sql("DELETE FROM reporting.weekly_office_program_performance")
    yield


def _insert_event(
    engine,
    *,
    event_id: str,
    event_type: str,
    office: str = "valencia",
    programme: str = "b2b-sales",
    quantity: int = 1,
    unit_cost: str | None = None,
    currency: str = "EUR",
    timestamp: datetime | None = None,
) -> None:
    tags = {
        "office": office,
        "programme_id": programme,
        "quantity": quantity,
        "currency": currency,
        "product_id": 1,
        "product_category": "certification",
        "_meta": {"eventId": event_id, "schemaVersion": "1.0"},
    }
    if unit_cost is not None:
        tags["unit_cost"] = unit_cost
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO public.telemetry_events
                (id, timestamp, service, event_type, level, value, message, tags)
                VALUES
                (:id, :timestamp, 'inventory-api', :event_type, 'info',
                 NULL, NULL, CAST(:tags AS jsonb))
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "timestamp": timestamp or datetime(2026, 10, 20, 12, tzinfo=timezone.utc),
                "event_type": event_type,
                "tags": __import__("json").dumps(tags),
            },
        )


def test_extract_reads_jsonb_window_and_dimension_scaffold(pg_engine):
    _insert_event(
        pg_engine,
        event_id="e1",
        event_type="inbound_order_created",
        quantity=3,
        unit_cost="12.50",
    )
    _insert_event(
        pg_engine,
        event_id="e2",
        event_type="outbound_order_created",
        office="miami",
        currency="USD",
    )
    _insert_event(
        pg_engine,
        event_id="outside",
        event_type="inbound_order_created",
        timestamp=datetime(2026, 10, 27, 0, 0, tzinfo=timezone.utc),
    )

    result = extract.extract_week(pg_engine, WEEK)

    assert len(result.raw_rows) == 2
    assert result.source_event_counts == {
        "inbound_order_created": 1,
        "outbound_order_created": 1,
    }
    assert result.office_counts == {"valencia": 1, "miami": 1}
    assert ("valencia", "b2b-sales") in result.dimension_pairs
    assert ("miami", "b2b-sales") in result.dimension_pairs
    assert ("valencia", "basic-leadership") in result.dimension_pairs
    assert set(result.known_programmes) == {"b2b-sales", "basic-leadership"}


def test_load_is_idempotent_and_preserves_row_identity(pg_engine):
    run_id = uuid.uuid4()
    run_log.create_or_adopt_run(
        pg_engine,
        run_id=run_id,
        trigger_type="manual",
        triggered_by="test",
        target_weeks=[WEEK],
        source_window_start=WINDOW_START,
        source_window_end=WINDOW_END,
    )
    rows = [
        {
            "office": "valencia",
            "programme_id": "b2b-sales",
            "week_start": WEEK.isoformat(),
            "total_material_cost": "48.00",
            "kits_delivered_count": 2,
            "shortage_events_count": 1,
            "cost_variance_events_count": 0,
            "currency": "EUR",
        }
    ]
    rejections = [
        {
            "event_id": "bad-1",
            "event_type": "inbound_order_created",
            "reason": "currency_office_mismatch",
            "details": {"field": "currency"},
        }
    ]

    first = load.load_week(
        pg_engine, week_start=WEEK, rows=rows, rejections=rejections, run_id=run_id
    )
    second = load.load_week(
        pg_engine, week_start=WEEK, rows=rows, rejections=rejections, run_id=run_id
    )

    assert first.records_loaded == second.records_loaded == 1
    with pg_engine.connect() as connection:
        stored = connection.execute(
            text(
                "SELECT id, total_material_cost FROM "
                "reporting.weekly_office_program_performance WHERE week_start = :week"
            ),
            {"week": WEEK},
        ).mappings().all()
        quarantine = connection.execute(
            text("SELECT count(*) FROM reporting.pipeline_rejected_events")
        ).scalar_one()
    assert len(stored) == 1
    assert float(stored[0]["total_material_cost"]) == 48.0
    assert quarantine == 1

    first_id = stored[0]["id"]
    rows[0]["total_material_cost"] = "50.00"
    load.load_week(
        pg_engine, week_start=WEEK, rows=rows, rejections=[], run_id=run_id
    )
    with pg_engine.connect() as connection:
        updated = connection.execute(
            text(
                "SELECT id, total_material_cost FROM "
                "reporting.weekly_office_program_performance WHERE week_start = :week"
            ),
            {"week": WEEK},
        ).mappings().one()
    assert updated["id"] == first_id
    assert float(updated["total_material_cost"]) == 50.0


def test_mid_load_failure_rolls_back_the_whole_week(pg_engine):
    run_id = uuid.uuid4()
    run_log.create_or_adopt_run(
        pg_engine,
        run_id=run_id,
        trigger_type="manual",
        triggered_by="test",
        target_weeks=[WEEK],
        source_window_start=WINDOW_START,
        source_window_end=WINDOW_END,
    )
    with pg_engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE OR REPLACE FUNCTION reporting.fail_on_boom()
            RETURNS trigger AS $$
            BEGIN
              IF NEW.programme_id = 'boom' THEN
                RAISE EXCEPTION 'injected mid-load failure';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        connection.exec_driver_sql(
            "DROP TRIGGER IF EXISTS trg_fail_on_boom ON "
            "reporting.weekly_office_program_performance"
        )
        connection.exec_driver_sql(
            "CREATE TRIGGER trg_fail_on_boom BEFORE INSERT OR UPDATE ON "
            "reporting.weekly_office_program_performance FOR EACH ROW "
            "EXECUTE FUNCTION reporting.fail_on_boom()"
        )

    good = {
        "office": "valencia",
        "programme_id": "b2b-sales",
        "week_start": WEEK.isoformat(),
        "total_material_cost": "10.00",
        "kits_delivered_count": 0,
        "shortage_events_count": 0,
        "cost_variance_events_count": 0,
        "currency": "EUR",
    }
    boom = {**good, "programme_id": "boom"}

    with pytest.raises(SQLAlchemyError):
        load.load_week(
            pg_engine,
            week_start=WEEK,
            rows=[good, boom],
            rejections=[],
            run_id=run_id,
        )

    with pg_engine.connect() as connection:
        count = connection.execute(
            text(
                "SELECT count(*) FROM reporting.weekly_office_program_performance"
            )
        ).scalar_one()
    assert count == 0

    with pg_engine.begin() as connection:
        connection.exec_driver_sql(
            "DROP TRIGGER IF EXISTS trg_fail_on_boom ON "
            "reporting.weekly_office_program_performance"
        )


def test_active_run_unique_index_rejects_a_second_run(pg_engine):
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    run_log.create_or_adopt_run(
        pg_engine,
        run_id=first_id,
        trigger_type="manual",
        triggered_by="test",
        target_weeks=[WEEK],
        source_window_start=WINDOW_START,
        source_window_end=WINDOW_END,
    )

    with pytest.raises(Exception):
        run_log.create_or_adopt_run(
            pg_engine,
            run_id=second_id,
            trigger_type="manual",
            triggered_by="test",
            target_weeks=[WEEK],
            source_window_start=WINDOW_START,
            source_window_end=WINDOW_END,
        )


def test_advisory_lock_serializes_runs(pg_engine, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", str(pg_engine.url))
    db.dispose_engine()
    try:
        with db.advisory_lock(key=987654321) as first:
            assert first is True
            with db.advisory_lock(key=987654321) as second:
                assert second is False
    finally:
        db.dispose_engine()


def test_reporting_migration_is_idempotent_and_enables_rls(pg_engine):
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    with pg_engine.begin() as connection:
        connection.exec_driver_sql(sql)
        connection.exec_driver_sql(sql)
    with pg_engine.connect() as connection:
        flags = connection.execute(
            text(
                """
                SELECT c.relname, c.relrowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'reporting'
                  AND c.relname IN (
                    'weekly_office_program_performance',
                    'pipeline_runs',
                    'pipeline_rejected_events'
                  )
                ORDER BY c.relname
                """
            )
        ).all()
    assert len(flags) == 3
    assert all(flag[1] for flag in flags)
