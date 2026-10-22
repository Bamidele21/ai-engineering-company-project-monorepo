"""Storage and partial-validation contract tests for telemetry ingestion."""

import logging
from uuid import uuid4

from sqlalchemy import event, inspect, select
from sqlmodel import Session

import services.telemetry.router as telemetry_router_module
from services.telemetry.storage import telemetry_events_table


def _page_view(**overrides):
	event = {
		"eventId": str(uuid4()),
		"timestamp": "2026-10-21T10:00:00.000Z",
		"sessionId": str(uuid4()),
		"userId": "3",
		"event_type": "page_view",
		"schemaVersion": "1.0",
		"requestId": str(uuid4()),
		"source": "web",
		"properties": {"page_path": "/inventory/products"},
	}
	event.update(overrides)
	return event


def _inbound_event(**overrides):
	event = {
		"eventId": str(uuid4()),
		"timestamp": "2026-10-21T10:01:00.000Z",
		"sessionId": str(uuid4()),
		"userId": "3",
		"event_type": "inbound_order_created",
		"schemaVersion": "1.0",
		"requestId": str(uuid4()),
		"source": "inventory-api",
		"properties": {
			"office": "valencia",
			"product_id": 4,
			"product_category": "training_kit",
			"programme_id": "b2b-sales",
			"quantity": 40,
			"currency": "EUR",
			"supplier": "PrintWorks Valencia S.L.",
			"unit_cost": 12.5,
			"order_id": 118,
		},
	}
	event.update(overrides)
	return event


def _frontend_error(**overrides):
	event = {
		"eventId": str(uuid4()),
		"timestamp": "2026-10-21T10:02:00.000Z",
		"sessionId": str(uuid4()),
		"userId": "3",
		"event_type": "frontend_error_captured",
		"schemaVersion": "1.0",
		"requestId": str(uuid4()),
		"source": "web",
		"properties": {
			"error_type": "TypeError",
			"message": "Failed for elena@nexova.com at https://x.test/path",
			"page_path": "/inventory/products",
			"source": "window_onerror",
			"stack_frame": "inventory-products.tsx:104",
		},
	}
	event.update(overrides)
	return event


def _rows(sqlite_engine):
	with Session(sqlite_engine) as session:
		return session.execute(select(telemetry_events_table)).mappings().all()


def _post_batch(client, events):
	return client.post("/telemetry/events", json={"events": events})


def test_table_has_the_eight_contract_columns(inventory_client, sqlite_engine):
	columns = {column["name"] for column in inspect(sqlite_engine).get_columns(
		"telemetry_events"
	)}
	assert columns == {
		"id",
		"timestamp",
		"service",
		"event_type",
		"level",
		"value",
		"message",
		"tags",
	}


def test_valid_batch_is_stored_and_counted(inventory_client, sqlite_engine):
	response = _post_batch(
		inventory_client,
		[_page_view(), _inbound_event()],
	)

	assert response.status_code == 200
	assert response.json() == {"received": 2, "stored": 2, "rejected": 0}
	assert len(_rows(sqlite_engine)) == 2


def test_empty_batch_returns_zeroes(inventory_client, sqlite_engine):
	response = _post_batch(inventory_client, [])

	assert response.status_code == 200
	assert response.json() == {"received": 0, "stored": 0, "rejected": 0}
	assert _rows(sqlite_engine) == []


def test_mixed_batch_stores_valid_siblings_and_rejects_invalid_items(
	inventory_client, sqlite_engine
):
	invalid_missing_source = _page_view()
	invalid_missing_source.pop("source")

	response = _post_batch(
		inventory_client,
		[_page_view(), invalid_missing_source, "not-an-object", 42],
	)

	assert response.status_code == 200
	assert response.json() == {"received": 4, "stored": 1, "rejected": 3}
	assert len(_rows(sqlite_engine)) == 1


def test_missing_events_array_is_a_malformed_envelope(inventory_client):
	assert inventory_client.post("/telemetry/events", json={}).status_code == 422
	assert (
		inventory_client.post(
			"/telemetry/events", json={"events": "not-a-list"}
		).status_code
		== 422
	)


def test_unexpected_envelope_field_is_rejected(inventory_client):
	response = inventory_client.post(
		"/telemetry/events",
		json={"events": [_page_view()], "extra": True},
	)
	assert response.status_code == 422


def test_invalid_events_are_rejected_individually(inventory_client):
	invalid_uuid = _page_view(sessionId="not-a-uuid")
	unsupported_type = _page_view(event_type="not_a_catalogue_event")
	unsupported_source = _page_view(source="inventory-api")
	wrong_version = _page_view(schemaVersion="2.0")
	unexpected_property = _page_view(properties={"page_path": "/x", "email": "a@b.com"})
	wrong_type = _page_view(properties={"page_path": "/x", "load_duration_ms": "slow"})

	response = _post_batch(
		inventory_client,
		[
			invalid_uuid,
			unsupported_type,
			unsupported_source,
			wrong_version,
			unexpected_property,
			wrong_type,
		],
	)

	assert response.status_code == 200
	assert response.json() == {"received": 6, "stored": 0, "rejected": 6}


