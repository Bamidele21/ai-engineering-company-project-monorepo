"""Static catalogue and per-event validation for telemetry ingestion."""

from typing import Any

from .models import TelemetryEvent


class EventValidationError(ValueError):
	"""A syntactically valid envelope failed the event catalogue contract."""


def _spec(required: str, allowed: str, emitters: str, overrides=None) -> dict:
	return {
		"schema_version": "1.0",
		"required": frozenset(required.split()),
		"allowed": frozenset(allowed.split()),
		"emitters": frozenset(emitters.split()),
		"overrides": overrides or {},
	}


EVENT_SPECS = {
	"inbound_order_created": _spec(
		"office product_id product_category programme_id quantity currency "
		"supplier unit_cost order_id",
		"office product_id product_category programme_id quantity currency "
		"supplier unit_cost order_id",
		"inventory-api",
		{"quantity": {"minimum": 1}},
	),
	"outbound_order_created": _spec(
		"office product_id product_category programme_id quantity currency "
		"exit_type order_id",
		"office product_id product_category programme_id quantity currency "
		"exit_type order_id",
		"inventory-api",
		{"quantity": {"minimum": 1}},
	),
	"stock_threshold_triggered": _spec(
		"office product_id product_category programme_id quantity currency "
		"min_stock previous_stock",
		"office product_id product_category programme_id quantity currency "
		"min_stock previous_stock",
		"inventory-api",
	),
	"direct_stock_edit_rejected": _spec(
		"office product_id product_category programme_id quantity currency method path",
		"office product_id product_category programme_id quantity currency method path",
		"inventory-api",
		{"method": {"enum": ("PUT", "PATCH", "DELETE")}},
	),
	"kit_cost_variance_detected": _spec(
		"office product_id product_category programme_id quantity currency "
		"supplier unit_cost historical_avg_cost variance_percent order_id",
		"office product_id product_category programme_id quantity currency "
		"supplier unit_cost historical_avg_cost variance_percent order_id",
		"inventory-api",
		{"quantity": {"minimum": 1}},
	),
	"product_created": _spec(
		"office product_id product_category programme_id quantity currency sku min_stock",
		"office product_id product_category programme_id quantity currency sku min_stock",
		"inventory-api",
	),
	"outbound_order_rejected": _spec(
		"office product_id product_category programme_id quantity currency "
		"exit_type available_stock",
		"office product_id product_category programme_id quantity currency "
		"exit_type available_stock",
		"inventory-api",
		{"quantity": {"minimum": 1}},
	),
	"supplier_rate_edited": _spec(
		"supplier_id old_rate new_rate currency",
		"supplier_id old_rate new_rate currency",
		"supply-directory-api",
	),
	"incident_report_analyzed": _spec(
		"row_count valid_count duration_ms",
		"row_count valid_count duration_ms",
		"analyzer-api",
	),
	"login_succeeded": _spec("", "", "supply-directory-api"),
	"login_failed": _spec(
		"failure_reason", "failure_reason", "supply-directory-api"
	),
	"session_expired": _spec(
		"detected_by", "detected_by", "supply-directory-api web"
	),
	"password_reset_requested": _spec("", "", "supply-directory-api"),
	"password_reset_failed": _spec(
		"reason",
		"reason",
		"supply-directory-api",
		{
			"reason": {
				"enum": ("email_service_unavailable", "invalid_reset_token")
			}
		},
	),
	"user_registered": _spec("role", "role", "supply-directory-api"),
	"admin_role_changed": _spec(
		"target_user_id previous_role new_role",
		"target_user_id previous_role new_role",
		"supply-directory-api",
	),
	"page_view": _spec(
		"page_path",
		"page_path load_duration_ms referrer_path",
		"web",
	),
	"form_abandoned": _spec("flow_id page_path", "flow_id page_path", "web"),
	"api_latency_recorded": _spec(
		"service method path status_code duration_ms",
		"service method path status_code duration_ms",
		"inventory-api supply-directory-api analyzer-api",
		{
			"duration_ms": {"minimum": 500},
			"method": {"min_length": 1},
		},
	),
	"frontend_error_captured": _spec(
		"error_type message page_path source",
		"error_type message page_path source stack_frame",
		"web",
		{
			"source": {
				"enum": (
					"window_onerror",
					"unhandledrejection",
					"error_boundary",
				)
			}
		},
	),
	"network_request_failed": _spec(
		"target page_path", "target page_path", "web"
	),
	"validation_failed": _spec(
		"source context field reason",
		"source context field reason page_path",
		"web inventory-api",
		{
			"source": {"enum": ("client", "server")},
			"reason": {"min_length": 1},
		},
	),
}

