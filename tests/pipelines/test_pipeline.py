"""Isolated transformation tests for the Nexova weekly performance KPIs.

These tests call the Prefect task ``.fn`` implementations with in-memory
telemetry-shaped fixtures. No database, network, Prefect server, or secrets are
required. Pure validation and assembly behavior is covered alongside the tasks.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from data.pipelines.weekly_office_program_performance import tasks
from data.process.weekly_performance import kpi as pure_kpi
from data.process.weekly_performance.aggregate import assemble_week
from data.process.weekly_performance.transform import validate_and_dedupe

WEEK = date(2026, 10, 19)
DIMENSIONS = (("valencia", "b2b-sales"), ("miami", "b2b-sales"))
KNOWN = ("b2b-sales",)
_OMIT_EVENT_ID = object()


def _row(
    event_type: str,
    *,
    event_id=_OMIT_EVENT_ID,
    office: str = "valencia",
    programme: str = "b2b-sales",
    quantity=1,
    unit_cost=None,
    currency: str | None = None,
    timestamp: datetime | None = None,
    order_id: str | None = None,
    schema_version: str = "1.0",
    service: str = "inventory-api",
    extra: dict | None = None,
) -> dict:
    meta = {"schemaVersion": schema_version}
    if event_id is not _OMIT_EVENT_ID and event_id is not None:
        meta["eventId"] = event_id
    tags = {
        "office": office,
        "programme_id": programme,
        "quantity": quantity,
        "currency": currency
        if currency is not None
        else ("EUR" if office == "valencia" else "USD"),
        "product_id": 1,
        "product_category": "certification",
        "_meta": meta,
    }
    if unit_cost is not None:
        tags["unit_cost"] = unit_cost
    if order_id is not None:
        tags["order_id"] = order_id
    if extra:
        tags.update(extra)
    return {
        "id": str(uuid.uuid4()),
        "timestamp": timestamp or datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc),
        "service": service,
        "event_type": event_type,
        "tags": tags,
    }


def _events(rows: list[dict]) -> list[dict]:
    validated = validate_and_dedupe(rows, week_start=WEEK)
    return [event.as_dict() for event in validated.events]


def _assemble(
    rows: list[dict],
    *,
    dimensions=DIMENSIONS,
    known=KNOWN,
    threshold=Decimal("0.05"),
):
    validated = validate_and_dedupe(rows, week_start=WEEK)
    events = [event.as_dict() for event in validated.events]
    assembled = assemble_week(
        week_start=WEEK,
        events=events,
        rejections=[rejection.to_dict() for rejection in validated.rejections],
        cost_by_pair=pure_kpi.compute_total_material_cost(events),
        kits_by_pair=pure_kpi.count_kits_delivered(events),
        shortages_by_pair=pure_kpi.count_shortage_events(events),
        variances_by_pair=pure_kpi.count_cost_variance_events(events),
        dimension_pairs=dimensions,
        known_programmes=known,
        records_extracted=validated.records_extracted,
        records_deduplicated=validated.records_deduplicated,
        duplicate_payload_conflict_count=validated.duplicate_payload_conflict_count,
        order_identity_anomaly_count=validated.order_identity_anomaly_count,
        order_identity_missing_count=validated.order_identity_missing_count,
        rejection_threshold=threshold,
    )
    return validated, assembled


def _entry(assembled, office: str, programme: str) -> dict:
    return next(
        row
        for row in assembled.rows
        if row["office"] == office and row["programme_id"] == programme
    )


# ---------------------------------------------------------------------------
# Hand-calculated KPI task cases (the four briefing KPIs)
# ---------------------------------------------------------------------------


def test_total_material_cost_uses_quantity_and_decimal_cost():
    rows = [
        _row("inbound_order_created", quantity=3, unit_cost="12.50", order_id="1"),
        _row("inbound_order_created", quantity=2, unit_cost="5.25", order_id="2"),
        _row(
            "kit_cost_variance_detected",
            quantity=4,
            unit_cost="99.99",
            order_id="3",
            extra={"variance_percent": 55.0},
        ),
    ]

    totals = tasks.compute_total_material_cost.fn(_events(rows))
    assert totals == {"valencia|b2b-sales": "48.00"}

    _, assembled = _assemble(rows, dimensions=(("valencia", "b2b-sales"),))
    row = _entry(assembled, "valencia", "b2b-sales")
    assert row["total_material_cost"] == Decimal("48.00")
    assert row["currency"] == "EUR"
    assert row["cost_variance_events_count"] == 1


def test_kits_delivered_counts_events_not_units():
    rows = [
        _row("outbound_order_created", quantity=10, order_id="1"),
        _row("outbound_order_created", quantity=2, order_id="2"),
    ]

    counts = tasks.count_kits_delivered.fn(_events(rows))
    assert counts == {"valencia|b2b-sales": 2}

    _, assembled = _assemble(rows, dimensions=(("valencia", "b2b-sales"),))
    assert _entry(assembled, "valencia", "b2b-sales")["kits_delivered_count"] == 2


def test_shortage_frequency_counts_captured_threshold_events():
    rows = [
        _row("stock_threshold_triggered", quantity=0, extra={"min_stock": 10}),
        _row("stock_threshold_triggered", quantity=5, extra={"min_stock": 10}),
    ]

    counts = tasks.count_shortage_events.fn(_events(rows))
    assert counts == {"valencia|b2b-sales": 2}

    _, assembled = _assemble(rows, dimensions=(("valencia", "b2b-sales"),))
    assert (
        _entry(assembled, "valencia", "b2b-sales")["shortage_events_count"] == 2
    )


def test_cost_variance_frequency_counts_alerts():
    rows = [
        _row(
            "kit_cost_variance_detected",
            quantity=1,
            unit_cost="20.00",
            order_id="1",
            extra={"variance_percent": 55.0},
        ),
        _row(
            "kit_cost_variance_detected",
            quantity=1,
            unit_cost="5.00",
            order_id="2",
            extra={"variance_percent": -25.0},
        ),
    ]

    counts = tasks.count_cost_variance_events.fn(_events(rows))
    assert counts == {"valencia|b2b-sales": 2}

    _, assembled = _assemble(rows, dimensions=(("valencia", "b2b-sales"),))
    row = _entry(assembled, "valencia", "b2b-sales")
    assert row["cost_variance_events_count"] == 2
    assert row["total_material_cost"] == Decimal("0.00")


# ---------------------------------------------------------------------------
# Defensive behavior of every KPI task
# ---------------------------------------------------------------------------


def test_kpi_tasks_return_empty_mappings_for_empty_input():
    assert tasks.compute_total_material_cost.fn([]) == {}
    assert tasks.count_kits_delivered.fn([]) == {}
    assert tasks.count_shortage_events.fn([]) == {}
    assert tasks.count_cost_variance_events.fn([]) == {}


def test_material_cost_task_rejects_malformed_quantities_and_costs():
    valid = {
        "event_type": "inbound_order_created",
        "office": "valencia",
        "programme_id": "b2b-sales",
    }
    malformed = [
        {**valid, "quantity": None, "unit_cost": "1.00"},
        {**valid, "quantity": 1, "unit_cost": None},
        {**valid, "quantity": "abc", "unit_cost": "1.00"},
        {**valid, "quantity": 1.5, "unit_cost": "1.00"},
        {**valid, "quantity": 0, "unit_cost": "1.00"},
        {**valid, "quantity": -2, "unit_cost": "1.00"},
        {**valid, "quantity": 1, "unit_cost": "NaN"},
        {**valid, "quantity": 1, "unit_cost": "Infinity"},
        {**valid, "quantity": 1, "unit_cost": 0},
        {**valid, "quantity": 1, "unit_cost": -1},
        {**valid, "quantity": 1, "unit_cost": "not-a-number"},
    ]
    for payload in malformed:
        with pytest.raises(ValueError):
            tasks.compute_total_material_cost.fn([payload])


def test_count_tasks_reject_events_with_missing_dimensions():
    cases = [
        (tasks.count_kits_delivered.fn, "outbound_order_created"),
        (tasks.count_shortage_events.fn, "stock_threshold_triggered"),
        (tasks.count_cost_variance_events.fn, "kit_cost_variance_detected"),
    ]
    for task_fn, event_type in cases:
        with pytest.raises(ValueError):
            # Missing office on a matching event.
            task_fn([{"event_type": event_type, "programme_id": "x"}])
        with pytest.raises(ValueError):
            # Missing programme on a matching event.
            task_fn([{"event_type": event_type, "office": "valencia"}])
        with pytest.raises(ValueError):
            # Missing event type entirely.
            task_fn([{"office": "valencia", "programme_id": "x"}])


def test_kpi_tasks_keep_office_currencies_separate():
    rows = [
        _row("inbound_order_created", office="valencia", quantity=3, unit_cost="10.00", order_id="1"),
        _row("inbound_order_created", office="miami", quantity=2, unit_cost="4.00", order_id="2"),
    ]

    totals = tasks.compute_total_material_cost.fn(_events(rows))
    assert totals == {
        "valencia|b2b-sales": "30.00",
        "miami|b2b-sales": "8.00",
    }

    _, assembled = _assemble(rows)
    assert _entry(assembled, "valencia", "b2b-sales")["currency"] == "EUR"
    assert _entry(assembled, "miami", "b2b-sales")["currency"] == "USD"


# ---------------------------------------------------------------------------
# Deduplication and validation
# ---------------------------------------------------------------------------


def test_dedup_keeps_earliest_event_and_reports_payload_conflict():
    event_id = str(uuid.uuid4())
    earlier = _row(
        "inbound_order_created",
        event_id=event_id,
        quantity=1,
        unit_cost="10.00",
        order_id="1",
        timestamp=datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc),
    )
    later = _row(
        "inbound_order_created",
        event_id=event_id,
        quantity=1,
        unit_cost="99.00",
        order_id="1",
        timestamp=datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc),
    )
    later["id"] = "00000000-0000-0000-0000-000000000000"

    validated, assembled = _assemble(
        [later, earlier], dimensions=(("valencia", "b2b-sales"),)
    )

    assert validated.records_extracted == 2
    assert validated.records_deduplicated == 1
    assert validated.duplicate_payload_conflict_count == 1
    assert assembled.reconciliation["duplicate_count"] == 1
    assert _entry(assembled, "valencia", "b2b-sales")[
        "total_material_cost"
    ] == Decimal("10.00")


def test_missing_event_id_falls_back_to_source_row_id():
    first = _row("inbound_order_created", event_id=None, quantity=1, unit_cost="1.00")
    second = _row("inbound_order_created", event_id=None, quantity=1, unit_cost="2.00")

    validated, assembled = _assemble(
        [first, second], dimensions=(("valencia", "b2b-sales"),)
    )

    assert validated.records_extracted == 2
    assert validated.records_deduplicated == 2
    assert _entry(assembled, "valencia", "b2b-sales")[
        "total_material_cost"
    ] == Decimal("3.00")


def test_week_boundary_uses_utc_monday():
    sunday = _row(
        "inbound_order_created",
        quantity=1,
        unit_cost="5.00",
        order_id="1",
        timestamp=datetime(2026, 10, 18, 23, 59, 59, tzinfo=timezone.utc),
    )
    monday = _row(
        "inbound_order_created",
        quantity=1,
        unit_cost="7.00",
        order_id="2",
        timestamp=datetime(2026, 10, 19, 0, 0, tzinfo=timezone.utc),
    )

    validated, assembled = _assemble(
        [sunday, monday], dimensions=(("valencia", "b2b-sales"),)
    )

    assert [rejection.reason for rejection in validated.rejections] == [
        "week_out_of_range"
    ]
    assert _entry(assembled, "valencia", "b2b-sales")[
        "total_material_cost"
    ] == Decimal("7.00")


def test_currency_office_mismatch_is_rejected_not_converted():
    validated, assembled = _assemble(
        [
            _row(
                "inbound_order_created",
                office="valencia",
                currency="USD",
                quantity=1,
                unit_cost="10.00",
                order_id="1",
            )
        ],
        dimensions=(("valencia", "b2b-sales"),),
    )

    assert [rejection.reason for rejection in validated.rejections] == [
        "currency_office_mismatch"
    ]
    assert assembled.publication_blocked is True
    assert "rejection_threshold_exceeded" in assembled.block_reasons


def test_schema_version_and_service_are_rejected():
    validated, _ = _assemble(
        [
            _row(
                "inbound_order_created",
                quantity=1,
                unit_cost="1.00",
                schema_version="2.0",
            ),
            _row(
                "inbound_order_created",
                quantity=1,
                unit_cost="1.00",
                service="other-service",
            ),
        ],
        dimensions=(("valencia", "b2b-sales"),),
    )

    reasons = {rejection.reason for rejection in validated.rejections}
    assert reasons == {"schema_version_not_supported", "service_not_allowed"}


def test_malformed_quantity_and_cost_are_rejected():
    validated, _ = _assemble(
        [
            _row("inbound_order_created", quantity=0, unit_cost="1.00", order_id="1"),
            _row("inbound_order_created", quantity=1, unit_cost="0", order_id="2"),
            _row("inbound_order_created", quantity="abc", unit_cost="1.00", order_id="3"),
            _row("inbound_order_created", quantity=1, unit_cost="NaN", order_id="4"),
        ],
        dimensions=(("valencia", "b2b-sales"),),
    )

    reasons = {rejection.reason for rejection in validated.rejections}
    assert reasons == {
        "quantity_not_positive",
        "unit_cost_not_positive",
        "quantity_not_integer",
        "unit_cost_not_finite",
    }


def test_rejection_threshold_is_strictly_greater_than_five_percent():
    valid = [
        _row("outbound_order_created", quantity=1, order_id=str(index))
        for index in range(19)
    ]
    invalid = [
        _row("inbound_order_created", quantity=0, unit_cost="1.00", order_id="bad")
    ]
    second_invalid = [
        _row(
            "inbound_order_created",
            quantity=0,
            unit_cost="1.00",
            order_id="bad-2",
        )
    ]

    _, at_boundary = _assemble(
        valid + invalid, dimensions=(("valencia", "b2b-sales"),)
    )
    _, above_boundary = _assemble(
        valid + invalid + second_invalid, dimensions=(("valencia", "b2b-sales"),)
    )

    assert at_boundary.reconciliation["rejection_rate"] == "0.0500"
    assert at_boundary.publication_blocked is False
    assert above_boundary.publication_blocked is True
    assert "rejection_threshold_exceeded" in above_boundary.block_reasons


# ---------------------------------------------------------------------------
# Assembly, zero-fill, and reconciliation
# ---------------------------------------------------------------------------


def test_cost_rounds_half_up_to_two_decimal_places():
    _, assembled = _assemble(
        [_row("inbound_order_created", quantity=1, unit_cost="0.005", order_id="1")],
        dimensions=(("valencia", "b2b-sales"),),
    )

    assert _entry(assembled, "valencia", "b2b-sales")[
        "total_material_cost"
    ] == Decimal("0.01")


def test_zero_fill_uses_real_dimension_scaffold():
    _, assembled = _assemble(
        [_row("outbound_order_created", quantity=1, order_id="1")],
        dimensions=(
            ("valencia", "b2b-sales"),
            ("miami", "b2b-sales"),
            ("valencia", "basic-leadership"),
        ),
    )

    assert len(assembled.rows) == 3
    assert assembled.reconciliation["zero_filled_row_count"] == 2
    miami = _entry(assembled, "miami", "b2b-sales")
    assert miami["total_material_cost"] == Decimal("0.00")
    assert miami["kits_delivered_count"] == 0
    assert miami["currency"] == "USD"


def test_unknown_programme_slug_is_published_with_warning():
    _, assembled = _assemble(
        [
            _row(
                "outbound_order_created",
                programme="test-programme",
                quantity=1,
                order_id="1",
            )
        ],
        dimensions=(("valencia", "b2b-sales"),),
        known=("b2b-sales",),
    )

    assert _entry(assembled, "valencia", "test-programme")["kits_delivered_count"] == 1
    assert assembled.reconciliation["unknown_programme_ids"] == ["test-programme"]


def test_empty_source_week_with_valid_dimensions_yields_zero_rows():
    _, assembled = _assemble([], dimensions=DIMENSIONS)

    assert len(assembled.rows) == 2
    assert all(row["total_material_cost"] == Decimal("0.00") for row in assembled.rows)
    assert assembled.publication_blocked is False
    assert assembled.reconciliation["zero_filled_row_count"] == 2


def test_week_fingerprint_is_stable_for_identical_input():
    rows = [
        _row("outbound_order_created", quantity=1, order_id="1"),
        _row("inbound_order_created", quantity=2, unit_cost="3.00", order_id="2"),
    ]

    _, first = _assemble(rows, dimensions=(("valencia", "b2b-sales"),))
    _, second = _assemble(rows, dimensions=(("valencia", "b2b-sales"),))

    assert (
        first.reconciliation["week_fingerprint"]
        == second.reconciliation["week_fingerprint"]
    )


def test_week_fingerprint_changes_on_cost_only_change():
    original = [
        _row(
            "inbound_order_created",
            event_id="fixed-event-1",
            quantity=2,
            unit_cost="3.00",
            order_id="1",
        )
    ]
    repriced = [
        _row(
            "inbound_order_created",
            event_id="fixed-event-1",
            quantity=2,
            unit_cost="4.00",
            order_id="1",
        )
    ]

    _, first = _assemble(original, dimensions=(("valencia", "b2b-sales"),))
    _, second = _assemble(repriced, dimensions=(("valencia", "b2b-sales"),))

    assert (
        first.reconciliation["week_fingerprint"]
        != second.reconciliation["week_fingerprint"]
    )


def test_week_fingerprint_changes_on_count_only_change():
    original = [_row("outbound_order_created", quantity=1, order_id="1")]
    with_extra = [
        _row("outbound_order_created", quantity=1, order_id="1"),
        _row("outbound_order_created", quantity=1, order_id="2"),
    ]

    _, first = _assemble(original, dimensions=(("valencia", "b2b-sales"),))
    _, second = _assemble(with_extra, dimensions=(("valencia", "b2b-sales"),))

    assert (
        first.reconciliation["week_fingerprint"]
        != second.reconciliation["week_fingerprint"]
    )
