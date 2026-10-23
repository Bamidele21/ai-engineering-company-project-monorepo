"""Catalogue parity and per-event validation tests."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from services.telemetry.catalog import (
	EVENT_SPECS,
	PROPERTY_RULES,
	EventValidationError,
	validate_event,
	validate_event_payload,
)
from services.telemetry.constants import EVENT_SCHEMA_VERSIONS
from services.telemetry.models import TelemetryEvent


REPO_ROOT = Path(__file__).resolve().parents[4]
SCHEMA_PATH = REPO_ROOT / "docs" / "telemetry" / "event-schemas.json"


def _event(event_type="page_view", source="web", properties=None, version="1.0"):
	return TelemetryEvent(
		eventId=str(uuid4()),
		timestamp="2026-10-21T10:00:00.000Z",
		sessionId=str(uuid4()),
		userId="3",
		event_type=event_type,
		schemaVersion=version,
		requestId=str(uuid4()),
		source=source,
		properties=properties if properties is not None else {"page_path": "/x"},
	)


def test_catalogue_matches_the_normative_schema():
	data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
	assert set(EVENT_SPECS) == set(data["events"])

	for event_type, schema in data["events"].items():
		spec = EVENT_SPECS[event_type]
		assert spec["schema_version"] == schema["schema_version"]
		assert EVENT_SCHEMA_VERSIONS[event_type] == spec["schema_version"]
		assert spec["required"] == set(schema["properties_schema"]["required"])
		assert spec["allowed"] == set(
			schema["properties_schema"]["properties"]
		)
		assert spec["emitters"] == set(schema["emitters"])
		for key in spec["allowed"]:
			assert key in PROPERTY_RULES


def test_valid_page_view_passes():
	validate_event(_event())


def test_extra_property_is_rejected():
	with pytest.raises(EventValidationError, match="Unexpected properties"):
		validate_event(_event(properties={"page_path": "/x", "email": "a@b.com"}))


def test_missing_required_property_is_rejected():
	with pytest.raises(EventValidationError, match="Missing properties"):
		validate_event(_event(properties={}))


def test_wrong_property_type_is_rejected():
	with pytest.raises(EventValidationError, match="must be integer"):
		validate_event(
			_event(properties={"page_path": "/x", "load_duration_ms": "slow"})
		)


def test_invalid_enum_is_rejected():
	with pytest.raises(EventValidationError, match="not an allowed value"):
		validate_event_payload(
			"inbound_order_created",
			"inventory-api",
			"1.0",
			{
				"office": "paris",
				"product_id": 4,
				"product_category": "training_kit",
				"programme_id": "b2b-sales",
				"quantity": 1,
				"currency": "EUR",
				"supplier": "PrintWorks",
				"unit_cost": 12.5,
				"order_id": 1,
			},
		)


def test_source_must_match_the_catalogue_emitters():
	with pytest.raises(EventValidationError, match="cannot emit"):
		validate_event(_event(source="inventory-api"))


def test_schema_version_must_match():
	with pytest.raises(EventValidationError, match="schemaVersion"):
		validate_event(_event(version="2.0"))


def test_unknown_event_type_is_rejected():
	with pytest.raises(EventValidationError, match="Unsupported event type"):
		validate_event(_event(event_type="unknown_event"))


def test_direct_edit_allows_nullable_unresolved_dimensions():
	validate_event_payload(
		"direct_stock_edit_rejected",
		"inventory-api",
		"1.0",
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


def test_direct_edit_method_is_restricted():
	with pytest.raises(EventValidationError, match="not an allowed value"):
		validate_event_payload(
			"direct_stock_edit_rejected",
			"inventory-api",
			"1.0",
			{
				"office": "valencia",
				"product_id": 1,
				"product_category": "certification",
				"programme_id": "b2b-sales",
				"quantity": None,
				"currency": "EUR",
				"method": "POST",
				"path": "/inventory/products/{id}",
			},
		)


def test_frontend_error_stack_frame_may_be_null():
	validate_event_payload(
		"frontend_error_captured",
		"web",
		"1.0",
		{
			"error_type": "TypeError",
			"message": "boom",
			"page_path": "/inventory",
			"source": "window_onerror",
			"stack_frame": None,
		},
	)


def test_api_latency_requires_at_least_500_ms():
	with pytest.raises(EventValidationError, match="below the minimum"):
		validate_event_payload(
			"api_latency_recorded",
			"inventory-api",
			"1.0",
			{
				"service": "inventory-api",
				"method": "GET",
				"path": "/inventory/orders",
				"status_code": 200,
				"duration_ms": 499,
			},
		)

	validate_event_payload(
		"api_latency_recorded",
		"inventory-api",
		"1.0",
		{
			"service": "inventory-api",
			"method": "GET",
			"path": "/inventory/orders",
			"status_code": 200,
			"duration_ms": 500,
		},
	)


def test_inbound_quantity_must_be_positive():
	properties = {
		"office": "valencia",
		"product_id": 4,
		"product_category": "training_kit",
		"programme_id": "b2b-sales",
		"quantity": 0,
		"currency": "EUR",
		"supplier": "PrintWorks",
		"unit_cost": 12.5,
		"order_id": 1,
	}
	with pytest.raises(EventValidationError, match="below the minimum"):
		validate_event_payload(
			"inbound_order_created", "inventory-api", "1.0", properties
		)
