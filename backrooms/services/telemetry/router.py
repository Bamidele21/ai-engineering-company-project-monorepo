"""Per-event validation and bulk persistence for telemetry batches."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlmodel import Session

from database import get_sql_session

from .catalog import EventValidationError, validate_event
from .models import TelemetryBatch, TelemetryEvent, TelemetryResponse
from .storage import build_row, insert_rows

logger = logging.getLogger("nexova.telemetry")

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.post("/events", response_model=TelemetryResponse)
def receive_events(
	batch: TelemetryBatch,
	session: Session = Depends(get_sql_session),
) -> TelemetryResponse:
	received = len(batch.events)
	rejected = 0
	rows = []

	for raw_event in batch.events:
		if not isinstance(raw_event, dict):
			rejected += 1
			continue
		try:
			event = TelemetryEvent.model_validate(raw_event)
			validate_event(event)
			rows.append(build_row(event))
		except (ValidationError, EventValidationError, TypeError, ValueError):
			rejected += 1

	stored = 0
	if rows:
		try:
			stored = insert_rows(session, rows)
		except Exception as error:
			session.rollback()
			logger.error(
				"telemetry bulk insert failed: %s", type(error).__name__
			)
			raise HTTPException(
				status_code=503, detail="Telemetry storage unavailable"
			)

	logger.info(
		"telemetry batch received=%d stored=%d rejected=%d",
		received,
		stored,
		rejected,
	)
	return TelemetryResponse(
		received=received,
		stored=stored,
		rejected=rejected,
	)