def test_all_invalid_batch_does_not_call_the_database(
	inventory_client, sqlite_engine
):
	response = _post_batch(inventory_client, [_page_view(sessionId="bad")])

	assert response.status_code == 200
	assert response.json() == {"received": 1, "stored": 0, "rejected": 1}
	assert _rows(sqlite_engine) == []


def test_page_view_mapping_and_reserved_metadata(inventory_client, sqlite_engine):
	event = _page_view(
		properties={"page_path": "/inventory/products", "load_duration_ms": 812}
	)
	response = _post_batch(inventory_client, [event])

	assert response.status_code == 200
	row = _rows(sqlite_engine)[0]
	assert row["service"] == "backoffice"
	assert row["event_type"] == "page_view"
	assert row["level"] == "info"
	assert float(row["value"]) == 812
	assert row["message"] is None
	assert row["tags"]["page_path"] == "/inventory/products"
	assert row["tags"]["_meta"]["eventId"] == event["eventId"]
	assert row["tags"]["_meta"]["sessionId"] == event["sessionId"]
	assert row["tags"]["_meta"]["userId"] == "3"
	assert row["tags"]["_meta"]["schemaVersion"] == "1.0"
	assert row["tags"]["_meta"]["requestId"] == event["requestId"]


def test_tags_strip_query_strings(inventory_client, sqlite_engine):
	event = _page_view(
		properties={"page_path": "/login?next=%2Finventory&token=secret"}
	)
	response = _post_batch(inventory_client, [event])

	assert response.status_code == 200
	assert _rows(sqlite_engine)[0]["tags"]["page_path"] == "/login"


def test_inventory_event_mapping_uses_api_service_and_quantity(
	inventory_client, sqlite_engine
):
	response = _post_batch(inventory_client, [_inbound_event()])

	assert response.status_code == 200
	row = _rows(sqlite_engine)[0]
	assert row["service"] == "inventory-api"
	assert row["level"] == "info"
	assert float(row["value"]) == 40
	assert row["tags"]["product_category"] == "training_kit"


def test_frontend_error_message_is_sanitised_and_level_is_error(
	inventory_client, sqlite_engine
):
	response = _post_batch(inventory_client, [_frontend_error()])

	assert response.status_code == 200
	row = _rows(sqlite_engine)[0]
	assert row["level"] == "error"
	assert row["message"] == "Failed for [email] at [url]"
	assert row["value"] is None
	assert row["tags"]["message"] == "Failed for [email] at [url]"


def test_validation_failure_is_warn_level(inventory_client, sqlite_engine):
	event = _page_view(
		event_type="validation_failed",
		properties={
			"source": "client",
			"context": "inbound_order_form",
			"field": "quantity",
			"reason": "quantity_gt_0",
			"page_path": "/inventory/orders/inbound",
		},
	)
	response = _post_batch(inventory_client, [event])

	assert response.status_code == 200
	assert _rows(sqlite_engine)[0]["level"] == "warn"


def test_duplicate_delivery_creates_duplicate_immutable_rows(
	inventory_client, sqlite_engine
):
	event = _page_view()
	response = _post_batch(inventory_client, [event, event])

	assert response.status_code == 200
	assert response.json() == {"received": 2, "stored": 2, "rejected": 0}
	rows = _rows(sqlite_engine)
	assert len(rows) == 2
	assert rows[0]["tags"]["_meta"]["eventId"] == rows[1]["tags"]["_meta"]["eventId"]


def test_database_failure_returns_503_and_rolls_back(
	inventory_client, sqlite_engine, monkeypatch
):
	def failing_insert(_session, _rows):
		raise RuntimeError("database unavailable")

	monkeypatch.setattr(telemetry_router_module, "insert_rows", failing_insert)

	response = _post_batch(inventory_client, [_page_view()])

	assert response.status_code == 503
	assert _rows(sqlite_engine) == []


def test_valid_batch_is_one_bulk_insert_statement(
	inventory_client, sqlite_engine
):
	statements = []

	def capture(_conn, _cursor, statement, _parameters, _context, _many):
		if statement.lstrip().upper().startswith(
			"INSERT INTO TELEMETRY_EVENTS"
		):
			statements.append(statement)

	event.listen(sqlite_engine, "before_cursor_execute", capture)
	try:
		response = _post_batch(
			inventory_client,
			[_page_view(), _page_view(), _inbound_event()],
		)
	finally:
		event.remove(sqlite_engine, "before_cursor_execute", capture)

	assert response.status_code == 200
	assert response.json()["stored"] == 3
	assert len(statements) == 1


def test_receiver_logs_counts_without_payloads(inventory_client, caplog):
	caplog.set_level(logging.INFO, logger="nexova.telemetry")

	response = _post_batch(inventory_client, [_page_view()])

	assert response.status_code == 200
	assert "received=1 stored=1 rejected=0" in caplog.text
	assert "/inventory/products" not in caplog.text
