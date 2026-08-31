from __future__ import annotations

import base64
import io
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from PIL import Image

from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.vision.models import CameraDevice, CaptureSource, VisionProviderHealth, VisionResult

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def png_bytes(color: str = "red") -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (16, 12), color).save(output, format="PNG")
    return output.getvalue()


def runtime_in_tempdir():
    directory = tempfile.TemporaryDirectory()
    settings = Settings(PROJECT_ROOT, Path(directory.name) / "data", "127.0.0.1", 8717, "local_owner")
    return directory, create_runtime(settings)


class ControlledVisionProvider:
    provider_id = "controlled_vision"

    def analyze_image(self, image, path):
        return VisionResult(
            input_id=image.id,
            observations=[{"type": "screen.error_visible", "description": {"summary": "Test failure visible"}, "confidence": 0.8}],
            confidence=0.8,
            provider=self.provider_id,
            model="controlled",
            model_version="test-v1",
            provenance=[{"input_id": image.id, "checksum": image.checksum, "artifact_path": "C:\\secret\\frame.png"}],
        )

    def health(self):
        return VisionProviderHealth(self.provider_id, "ready", self.capabilities(), True)

    def capabilities(self):
        return ["scene_description", "screen_understanding"]

    def cancel(self, analysis_id):
        return analysis_id == "pending"


class ControlledScreenProvider:
    provider_id = "controlled_screen"

    def list_sources(self):
        return [CaptureSource("1", "monitor", "Controlled monitor", True)]

    def capture(self, source_id, region=None):
        return png_bytes("blue"), {"source_id": source_id, "region": region}

    def health(self):
        return {"provider": self.provider_id, "state": "ready", "sources": 1}


class ControlledCameraProvider:
    provider_id = "controlled_camera"

    def list_devices(self):
        return [CameraDevice("cam-1", "Controlled camera", True, "ready")]

    def open(self, device_id):
        return None

    def capture_frame(self, device_id):
        return png_bytes("green")

    def close(self, device_id):
        return None

    def health(self):
        return VisionProviderHealth(self.provider_id, "ready", ["frame_capture"], True)


def test_explicit_image_analysis_creates_perception_observation() -> None:
    directory, runtime = runtime_in_tempdir()
    try:
        runtime.vision.vision_provider = ControlledVisionProvider()
        image = runtime.vision.store_image(png_bytes(), "image/png", owner="test")
        assert image.persisted is False
        assert image.retention_class == "transient_only"
        raw_root = runtime.settings.data_dir / "vision" / "raw"
        assert not raw_root.exists() or not list(raw_root.iterdir())
        result = runtime.vision.analyze_image(image, delete_raw_after=False, correlation_id="corr-1")
        observations = runtime.perception.list_observations(correlation_id="corr-1")
        assert result.confidence == 0.8
        assert observations[0].type == "screen.error_visible"
        assert runtime.vision.get_result(result.id).provider == "controlled_vision"
        assert result.provenance[0]["artifact_path"] == "[REDACTED]"
        assert not Path(image.image_reference).is_absolute()
    finally:
        directory.cleanup()


def test_raw_visual_persistence_requires_explicit_policy() -> None:
    directory, runtime = runtime_in_tempdir()
    try:
        policy_path = runtime.settings.data_dir / "config" / "perception_policy.yaml"
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text(
            json.dumps({"perception": {"persist_raw_visual": True}}), encoding="utf-8"
        )
        image = runtime.vision.store_image(png_bytes(), "image/png", owner="approved-owner")
        raw_path = runtime.capture.resolve_path(image)
        assert image.persisted is True
        assert image.retention_class == "raw_media_explicit_only"
        assert image.expires_at is not None
        assert image.sensitivity == "sensitive"
        assert image.provenance[0]["persist_raw_visual"] is True
        assert raw_path.exists()
        assert runtime.settings.data_dir in raw_path.parents
    finally:
        directory.cleanup()


def test_screenshot_is_explicit_and_raw_is_deleted_after_analysis() -> None:
    directory, runtime = runtime_in_tempdir()
    try:
        runtime.capture.provider = ControlledScreenProvider()
        runtime.vision.vision_provider = ControlledVisionProvider()
        image = runtime.vision.capture_screenshot(owner="test", source_id="1")
        raw_path = runtime.capture.resolve_path(image)
        assert raw_path.exists()
        runtime.vision.analyze_image(image)
        assert not raw_path.exists()
    finally:
        directory.cleanup()


def test_camera_is_optional_disabled_and_controlled_by_policy() -> None:
    directory, runtime = runtime_in_tempdir()
    try:
        runtime.vision.camera_provider = ControlledCameraProvider()
        assert runtime.vision.health()["camera"]["state"] == "ready"
        try:
            runtime.vision.open_camera("cam-1")
        except Exception as exc:
            assert getattr(exc, "code", None) == "camera_permission_denied"
        else:
            raise AssertionError("camera should be disabled by default")
    finally:
        directory.cleanup()


def test_provider_capabilities_health_and_cancel() -> None:
    directory, runtime = runtime_in_tempdir()
    try:
        runtime.vision.vision_provider = ControlledVisionProvider()
        assert "screen_understanding" in runtime.vision.provider_capabilities()["vision"]
        assert runtime.vision.health()["ocr"]["state"] == "not_configured"
        assert runtime.vision.cancel_analysis("pending") is True
    finally:
        directory.cleanup()


def test_vision_api_accepts_base64_without_exposing_absolute_path() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from synapse.api.routes import router

    directory, runtime = runtime_in_tempdir()
    try:
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        response = TestClient(app).post("/api/vision/images/analyze", json={
            "image_base64": base64.b64encode(png_bytes()).decode(),
            "mime": "image/png",
            "delete_raw_after": True,
        })
        assert response.status_code == 200
        assert "image_reference" not in response.text
        assert response.json()["provider"] == "local_image_metadata"
    finally:
        directory.cleanup()


def test_session_lifecycle_and_commands_remain_compatible() -> None:
    directory, runtime = runtime_in_tempdir()
    try:
        session = runtime.vision.create_session(agent_id="agent")
        assert runtime.vision.pause_session(session.session_id).status == "paused"
        assert runtime.vision.resume_session(session.session_id).status == "idle"
        assert runtime.commands.execute(runtime.context(), "/vision-health").status == "ok"
        assert runtime.vision.close_session(session.session_id).status == "closed"
        assert asdict(runtime.health.summary())["vision_provider_unavailable_count"] == 0
    finally:
        directory.cleanup()
