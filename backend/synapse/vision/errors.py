from __future__ import annotations

from typing import Any

from synapse.core.exceptions import NotFound, PermissionDenied, ValidationError


class VisionErrorMixin(Exception):
    code: str
    status_code: int = 400
    details: dict[str, Any]

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "details": self.details}


class InvalidImage(VisionErrorMixin, ValidationError):
    code = "invalid_image"
    status_code = 422


class UnsupportedImageFormat(InvalidImage):
    code = "unsupported_image_format"


class VisionProviderNotFound(VisionErrorMixin, NotFound):
    code = "vision_provider_not_found"
    status_code = 404


class VisionProviderUnavailable(VisionErrorMixin, ValidationError):
    code = "vision_provider_unavailable"
    status_code = 503


class VisionAnalysisFailed(VisionErrorMixin, ValidationError):
    code = "vision_analysis_failed"
    status_code = 422


class ScreenshotPermissionDenied(VisionErrorMixin, PermissionDenied):
    code = "screenshot_permission_denied"
    status_code = 403


class CaptureSourceNotFound(VisionErrorMixin, NotFound):
    code = "capture_source_not_found"
    status_code = 404


class CameraNotFound(VisionErrorMixin, NotFound):
    code = "camera_not_found"
    status_code = 404


class CameraUnavailable(VisionErrorMixin, ValidationError):
    code = "camera_unavailable"
    status_code = 503


class CameraPermissionDenied(VisionErrorMixin, PermissionDenied):
    code = "camera_permission_denied"
    status_code = 403


class OCRUnavailable(VisionErrorMixin, ValidationError):
    code = "ocr_unavailable"
    status_code = 503
