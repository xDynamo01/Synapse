from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

VISION_SESSION_STATUSES = {"idle", "observing", "paused", "closed", "failed"}
VISION_SOURCE_TYPES = {"uploaded_image", "screenshot", "camera"}
SUPPORTED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
VisionSessionStatus = str


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class VisionSession:
    session_id: str = field(default_factory=lambda: str(uuid4()))
    multimodal_session_id: str | None = None
    agent_id: str | None = None
    status: VisionSessionStatus = "idle"
    camera_device_id: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaptureSource:
    id: str
    source_type: str
    label: str
    available: bool
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CameraDevice:
    device_id: str
    name: str
    enabled: bool = False
    status: str = "not_configured"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VisionInput:
    image_reference: str
    mime: str
    dimensions: dict[str, int]
    checksum: str
    source_type: str
    owner: str
    id: str = field(default_factory=lambda: str(uuid4()))
    captured_at: str = field(default_factory=now_iso)
    policy_context: dict[str, Any] = field(default_factory=dict)
    sensitivity: str = "sensitive"
    expires_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    retention_class: str = "transient_only"
    persisted: bool = False
    provenance: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class VisionObject:
    label: str
    confidence: float | None = None
    region: dict[str, int] | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OCRBlock:
    text: str
    bounding_box: dict[str, int] | None = None
    confidence: float | None = None
    language: str | None = None


@dataclass(frozen=True)
class OCRResult:
    text: str | None
    blocks: list[OCRBlock]
    confidence: float | None
    language: str | None
    provider: str | None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VisionResult:
    input_id: str
    observations: list[dict[str, Any]]
    id: str = field(default_factory=lambda: str(uuid4()))
    detected_text: str | None = None
    objects: list[VisionObject] = field(default_factory=list)
    regions: list[dict[str, Any]] = field(default_factory=list)
    scene_description: str | None = None
    confidence: float | None = None
    provider: str | None = None
    model: str | None = None
    model_version: str | None = None
    latency_ms: int | None = None
    warnings: list[str] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    status: str = "completed"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VisionProviderHealth:
    provider: str
    state: str
    capabilities: list[str]
    configured: bool
    message: str | None = None


# Legacy provider-output shapes retained as neutral transport compatibility.
@dataclass(frozen=True)
class VisionFrame:
    frame_id: str = field(default_factory=lambda: str(uuid4()))
    session_id: str = ""
    timestamp: str = field(default_factory=now_iso)
    frame_ref: str | None = None
    width: int | None = None
    height: int | None = None
    provider_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FaceObservation:
    frame_id: str
    face_id: str | None = None
    confidence: float | None = None
    bounding_box: dict[str, int] | None = None
    provider_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BodyObservation:
    frame_id: str
    confidence: float | None = None
    provider_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VisionAnalysisResult:
    frame_id: str
    faces: list[FaceObservation] = field(default_factory=list)
    bodies: list[BodyObservation] = field(default_factory=list)
    provider_id: str | None = None
    latency_ms: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
