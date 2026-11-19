"""Behavioral tests for the dead letter queue storage layer."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import insert

from services.task_queue.storage import (
    dead_letter_tasks,
    ensure_dead_letter_table,
    list_dead_letter,
    record_dead_letter,
)


def test_record_and_list_round_trip(engine):
    recorded = record_dead_letter(
        task_id="t-1",
        task_name="nexova.analyze_incident_csv",
        attempt=4,
        error="FileNotFoundError: staged file missing",
        engine=engine,
    )

    rows = list_dead_letter(engine=engine)
    assert len(rows) == 1
    row = rows[0]
    assert row["task_id"] == "t-1"
    assert row["task_name"] == "nexova.analyze_incident_csv"
    assert row["attempt"] == 4
    assert row["error_message"] == "FileNotFoundError: staged file missing"
    # SQLite has no timezone-aware column type, so the stored value comes
    # back naive; the instant itself must be identical.
    assert row["created_at"] == recorded["created_at"].replace(tzinfo=None)


def test_list_returns_newest_first(engine):
    now = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            insert(dead_letter_tasks).values(
                task_id="t-old",
                task_name="nexova.analyze_incident_csv",
                attempt=4,
                error_message="old failure",
                created_at=now - timedelta(hours=1),
            )
        )
        connection.execute(
            insert(dead_letter_tasks).values(
                task_id="t-new",
                task_name="nexova.analyze_incident_csv",
                attempt=4,
                error_message="new failure",
                created_at=now,
            )
        )

    rows = list_dead_letter(engine=engine)
    assert [row["task_id"] for row in rows] == ["t-new", "t-old"]


def test_list_respects_limit(engine):
    for index in range(3):
        record_dead_letter(
            task_id=f"t-{index}",
            task_name="nexova.analyze_incident_csv",
            attempt=4,
            error="failure",
            engine=engine,
        )

    assert len(list_dead_letter(limit=2, engine=engine)) == 2


def test_ensure_dead_letter_table_is_idempotent(engine):
    ensure_dead_letter_table(engine)
    ensure_dead_letter_table(engine)
    rows = list_dead_letter(engine=engine)
    assert rows == []
