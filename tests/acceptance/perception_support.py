from __future__ import annotations

import io
import tempfile
from pathlib import Path

from PIL import Image

from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.vision.models import CaptureSource, VisionProviderHealth, VisionResult

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def runtime_fixture():
    directory = tempfile.TemporaryDirectory()
    settings = Settings(PROJECT_ROOT, Path(directory.name) / "data", "127.0.0.1", 8717, "local_owner")
    return directory, settings, create_runtime(settings)


def png_bytes(color: str = "navy") -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (24, 16), color).save(output, "PNG")
    return output.getvalue()


class ControlledVision:
    provider_id = "controlled_acceptance_vision"

    def analyze_image(self, image, path):
        return VisionResult(
            input_id=image.id,
            observations=[{
                "type": "screen.error_visible" if image.source_type == "screenshot" else "vision.document_visible",
                "description": {"summary": "Controlled visual evidence"},
                "attributes": {"source_type": image.source_type},
                "confidence": 0.82,
            }],
            confidence=0.82,
            provider=self.provider_id,
            model="controlled-vision",
            model_version="acceptance-v1",
            provenance=[{"input_id": image.id, "checksum": image.checksum}],
        )

    def health(self):
        return VisionProviderHealth(self.provider_id, "ready", self.capabilities(), True)

    def capabilities(self):
        return ["screen_understanding", "document_analysis"]

    def cancel(self, analysis_id):
        return False


class ControlledScreen:
    provider_id = "controlled_acceptance_screen"

    def list_sources(self):
        return [CaptureSource("1", "monitor", "Controlled monitor", True)]

    def capture(self, source_id, region=None):
        return png_bytes(), {"source_id": source_id, "region": region}

    def health(self):
        return {"provider": self.provider_id, "state": "ready", "sources": 1}
