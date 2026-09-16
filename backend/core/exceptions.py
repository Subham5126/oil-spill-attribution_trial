"""OilTrace Custom Exception Hierarchy.

Defines domain-specific errors mapped to clean HTTP responses without leaking tracebacks.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class OilTraceException(Exception):
    """Base exception for all OilTrace domain errors."""

    status_code: int = 500
    error_code: str = "INTERNAL_SERVER_ERROR"

    def __init__(
        self,
        message: str,
        stage: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status_code: Optional[int] = None,
    ):
        super().__init__(message)
        self.message = message
        self.stage = stage
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "status": "FAILED",
            "error_code": self.error_code,
            "message": self.message,
        }
        if self.stage:
            d["stage"] = self.stage
        if self.details:
            d["details"] = self.details
        return d


class InvestigationNotFoundError(OilTraceException):
    status_code = 404
    error_code = "INVESTIGATION_NOT_FOUND"


class SpillNotFoundError(OilTraceException):
    status_code = 404
    error_code = "SPILL_NOT_FOUND"


class VesselNotFoundError(OilTraceException):
    status_code = 404
    error_code = "VESSEL_NOT_FOUND"


class ReportNotFoundError(OilTraceException):
    status_code = 404
    error_code = "REPORT_NOT_FOUND"


class PipelineExecutionError(OilTraceException):
    status_code = 500
    error_code = "PIPELINE_EXECUTION_ERROR"


class ExternalServiceUnavailableError(OilTraceException):
    status_code = 503
    error_code = "SERVICE_UNAVAILABLE"


class InvalidRequestError(OilTraceException):
    status_code = 400
    error_code = "INVALID_REQUEST"
