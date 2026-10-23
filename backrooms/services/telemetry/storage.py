"""Telemetry table definition, envelope-to-row mapping, and bulk insertion."""

import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import (
	Column,
	DateTime,
	JSON,
	MetaData,
	Numeric,
	String,
	Table,
	Text,
	Uuid,
	insert,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from .models import TelemetryEvent


telemetry_metadata = MetaData()

telemetry_events_table = Table(
	"telemetry_events",
	telemetry_metadata,
	Column("id", Uuid(as_uuid=True), primary_key=True),
	Column("timestamp", DateTime(timezone=True), nullable=False),
	Column("service", String, nullable=False),
	Column("event_type", String, nullable=False),
	Column("level", String, nullable=False, default="info"),
	Column("value", Numeric(18, 4), nullable=True),
	Column("message", Text, nullable=True),
	Column(
		"tags",
		JSONB().with_variant(JSON(), "sqlite"),
		nullable=False,
		default=dict,
	),
)

MIGRATION_PATH = (
	Path(__file__).resolve().parents[1]
	/ "Inventory-API"
	/ "migrations"
	/ "002_telemetry_events.sql"
)

EVENT_SERVICE_MAP = {
	"web": "backoffice",
	"inventory-api": "inventory-api",
	"supply-directory-api": "supply-directory-api",
	"analyzer-api": "analyzer-api",
}

ERROR_EVENTS = frozenset(
	{
		"frontend_error_captured",
		"network_request_failed",
		"login_failed",
		"password_reset_failed",
	}
)

WARN_EVENTS = frozenset(
	{
		"validation_failed",
		"outbound_order_rejected",
		"direct_stock_edit_rejected",
		"stock_threshold_triggered",
		"kit_cost_variance_detected",
		"session_expired",
	}
)

EVENT_VALUE_FIELDS = {
	"page_view": "load_duration_ms",
	"api_latency_recorded": "duration_ms",
	"incident_report_analyzed": "duration_ms",
	"kit_cost_variance_detected": "variance_percent",
	"stock_threshold_triggered": "quantity",
	"inbound_order_created": "quantity",
	"outbound_order_created": "quantity",
	"outbound_order_rejected": "quantity",
}

EMAIL_PATTERN = re.compile(
	r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE
)
URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)
SENSITIVE_QUERY_PATTERN = re.compile(
	r"([?&](?:token|next|email|password|reset_token)=)[^\s&#]+",
	re.IGNORECASE,
)


def sanitize_message(message: str) -> str:
	return SENSITIVE_QUERY_PATTERN.sub(
		r"\1[redacted]",
		URL_PATTERN.sub(
			"[url]",
			EMAIL_PATTERN.sub("[email]", message),
		),
	)[:300]


def level_for(event_type: str) -> str:
	if event_type in ERROR_EVENTS:
		return "error"
	if event_type in WARN_EVENTS:
		return "warn"
	return "info"


def _sanitized_properties(event: TelemetryEvent, message: str | None) -> dict:
	properties = dict(event.properties)
	for key in ("page_path", "referrer_path", "target"):
		value = properties.get(key)
		if isinstance(value, str):
			properties[key] = value.split("?")[0].split("#")[0]
	if event.event_type == "frontend_error_captured" and message is not None:
		properties["message"] = message
	return properties


def build_row(event: TelemetryEvent) -> dict[str, Any]:
	properties = dict(event.properties)
	value_field = EVENT_VALUE_FIELDS.get(event.event_type)
	raw_value = properties.get(value_field) if value_field else None
	message = None
	if event.event_type == "frontend_error_captured":
		message = sanitize_message(str(properties.get("message", ""))) or None

	return {
		"id": uuid4(),
		"timestamp": event.timestamp,
		"service": EVENT_SERVICE_MAP.get(event.source, event.source),
		"event_type": event.event_type,
		"level": level_for(event.event_type),
		"value": float(raw_value) if raw_value is not None else None,
		"message": message,
		"tags": {
			**_sanitized_properties(event, message),
			"_meta": {
				"eventId": event.eventId,
				"sessionId": event.sessionId,
				"userId": event.userId,
				"schemaVersion": event.schemaVersion,
				"requestId": event.requestId,
			},
		},
	}


def insert_rows(session: Any, rows: list[dict[str, Any]]) -> int:
	if not rows:
		return 0
	try:
		session.execute(insert(telemetry_events_table), rows)
		session.commit()
	except Exception:
		session.rollback()
		raise
	return len(rows)


def ensure_telemetry_table(engine: Engine) -> None:
	if engine.dialect.name == "postgresql":
		sql = MIGRATION_PATH.read_text(encoding="utf-8")
		with engine.begin() as connection:
			connection.exec_driver_sql(sql)
		return
	telemetry_metadata.create_all(engine)
