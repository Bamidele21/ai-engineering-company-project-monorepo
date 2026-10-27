"""Business reporting endpoints, kept separate from the telemetry module."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlmodel import Session

from database import get_sql_session
from services.Supply_directory_API.auth.dependencies import get_current_user
from services.Supply_directory_API.models import AuthenticatedUser

from . import service
from .models import (
    LatestRunResponse,
    TriggerRequest,
    TriggerResponse,
    WeeklyReportResponse,
)

router = APIRouter(prefix="/reporting", tags=["reporting"])


def require_manager_or_admin(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    if current_user.role not in ("manager", "admin"):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Manager or admin role required",
        )
    return current_user


@router.get(
    "/weekly-office-program-performance",
    response_model=WeeklyReportResponse,
)
def weekly_office_program_performance(
    week_start: date | None = Query(default=None),
    session: Session = Depends(get_sql_session),
    _: AuthenticatedUser = Depends(get_current_user),
) -> WeeklyReportResponse:
    return WeeklyReportResponse.model_validate(
        service.get_report(session, week_start)
    )


@router.get("/pipeline-runs/latest", response_model=LatestRunResponse)
def latest_pipeline_run(
    session: Session = Depends(get_sql_session),
    _: AuthenticatedUser = Depends(get_current_user),
) -> LatestRunResponse:
    return LatestRunResponse.model_validate(service.get_latest_run(session))


@router.post(
    "/pipeline-runs",
    response_model=TriggerResponse,
    status_code=http_status.HTTP_202_ACCEPTED,
)
def trigger_pipeline_run(
    request: TriggerRequest,
    session: Session = Depends(get_sql_session),
    current_user: AuthenticatedUser = Depends(require_manager_or_admin),
) -> TriggerResponse:
    return TriggerResponse.model_validate(
        service.trigger_run(
            session,
            week_start=request.week_start,
            weeks=request.weeks,
            requested_by=f"user:{current_user.id}",
        )
    )
