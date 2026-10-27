"""Typed errors shared by the ETL, API, and tests."""


class PipelineError(Exception):
    """Base class for expected, sanitized pipeline failures."""

    code = "pipeline_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code:
            self.code = code


class InvalidWeekError(PipelineError):
    code = "invalid_week"


class InvalidRangeError(PipelineError):
    code = "invalid_range"


class NoReportFoundError(PipelineError):
    code = "report_not_found"


class NoRunFoundError(PipelineError):
    code = "run_not_found"


class ActiveRunExistsError(PipelineError):
    code = "active_run_exists"


class DispatchError(PipelineError):
    code = "dispatch_failed"


class PublicationBlockedError(PipelineError):
    code = "publication_blocked"


class SchemaUnavailableError(PipelineError):
    code = "database_unavailable"


class DimensionUnavailableError(PipelineError):
    code = "dimension_unavailable"
