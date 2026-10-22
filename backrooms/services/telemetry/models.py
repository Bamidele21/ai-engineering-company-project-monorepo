"""Pydantic models for the telemetry envelope.

Sprint 1 validates the format only. Sprint 2 reuses ``TelemetryEvent`` unchanged
while adding per-event property validation and Supabase persistence.
"""

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


EventSource = Literal[
	"web",
	"inventory-api",
	"supply-directory-api",
	"analyzer-api",
]


def _validate_uuid(value: str) -> str:
	try:
		UUID(str(value))
	except (TypeError, ValueError) as error:
		raise ValueError("must be a UUID") from error
	return str(value)


class TelemetryEvent(BaseModel):
	model_config = ConfigDict(extra="forbid")

	eventId: str
	timestamp: datetime
	sessionId: str
	userId: str | None = None
	event_type: str = Field(pattern=r"^[a-z][a-z0-9]*(_[a-z][a-z0-9]*)+$")
	schemaVersion: str = Field(pattern=r"^\d+\.\d+$")
	requestId: str
	source: EventSource
	properties: dict[str, Any] = Field(default_factory=dict)

	@field_validator("eventId", "sessionId", "requestId")
	@classmethod
	def validate_uuid_fields(cls, value: str) -> str:
		return _validate_uuid(value)

	@field_validator("timestamp")
	@classmethod
	def validate_timestamp(cls, value: datetime) -> datetime:
		if value.tzinfo is None:
			raise ValueError("timestamp must include a timezone")
		return value.astimezone(timezone.utc)

	@field_validator("userId")
	@classmethod
	def validate_user_id(cls, value: str | None) -> str | None:
		if value is not None and not value.isdigit():
			raise ValueError("userId must be a stringified integer id or null")
		return value


class TelemetryBatch(BaseModel):
	model_config = ConfigDict(extra="forbid")

	events: list[TelemetryEvent] = Field(default_factory=list)


class TelemetryResponse(BaseModel):
	received: int
