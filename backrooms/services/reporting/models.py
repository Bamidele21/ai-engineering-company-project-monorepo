"""Pydantic contracts for the reporting endpoints."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, PlainSerializer

Money = Annotated[
    Decimal,
    PlainSerializer(lambda value: float(value), return_type=float, when_used="json"),
]
Office = Literal["valencia", "miami"]
Currency = Literal["EUR", "USD"]


class ReportEntry(BaseModel):
    office: Office
    programme_id: str
    total_material_cost: Money
    kits_delivered_count: int
    shortage_events_count: int
    cost_variance_events_count: int
    currency: Currency


class WeeklyReportResponse(BaseModel):
    week_start: date
    entries: list[ReportEntry]


class RunError(BaseModel):
    code: str | None = None
    message: str | None = None


class LatestRunResponse(BaseModel):
    run_id: str
    flow_run_id: str | None = None
    pipeline_name: str
    status: str
    trigger_type: str
    triggered_by: str | None = None
    target_weeks: list[str] = Field(default_factory=list)
    source_window_start: str | None = None
    source_window_end: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    heartbeat_at: str | None = None
    checkpoint_stage: str | None = None
    checkpoint_week: str | None = None
    records_extracted: int
    records_deduplicated: int
    records_rejected: int
    records_loaded: int
    source_event_counts: dict[str, Any] = Field(default_factory=dict)
    office_counts: dict[str, Any] = Field(default_factory=dict)
    reconciliation: dict[str, Any] = Field(default_factory=dict)
    supersedes_run_id: str | None = None
    retry_count: int = 0
    created_at: str | None = None
    error: RunError | None = None


class TriggerRequest(BaseModel):
    week_start: date | None = None
    weeks: int = Field(default=1, ge=1, le=52)


class TriggerResponse(BaseModel):
    run_id: str
    status: str
    target_weeks: list[str]
