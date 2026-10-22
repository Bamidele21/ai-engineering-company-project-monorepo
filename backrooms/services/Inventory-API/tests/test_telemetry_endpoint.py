"""Contract tests for the Sprint 1 validating telemetry receiver."""

import logging
from uuid import uuid4


def _event(**overrides):
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


def test_valid_batch_is_accepted_and_counted(inventory_client):
	response = inventory_client.post(
		"/telemetry/events",
		json={"events": [_event(), _event(event_type="network_request_failed")]},
	)

	assert response.status_code == 200
	assert response.json() == {"received": 2}


def test_empty_batch_returns_zero(inventory_client):
	response = inventory_client.post("/telemetry/events", json={"events": []})

	assert response.status_code == 200
	assert response.json() == {"received": 0}


def test_missing_envelope_field_is_rejected(inventory_client):
	payload = _event()
	payload.pop("source")

	response = inventory_client.post("/telemetry/events", json={"events": [payload]})

	assert response.status_code == 422


def test_unexpected_envelope_field_is_rejected(inventory_client):
	response = inventory_client.post(
		"/telemetry/events",
		json={"events": [_event(extra_field=True)]},
	)

	assert response.status_code == 422


def test_invalid_event_type_shape_is_rejected(inventory_client):
	response = inventory_client.post(
		"/telemetry/events",
		json={"events": [_event(event_type="PageView")]},
	)

	assert response.status_code == 422


def test_invalid_uuid_is_rejected(inventory_client):
	response = inventory_client.post(
		"/telemetry/events",
		json={"events": [_event(sessionId="not-a-uuid")]},
	)

	assert response.status_code == 422


def test_receiver_logs_only_count_and_types(inventory_client, caplog):
	caplog.set_level(logging.INFO, logger="nexova.telemetry")

	response = inventory_client.post(
		"/telemetry/events",
		json={"events": [_event(), _event(event_type="validation_failed")]},
	)

	assert response.status_code == 200
	assert "count=2" in caplog.text
	assert "page_view" in caplog.text
	assert "validation_failed" in caplog.text
	assert "/inventory/products" not in caplog.text
