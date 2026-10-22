import time

import pytest

from services.telemetry.emitter import (
	TelemetryQueue,
	build_event,
	emit_inventory_event,
)


REQUEST_ID = "7b3e1f2a-9c4d-4e5f-8a6b-2c0d1e3f4a5b"
SESSION_ID = "9a1b2c3d-4e5f-4a6b-8c9d-0e1f2a3b4c5d"


def inbound_properties(**overrides):
	properties = {
		"office": "valencia",
		"product_id": 4,
		"product_category": "training_kit",
		"programme_id": "b2b-sales",
		"quantity": 40,
		"currency": "EUR",
		"supplier": "PrintWorks Valencia S.L.",
		"unit_cost": 12.5,
		"order_id": 118,
	}
	properties.update(overrides)
	return properties


class FakeRequest:
	def __init__(self, headers=None):
		self.headers = headers or {}


def test_build_event_produces_the_standard_envelope():
	event = build_event(
		"inbound_order_created",
		inbound_properties(),
		user_id=3,
		request_id=REQUEST_ID,
		session_id=SESSION_ID,
	)

	assert event["event_type"] == "inbound_order_created"
	assert event["source"] == "inventory-api"
	assert event["schemaVersion"] == "1.0"
	assert event["userId"] == "3"
	assert event["requestId"] == REQUEST_ID
	assert event["sessionId"] == SESSION_ID
	assert event["timestamp"].endswith("Z")
	assert event["properties"]["unit_cost"] == 12.5


def test_build_event_rejects_properties_outside_the_allowlist():
	with pytest.raises(ValueError, match="Unexpected properties"):
		build_event("inbound_order_created", inbound_properties(assigned_to="Ana"))


def test_build_event_rejects_missing_required_properties():
	properties = inbound_properties()
	properties.pop("currency")
	with pytest.raises(ValueError, match="Missing properties"):
		build_event("inbound_order_created", properties)


def test_direct_edit_event_allows_unresolved_dimensions_to_be_null():
	event = build_event(
		"direct_stock_edit_rejected",
		{
			"office": None,
			"product_id": None,
			"product_category": None,
			"programme_id": None,
			"quantity": None,
			"currency": None,
			"method": "DELETE",
			"path": "/inventory/products",
		},
	)

	assert event["properties"]["quantity"] is None
	assert event["properties"]["method"] == "DELETE"


def test_emit_inventory_event_adopts_correlation_headers():
	captured = []
	queue = TelemetryQueue(
		captured.append,
		run_in_background=False,
		retry_delays=(),
	)
	request = FakeRequest(
		{"X-Request-Id": REQUEST_ID, "X-Session-Id": SESSION_ID}
	)

	event = emit_inventory_event(
		"inbound_order_created",
		inbound_properties(),
		request=request,
		user_id=3,
		queue=queue,
	)
	queue.flush_now()

	assert event["requestId"] == REQUEST_ID
	assert event["sessionId"] == SESSION_ID
	assert captured[0][0]["eventId"] == event["eventId"]


def test_invalid_correlation_headers_are_replaced():
	queue = TelemetryQueue(
		lambda _batch: None,
		run_in_background=False,
		retry_delays=(),
	)
	request = FakeRequest({"X-Request-Id": "not-a-uuid", "X-Session-Id": "nope"})

	event = emit_inventory_event(
		"inbound_order_created",
		inbound_properties(),
		request=request,
		queue=queue,
	)

	assert event["requestId"] != "not-a-uuid"
	assert event["sessionId"] != "nope"
	assert len(event["sessionId"]) == 36


def test_queue_flushes_at_the_batch_threshold():
	captured = []
	queue = TelemetryQueue(
		captured.append,
		batch_size=2,
		run_in_background=False,
		retry_delays=(),
	)
	event = build_event("inbound_order_created", inbound_properties())

	queue.add(event)
	assert captured == []
	assert queue.pending_count() == 1

	queue.add(build_event("inbound_order_created", inbound_properties()))
	assert len(captured) == 1
	assert len(captured[0]) == 2
	assert queue.pending_count() == 0


def test_queue_flushes_after_the_first_pending_interval():
	captured = []
	queue = TelemetryQueue(
		captured.append,
		flush_interval=0.01,
		run_in_background=False,
		retry_delays=(),
	)

	queue.add(build_event("inbound_order_created", inbound_properties()))
	time.sleep(0.05)

	assert len(captured) == 1
	assert queue.pending_count() == 0


def test_queue_retries_with_the_same_event_ids_then_succeeds():
	attempts = []

	def flaky_sink(batch):
		attempts.append(batch)
		if len(attempts) < 3:
			raise RuntimeError("transport unavailable")

	queue = TelemetryQueue(
		flaky_sink,
		batch_size=1,
		run_in_background=False,
		retry_delays=(0, 0, 0),
	)
	event = build_event("inbound_order_created", inbound_properties())

	queue.add(event)

	assert len(attempts) == 3
	assert attempts[0][0]["eventId"] == event["eventId"]
	assert attempts[2][0]["eventId"] == event["eventId"]


def test_queue_discards_an_exhausted_batch_without_raising():
	attempts = []

	def failing_sink(_batch):
		attempts.append(True)
		raise RuntimeError("still unavailable")

	queue = TelemetryQueue(
		failing_sink,
		batch_size=1,
		run_in_background=False,
		retry_delays=(0, 0, 0),
	)

	queue.add(build_event("inbound_order_created", inbound_properties()))

	assert len(attempts) == 4
	assert queue.pending_count() == 0


def test_unknown_inventory_event_is_rejected():
	with pytest.raises(ValueError, match="Unsupported inventory telemetry event"):
		build_event("page_view", {"page_path": "/"})


def test_new_events_receive_unique_ids():
	first = build_event("inbound_order_created", inbound_properties())
	second = build_event("inbound_order_created", inbound_properties())

	assert first["eventId"] != second["eventId"]
