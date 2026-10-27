"""Prefect behavior tests for real cache and optional-state semantics."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from prefect import flow

import data.pipelines.weekly_office_program_performance.tasks as tasks

WEEK = "2026-10-19"


def _row(unit_cost: str) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "timestamp": datetime(2026, 10, 20, 12, tzinfo=timezone.utc).isoformat(),
        "service": "inventory-api",
        "event_type": "inbound_order_created",
        "tags": {
            "office": "valencia",
            "programme_id": "b2b-sales",
            "quantity": 1,
            "currency": "EUR",
            "unit_cost": unit_cost,
            "order_id": str(uuid.uuid4()),
            "_meta": {"eventId": str(uuid.uuid4()), "schemaVersion": "1.0"},
        },
    }


@flow
def _transform_three_times(rows_a: list[dict], rows_b: list[dict]) -> list[dict]:
    first = tasks.transform_weekly_performance(
        rows_a, [["valencia", "b2b-sales"]], ["b2b-sales"], WEEK
    )
    second = tasks.transform_weekly_performance(
        rows_a, [["valencia", "b2b-sales"]], ["b2b-sales"], WEEK
    )
    third = tasks.transform_weekly_performance(
        rows_b, [["valencia", "b2b-sales"]], ["b2b-sales"], WEEK
    )
    return [first, second, third]


def test_transform_task_caches_identical_input_and_misses_on_change(monkeypatch):
    calls = {"count": 0}
    real_transform = tasks.transform_week

    def counting_transform(*args, **kwargs):
        calls["count"] += 1
        return real_transform(*args, **kwargs)

    monkeypatch.setattr(tasks, "transform_week", counting_transform)

    rows_a = [_row("10.00")]
    rows_b = [_row("25.00")]
    first, second, third = _transform_three_times(rows_a, rows_b)

    # Two executions for three calls: identical input reused the cached result,
    # changed input invalidated it.
    assert calls["count"] == 2
    assert first["rows"] == second["rows"]
    assert first["rows"][0]["total_material_cost"] == "10.00"
    assert third["rows"][0]["total_material_cost"] == "25.00"


@flow
def _optional_snapshot_flow() -> bool:
    state = tasks.write_eval_snapshot(
        run_id="test-run",
        week_start=WEEK,
        summary={"validation": True},
        fail=True,
        return_state=True,
    )
    return state.is_failed()


def test_optional_snapshot_failure_is_observed_without_failing_flow():
    assert _optional_snapshot_flow() is True