PROPERTY_RULES = {
	"available_stock": {"types": ("integer",), "minimum": 0},
	"context": {"types": ("string",), "min_length": 1},
	"currency": {"types": ("string",), "enum": ("EUR", "USD")},
	"detected_by": {"types": ("string",), "enum": ("client", "server")},
	"duration_ms": {"types": ("integer",), "minimum": 0},
	"error_type": {"types": ("string",), "min_length": 1, "max_length": 200},
	"exit_type": {"types": ("string",), "enum": ("allocation", "consumption")},
	"failure_reason": {
		"types": ("string",),
		"enum": (
			"unknown_email",
			"wrong_password",
			"inactive_account",
			"corrupt_hash",
		),
	},
	"field": {"types": ("string",), "min_length": 1},
	"flow_id": {
		"types": ("string",),
		"enum": (
			"inbound_order_form",
			"outbound_order_form",
			"supplier_registration_form",
			"password_reset_flow",
		),
	},
	"historical_avg_cost": {"types": ("number",), "exclusive_minimum": 0},
	"load_duration_ms": {"types": ("integer",), "minimum": 0},
	"message": {"types": ("string",), "min_length": 1, "max_length": 300},
	"method": {"types": ("string",), "min_length": 1},
	"min_stock": {"types": ("integer",), "minimum": 0},
	"new_rate": {"types": ("number",), "exclusive_minimum": 0},
	"new_role": {"types": ("string",), "enum": ("admin", "manager", "user")},
	"office": {"types": ("string",), "enum": ("valencia", "miami")},
	"old_rate": {"types": ("number",), "exclusive_minimum": 0},
	"order_id": {"types": ("integer",), "minimum": 1},
	"page_path": {"types": ("string",), "min_length": 1},
	"path": {"types": ("string",), "min_length": 1},
	"previous_role": {
		"types": ("string",),
		"enum": ("admin", "manager", "user"),
	},
	"previous_stock": {"types": ("integer",), "minimum": 0},
	"product_category": {
		"types": ("string",),
		"enum": ("training_kit", "certification", "onboarding_equipment"),
	},
	"product_id": {"types": ("integer",), "minimum": 1},
	"programme_id": {"types": ("string",), "min_length": 1},
	"quantity": {"types": ("integer",), "minimum": 0},
	"reason": {"types": ("string",), "min_length": 1},
	"referrer_path": {"types": ("string",), "min_length": 1},
	"role": {"types": ("string",), "enum": ("admin", "manager", "user")},
	"row_count": {"types": ("integer",), "minimum": 0},
	"service": {
		"types": ("string",),
		"enum": ("inventory-api", "supply-directory-api", "analyzer-api"),
	},
	"sku": {"types": ("string",), "min_length": 1},
	"source": {"types": ("string",), "min_length": 1},
	"stack_frame": {"types": ("string",), "min_length": 1},
	"status_code": {"types": ("integer",), "minimum": 100, "maximum": 599},
	"supplier": {"types": ("string",), "min_length": 1},
	"supplier_id": {"types": ("integer",), "minimum": 1},
	"target": {"types": ("string",), "min_length": 1},
	"target_user_id": {"types": ("integer",), "minimum": 1},
	"unit_cost": {"types": ("number",), "exclusive_minimum": 0},
	"valid_count": {"types": ("integer",), "minimum": 0},
	"variance_percent": {"types": ("number",)},
}

