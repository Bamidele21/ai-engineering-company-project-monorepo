"""Shared telemetry contract constants for the Nexova event catalogue."""

from typing import Final

SCHEMA_VERSION: Final = "1.0"
INVENTORY_SOURCE: Final = "inventory-api"
REPORT_CACHE_TTL_SECONDS: Final = 60
REPORT_DEFAULT_WINDOW_DAYS: Final = 7

OFFICE_CURRENCY: Final = {"valencia": "EUR", "miami": "USD"}

CATEGORY_ALIASES: Final = {
	"hardware": "onboarding_equipment",
	"peripherals": "onboarding_equipment",
	"office_supplies": "onboarding_equipment",
	"training_materials": "training_kit",
	"training_kit": "training_kit",
	"certification": "certification",
	"onboarding_equipment": "onboarding_equipment",
}

EVENT_SCHEMA_VERSIONS: Final = {
	"inbound_order_created": "1.0",
	"outbound_order_created": "1.0",
	"stock_threshold_triggered": "1.0",
	"direct_stock_edit_rejected": "1.0",
	"kit_cost_variance_detected": "1.0",
	"product_created": "1.0",
	"outbound_order_rejected": "1.0",
	"supplier_rate_edited": "1.0",
	"incident_report_analyzed": "1.0",
	"login_succeeded": "1.0",
	"login_failed": "1.0",
	"session_expired": "1.0",
	"password_reset_requested": "1.0",
	"password_reset_failed": "1.0",
	"user_registered": "1.0",
	"admin_role_changed": "1.0",
	"page_view": "1.0",
	"form_abandoned": "1.0",
	"api_latency_recorded": "1.0",
	"frontend_error_captured": "1.0",
	"network_request_failed": "1.0",
	"validation_failed": "1.0",
}

EVENT_PROPERTY_ALLOWLISTS: Final = {
	"inbound_order_created": frozenset(
		{
			"office",
			"product_id",
			"product_category",
			"programme_id",
			"quantity",
			"currency",
			"supplier",
			"unit_cost",
			"order_id",
		}
	),
	"outbound_order_created": frozenset(
		{
			"office",
			"product_id",
			"product_category",
			"programme_id",
			"quantity",
			"currency",
			"exit_type",
			"order_id",
		}
	),
	"stock_threshold_triggered": frozenset(
		{
			"office",
			"product_id",
			"product_category",
			"programme_id",
			"quantity",
			"currency",
			"min_stock",
			"previous_stock",
		}
	),
	"direct_stock_edit_rejected": frozenset(
		{
			"office",
			"product_id",
			"product_category",
			"programme_id",
			"quantity",
			"currency",
			"method",
			"path",
		}
	),
	"kit_cost_variance_detected": frozenset(
		{
			"office",
			"product_id",
			"product_category",
			"programme_id",
			"quantity",
			"currency",
			"supplier",
			"unit_cost",
			"historical_avg_cost",
			"variance_percent",
			"order_id",
		}
	),
	"outbound_order_rejected": frozenset(
		{
			"office",
			"product_id",
			"product_category",
			"programme_id",
			"quantity",
			"currency",
			"exit_type",
			"available_stock",
		}
	),
}

EVENT_REQUIRED_PROPERTIES: Final = {
	"inbound_order_created": frozenset(
		{
			"office",
			"product_id",
			"product_category",
			"programme_id",
			"quantity",
			"currency",
			"supplier",
			"unit_cost",
			"order_id",
		}
	),
	"outbound_order_created": frozenset(
		{
			"office",
			"product_id",
			"product_category",
			"programme_id",
			"quantity",
			"currency",
			"exit_type",
			"order_id",
		}
	),
	"stock_threshold_triggered": frozenset(
		{
			"office",
			"product_id",
			"product_category",
			"programme_id",
			"quantity",
			"currency",
			"min_stock",
			"previous_stock",
		}
	),
	"direct_stock_edit_rejected": frozenset(
		{
			"office",
			"product_id",
			"product_category",
			"programme_id",
			"quantity",
			"currency",
			"method",
			"path",
		}
	),
	"kit_cost_variance_detected": frozenset(
		{
			"office",
			"product_id",
			"product_category",
			"programme_id",
			"quantity",
			"currency",
			"supplier",
			"unit_cost",
			"historical_avg_cost",
			"variance_percent",
			"order_id",
		}
	),
	"outbound_order_rejected": frozenset(
		{
			"office",
			"product_id",
			"product_category",
			"programme_id",
			"quantity",
			"currency",
			"exit_type",
			"available_stock",
		}
	),
}

NON_NULL_MANDATORY_PROPERTIES: Final = frozenset(
	{
		"office",
		"product_category",
		"programme_id",
		"currency",
	}
)


def lower_office(office: str) -> str:
	return office.strip().lower()


def currency_for_office(office: str) -> str:
	return OFFICE_CURRENCY[lower_office(office)]


def normalize_category(category: str) -> str:
	return CATEGORY_ALIASES.get(category, category)
