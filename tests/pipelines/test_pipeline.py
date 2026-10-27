"""Isolated transformation tests for the Nexova weekly performance KPIs.

These tests are in-memory and require no database, network, Prefect server, or
secrets. They assert the four briefing KPIs against hand-calculated inputs.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from data.process.weekly_performance import transform_week

WEEK = date(2026, 10, 19)
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


def _run(
    rows,
    *,
    dimensions=(("valencia", "b2b-sales"), ("miami", "b2b-sales")),
    known=("b2b-sales",),
    threshold=Decimal("0.05"),
):
    return transform_week(
        rows,
        week_start=WEEK,
        dimension_pairs=dimensions,
        known_programmes=known,
        rejection_threshold=threshold,
    )


def _entry(result, office: str, programme: str) -> dict:
    return next(
        row
        for row in result.rows
        if row["office"] == office and row["programme_id"] == programme
    )


def test_total_material_cost_uses_quantity_and_decimal_cost():
    result = _run(
        [
            _row(
                "inbound_order_created",
                quantity=3,
                unit_cost="12.50",
                order_id="1",
            ),
            _row(
                "inbound_order_created",
                quantity=2,
                unit_cost="5.25",
                order_id="2",
            ),
            _row(
                "kit_cost_variance_detected",
                quantity=4,
                unit_cost="99.99",
                order_id="3",
            ),
        ],
        dimensions=(("valencia", "b2b-sales"),),
    )

    row = _entry(result, "valencia", "b2b-sales")
    assert row["total_material_cost"] == Decimal("48.00")
    assert row["currency"] == "EUR"
    assert row["cost_variance_events_count"] == 1


def test_kits_delivered_counts_events_not_units():
    result = _run(
        [
            _row("outbound_order_created", quantity=10, order_id="1"),
            _row("outbound_order_created", quantity=2, order_id="2"),
        ],
        dimensions=(("valencia", "b2b-sales"),),
    )

    assert _entry(result, "valencia", "b2b-sales")["kits_delivered_count"] == 2


def test_shortage_frequency_counts_captured_threshold_events():
    result = _run(
        [
            _row("stock_threshold_triggered", quantity=0, extra={"min_stock": 10}),
            _row("stock_threshold_triggered", quantity=5, extra={"min_stock": 10}),
        ],
        dimensions=(("valencia", "b2b-sales"),),
    )

    assert (
        _entry(result, "valencia", "b2b-sales")["shortage_events_count"] == 2
    )


def test_cost_variance_frequency_counts_alerts():
    result = _run(
        [
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
        ],
        dimensions=(("valencia", "b2b-sales"),),
    )

    row = _entry(result, "valencia", "b2b-sales")
    assert row["cost_variance_events_count"] == 2
    assert row["total_material_cost"] == Decimal("0.00")


def test_cost_rounds_half_up_to_two_decimal_places():
    result = _run(
        [_row("inbound_order_created", quantity=1, unit_cost="0.005", order_id="1")],
        dimensions=(("valencia", "b2b-sales"),),
    )

    assert _entry(result, "valencia", "b2b-sales")["total_material_cost"] == Decimal(
        "0.01"
    )


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

    result = _run([later, earlier], dimensions=(("valencia", "b2b-sales"),))

    assert result.records_extracted == 2
    assert result.records_deduplicated == 1
    assert result.reconciliation["duplicate_count"] == 1
    assert result.reconciliation["duplicate_payload_conflict_count"] == 1
    assert _entry(result, "valencia", "b2b-sales")["total_material_cost"] == Decimal(
        "10.00"
    )


def test_missing_event_id_falls_back_to_source_row_id():
    first = _row("inbound_order_created", event_id=None, quantity=1, unit_cost="1.00")
    second = _row("inbound_order_created", event_id=None, quantity=1, unit_cost="2.00")

    result = _run([first, second], dimensions=(("valencia", "b2b-sales"),))

    assert result.records_extracted == 2
    assert result.records_deduplicated == 2
    assert _entry(result, "valencia", "b2b-sales")["total_material_cost"] == Decimal(
        "3.00"
    )


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

    result = _run([sunday, monday], dimensions=(("valencia", "b2b-sales"),))

    assert [rejection.reason for rejection in result.rejections] == [
        "week_out_of_range"
    ]
    assert _entry(result, "valencia", "b2b-sales")["total_material_cost"] == Decimal(
        "7.00"
    )


def test_currency_office_mismatch_is_rejected_not_converted():
    result = _run(
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

    assert [rejection.reason for rejection in result.rejections] == [
        "currency_office_mismatch"
    ]
    assert result.publication_blocked is True
    assert "rejection_threshold_exceeded" in result.block_reasons


def test_malformed_quantity_and_cost_are_rejected():
    rows = [
        _row("inbound_order_created", quantity=0, unit_cost="1.00", order_id="1"),
        _row("inbound_order_created", quantity=1, unit_cost="0", order_id="2"),
        _row("inbound_order_created", quantity="abc", unit_cost="1.00", order_id="3"),
        _row("inbound_order_created", quantity=1, unit_cost="NaN", order_id="4"),
    ]

    result = _run(rows, dimensions=(("valencia", "b2b-sales"),))

    reasons = {rejection.reason for rejection in result.rejections}
    assert reasons == {
        "quantity_not_positive",
        "unit_cost_not_positive",
        "quantity_not_integer",
        "unit_cost_not_finite",
    }
    assert result.publication_blocked is True


def test_schema_version_and_service_are_rejected():
    result = _run(
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

    reasons = {rejection.reason for rejection in result.rejections}
    assert reasons == {"schema_version_not_supported", "service_not_allowed"}


def test_zero_fill_uses_real_dimension_scaffold():
    result = _run(
        [_row("outbound_order_created", quantity=1, order_id="1")],
        dimensions=(
            ("valencia", "b2b-sales"),
            ("miami", "b2b-sales"),
            ("valencia", "basic-leadership"),
        ),
    )

    assert len(result.rows) == 3
    assert result.reconciliation["zero_filled_row_count"] == 2
    miami = _entry(result, "miami", "b2b-sales")
    assert miami["total_material_cost"] == Decimal("0.00")
    assert miami["kits_delivered_count"] == 0
    assert miami["currency"] == "USD"


def test_unknown_programme_slug_is_published_with_warning():
    result = _run(
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

    assert _entry(result, "valencia", "test-programme")["kits_delivered_count"] == 1
    assert result.reconciliation["unknown_programme_ids"] == ["test-programme"]


def test_empty_source_week_with_valid_dimensions_yields_zero_rows():
    result = _run(
        [],
        dimensions=(("valencia", "b2b-sales"), ("miami", "b2b-sales")),
    )

    assert len(result.rows) == 2
    assert all(row["total_material_cost"] == Decimal("0.00") for row in result.rows)
    assert result.publication_blocked is False
    assert result.reconciliation["zero_filled_row_count"] == 2


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

    at_boundary = _run(
        valid + invalid, dimensions=(("valencia", "b2b-sales"),)
    )
    above_boundary = _run(
        valid + invalid + second_invalid,
        dimensions=(("valencia", "b2b-sales"),),
    )

    assert at_boundary.reconciliation["rejection_rate"] == "0.0500"
    assert at_boundary.publication_blocked is False
    assert above_boundary.publication_blocked is True
    assert "rejection_threshold_exceeded" in above_boundary.block_reasons


def test_week_fingerprint_is_stable_for_identical_input():
    rows = [
        _row("outbound_order_created", quantity=1, order_id="1"),
        _row("inbound_order_created", quantity=2, unit_cost="3.00", order_id="2"),
    ]

    first = _run(rows, dimensions=(("valencia", "b2b-sales"),))
    second = _run(rows, dimensions=(("valencia", "b2b-sales"),))

    assert (
        first.reconciliation["week_fingerprint"]
        == second.reconciliation["week_fingerprint"]
    )