NULLABLE_PROPERTIES = {
	"direct_stock_edit_rejected": frozenset(
		{
			"office",
			"product_id",
			"product_category",
			"programme_id",
			"quantity",
			"currency",
		}
	),
	"frontend_error_captured": frozenset({"stack_frame"}),
}


def _value_type_name(value: Any) -> str | None:
	if isinstance(value, bool):
		return "boolean"
	if isinstance(value, int):
		return "integer"
	if isinstance(value, float):
		return "number"
	if isinstance(value, str):
		return "string"
	if isinstance(value, list):
		return "array"
	if isinstance(value, dict):
		return "object"
	return None


def _validate_value(
	event_type: str,
	key: str,
	value: Any,
	rule: dict,
	nullable: frozenset[str],
) -> None:
	if value is None:
		if key in nullable:
			return
		raise EventValidationError(f"{event_type}.{key} must not be null")

	actual = _value_type_name(value)
	expected = rule.get("types", ("string",))
	if actual not in expected and not (actual == "integer" and "number" in expected):
		raise EventValidationError(
			f"{event_type}.{key} must be {' or '.join(expected)}, got {actual}"
		)

	enum = rule.get("enum")
	if enum is not None and value not in enum:
		raise EventValidationError(f"{event_type}.{key} is not an allowed value")

	minimum = rule.get("minimum")
	if minimum is not None and actual in ("integer", "number") and value < minimum:
		raise EventValidationError(f"{event_type}.{key} is below the minimum")

	maximum = rule.get("maximum")
	if maximum is not None and actual in ("integer", "number") and value > maximum:
		raise EventValidationError(f"{event_type}.{key} is above the maximum")

	exclusive_minimum = rule.get("exclusive_minimum")
	if (
		exclusive_minimum is not None
		and actual in ("integer", "number")
		and value <= exclusive_minimum
	):
		raise EventValidationError(
			f"{event_type}.{key} must be greater than {exclusive_minimum}"
		)

	if actual == "string":
		min_length = rule.get("min_length")
		if min_length is not None and len(value) < min_length:
			raise EventValidationError(f"{event_type}.{key} is too short")
		max_length = rule.get("max_length")
		if max_length is not None and len(value) > max_length:
			raise EventValidationError(f"{event_type}.{key} is too long")


def validate_event_payload(
	event_type: str,
	source: str,
	schema_version: str,
	properties: dict[str, Any],
) -> None:
	spec = EVENT_SPECS.get(event_type)
	if spec is None:
		raise EventValidationError(f"Unsupported event type: {event_type}")
	if schema_version != spec["schema_version"]:
		raise EventValidationError(
			f"Unsupported schemaVersion for {event_type}: {schema_version}"
		)
	if source not in spec["emitters"]:
		raise EventValidationError(f"Source {source} cannot emit {event_type}")

	keys = set(properties)
	unexpected = keys - spec["allowed"]
	if unexpected:
		raise EventValidationError(
			f"Unexpected properties for {event_type}: {sorted(unexpected)}"
		)

	missing = spec["required"] - keys
	if missing:
		raise EventValidationError(
			f"Missing properties for {event_type}: {sorted(missing)}"
		)

	nullable = NULLABLE_PROPERTIES.get(event_type, frozenset())
	for key, value in properties.items():
		rule = dict(PROPERTY_RULES[key])
		rule.update(spec["overrides"].get(key, {}))
		_validate_value(event_type, key, value, rule, nullable)


def validate_event(event: TelemetryEvent) -> None:
	validate_event_payload(
		event.event_type,
		event.source,
		event.schemaVersion,
		event.properties,
	)
