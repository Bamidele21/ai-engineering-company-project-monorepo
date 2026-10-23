"""Telemetry ingestion and technical report endpoints."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from database import get_sql_session
from services.cache import TtlCache

from . import analysis
from .catalog import EventValidationError, validate_event
from .constants import (
	REPORT_CACHE_TTL_SECONDS,
	REPORT_DEFAULT_WINDOW_DAYS,
)
from .models import (
	ReportPeriod,
	TelemetryBatch,
	TelemetryEvent,
	TelemetryReportResponse,
	TelemetryResponse,
)
from .storage import build_row, insert_rows

logger = logging.getLogger("nexova.telemetry")

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

_report_cache = TtlCache()
_default_period_cache = TtlCache()


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


def _parse_bound(value: str, label: str) -> datetime:
	try:
		parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
	except ValueError as error:
		raise HTTPException(
			status_code=422, detail=f"Invalid ISO 8601 {label}"
		) from error

	if parsed.tzinfo is None:
		parsed = parsed.replace(tzinfo=timezone.utc)
	return parsed.astimezone(timezone.utc)


def _resolve_period(
	start_date: str | None,
	end_date: str | None,
) -> tuple[datetime, datetime]:
	"""Resolve one UTC window to share across every metric function."""
	if start_date is None and end_date is None:
		cached = _default_period_cache.get("default")
		if cached is None:
			end = datetime.now(timezone.utc)
			cached = (
				end - timedelta(days=REPORT_DEFAULT_WINDOW_DAYS),
				end,
			)
			_default_period_cache.set(
				"default", cached, REPORT_CACHE_TTL_SECONDS
			)
		return cached

	if start_date is None:
		end = _parse_bound(end_date, "end_date")
		return end - timedelta(days=REPORT_DEFAULT_WINDOW_DAYS), end

	if end_date is None:
		start = _parse_bound(start_date, "start_date")
		return start, start + timedelta(days=REPORT_DEFAULT_WINDOW_DAYS)

	start = _parse_bound(start_date, "start_date")
	end = _parse_bound(end_date, "end_date")
	return start, end


def _iso_utc(value: datetime) -> str:
	return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@router.get("/report", response_model=TelemetryReportResponse)
def telemetry_report(
	start_date: str | None = Query(default=None),
	end_date: str | None = Query(default=None),
	session: Session = Depends(get_sql_session),
) -> TelemetryReportResponse:
	start, end = _resolve_period(start_date, end_date)
	if start >= end:
		raise HTTPException(
			status_code=422,
			detail="start_date must be before end_date",
		)

	cache_key = f"report:{start.isoformat()}|{end.isoformat()}"
	cached = _report_cache.get(cache_key)
	if cached is not None:
		return cached

	engine = session.get_bind()
	try:
		metrics = {
			"events_per_day": analysis.events_per_day(engine, start, end),
			"error_rate_by_type": analysis.error_rate_by_type(
				engine, start, end
			),
			"page_load_latency_by_day": analysis.page_load_latency_by_day(
				engine, start, end
			),
		}
	except SQLAlchemyError as error:
		logger.error(
			"telemetry report query failed: %s", type(error).__name__
		)
		raise HTTPException(
			status_code=503, detail="Telemetry report unavailable"
		) from error

	report = TelemetryReportResponse(
		period=ReportPeriod(
			start=_iso_utc(start),
			end=_iso_utc(end),
		),
		metrics=metrics,
	)
	_report_cache.set(cache_key, report, REPORT_CACHE_TTL_SECONDS)
	return report
