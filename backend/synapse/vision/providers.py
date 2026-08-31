from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Protocol

from synapse.vision.errors import CameraUnavailable, OCRUnavailable
from synapse.vision.models import (
    CameraDevice,
    OCRResult,
    VisionInput,
    VisionProviderHealth,
    VisionResult,
)


class VisionProvider(Protocol):
    provider_id: str

    def analyze_image(self, image: VisionInput, path: Path) -> VisionResult: ...
    def health(self) -> VisionProviderHealth: ...
    def capabilities(self) -> list[str]: ...
    def cancel(self, analysis_id: str) -> bool: ...


class OCRProvider(Protocol):
    provider_id: str

    def analyze(self, image: VisionInput, path: Path) -> OCRResult: ...
    def health(self) -> VisionProviderHealth: ...


class CameraProvider(Protocol):
    provider_id: str

    def list_devices(self) -> list[CameraDevice]: ...
    def open(self, device_id: str) -> None: ...
    def capture_frame(self, device_id: str) -> bytes: ...
    def close(self, device_id: str) -> None: ...
    def health(self) -> VisionProviderHealth: ...


class LocalImageMetadataProvider:
    provider_id = "local_image_metadata"

    def analyze_image(self, image: VisionInput, path: Path) -> VisionResult:
        return VisionResult(
            input_id=image.id,
            observations=[
                {
                    "type": "vision.image.validated",
                    "description": {"summary": "Image decoded and validated locally."},
                    "attributes": {"mime": image.mime, "dimensions": image.dimensions},
                    "confidence": None,
                }
            ],
            confidence=None,
            provider=self.provider_id,
            model=None,
            warnings=["No semantic vision provider is configured."],
            provenance=[
                {"input_id": image.id, "checksum": image.checksum, "provider": self.provider_id}
            ],
            metadata={"executes_semantic_analysis": False, "size_bytes": path.stat().st_size},
        )

    def health(self) -> VisionProviderHealth:
        return VisionProviderHealth(self.provider_id, "ready", self.capabilities(), True)

    def capabilities(self) -> list[str]:
        return ["image_validation", "dimensions", "checksum"]

    def cancel(self, analysis_id: str) -> bool:
        return False


class NullOCRProvider:
    provider_id = "not_configured"

    def analyze(self, image: VisionInput, path: Path) -> OCRResult:
        raise OCRUnavailable("OCR provider is not configured")

    def health(self) -> VisionProviderHealth:
        return VisionProviderHealth(self.provider_id, "not_configured", [], False)


class NullCameraProvider:
    provider_id = "not_configured"

    def list_devices(self) -> list[CameraDevice]:
        return []

    def open(self, device_id: str) -> None:
        raise CameraUnavailable("Camera provider is not configured")

    def capture_frame(self, device_id: str) -> bytes:
        raise CameraUnavailable("Camera provider is not configured")

    def close(self, device_id: str) -> None:
        return None

    def health(self) -> VisionProviderHealth:
        return VisionProviderHealth(self.provider_id, "not_configured", [], False)


def provider_descriptor(provider: VisionProvider | OCRProvider | CameraProvider) -> dict:
    health = provider.health()
    return asdict(health)
