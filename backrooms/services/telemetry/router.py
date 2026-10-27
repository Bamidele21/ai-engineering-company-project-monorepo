"""Validating telemetry receiver used by Sprint 1.

No database access or persistence happens here. Sprint 2 replaces the internals
with per-event validation and a bulk Supabase insert while retaining this route.
"""

import logging

from fastapi import APIRouter

from .models import TelemetryBatch, TelemetryResponse

logger = logging.getLogger("nexova.telemetry")

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.post("/events", response_model=TelemetryResponse)
def receive_events(batch: TelemetryBatch) -> TelemetryResponse:
	logger.info(
		"telemetry batch received: count=%d types=%s",
		len(batch.events),
		[event.event_type for event in batch.events],
	)
	return TelemetryResponse(received=len(batch.events))
