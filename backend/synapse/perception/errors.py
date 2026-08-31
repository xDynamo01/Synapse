from __future__ import annotations

from typing import Any

from synapse.core.exceptions import NotFound, PermissionDenied, ValidationError


class PerceptionErrorMixin(Exception):
    code: str
    status_code: int = 400
    details: dict[str, Any]

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "details": self.details}


class PerceptionSignalInvalid(PerceptionErrorMixin, ValidationError):
    code = "perception_signal_invalid"
    status_code = 422


class PerceptionSignalDenied(PerceptionErrorMixin, PermissionDenied):
    code = "perception_signal_denied"
    status_code = 403


class PerceptionSignalDuplicate(PerceptionErrorMixin, ValidationError):
    code = "perception_signal_duplicate"
    status_code = 409


class ObservationNotFound(PerceptionErrorMixin, NotFound):
    code = "observation_not_found"
    status_code = 404


class ObservationExpired(PerceptionErrorMixin, ValidationError):
    code = "observation_expired"
    status_code = 410


class PerceptionConflictError(PerceptionErrorMixin, ValidationError):
    code = "perception_conflict"
    status_code = 409


class RetentionFailed(PerceptionErrorMixin, ValidationError):
    code = "retention_failed"
    status_code = 500
