from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from time import perf_counter
from typing import Any

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound, ValidationError
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.multimodal.runtime import MultimodalCommunicationRuntime
from synapse.perception.models import PerceptionArtifactKind, PerceptionSignal
from synapse.perception.runtime import PerceptionRuntime
from synapse.vision.capture import CaptureRuntime
from synapse.vision.errors import CameraNotFound, CameraPermissionDenied, VisionAnalysisFailed
from synapse.vision.models import (
    VISION_SESSION_STATUSES,
    CameraDevice,
    VisionInput,
    VisionObject,
    VisionResult,
    VisionSession,
)
from synapse.vision.providers import (
    CameraProvider,
    LocalImageMetadataProvider,
    NullCameraProvider,
    NullOCRProvider,
    OCRProvider,
    VisionProvider,
    provider_descriptor,
)


class VisionRuntime:
    """Coordinates explicit visual inputs and providers without interpreting final context."""

    def __init__(
        self,
        data_dir: DataDir,
        events: EventBus,
        providers: Any,
        multimodal: MultimodalCommunicationRuntime,
        perception: PerceptionRuntime | None = None,
        capture: CaptureRuntime | None = None,
        vision_provider: VisionProvider | None = None,
        ocr_provider: OCRProvider | None = None,
        camera_provider: CameraProvider | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.events = events
        # Kept as a constructor argument for the frozen container contract. Semantic
        # vision providers use the explicit protocol above, never registry mocks.
        self.providers = providers
        self.multimodal = multimodal
        self.perception = perception
        self.capture = capture
        self.vision_provider = vision_provider or LocalImageMetadataProvider()
        self.ocr_provider = ocr_provider or NullOCRProvider()
        self.camera_provider = camera_provider or NullCameraProvider()
        self._active_cameras: set[str] = set()

    def create_session(
        self,
        multimodal_session_id: str | None = None,
        agent_id: str | None = None,
        camera_device_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> VisionSession:
        if multimodal_session_id:
            self.multimodal.get_session(multimodal_session_id)
        session = VisionSession(
            session_id=session_id or VisionSession().session_id,
            multimodal_session_id=multimodal_session_id,
            agent_id=agent_id,
            camera_device_id=camera_device_id,
            metadata=metadata or {},
        )
        self._write_session(session)
        self.events.emit("vision.session.created", "vision", self._safe_session(session))
        return session

    def get_session(self, session_id: str) -> VisionSession:
        if not self._session_path(session_id).exists():
            raise NotFound(f"Vision session not found: {session_id}")
        return self._read_session(session_id)

    def list_sessions(self, status: str | None = None) -> list[VisionSession]:
        if status and status not in VISION_SESSION_STATUSES:
            raise ValidationError(f"Invalid vision session status: {status}")
        sessions = [
            self._read_session(path.stem) for path in sorted(self._sessions_root().glob("*.yaml"))
        ]
        if status:
            sessions = [session for session in sessions if session.status == status]
        return sorted(sessions, key=lambda item: (item.updated_at, item.session_id))

    def pause_session(self, session_id: str) -> VisionSession:
        session = self._set_session_status(session_id, "paused")
        self.events.emit("vision.session.paused", "vision", self._safe_session(session))
        return session

    def resume_session(self, session_id: str) -> VisionSession:
        session = self._set_session_status(session_id, "idle")
        self.events.emit("vision.session.resumed", "vision", self._safe_session(session))
        return session

    def close_session(self, session_id: str) -> VisionSession:
        session = self._set_session_status(session_id, "closed")
        if session.camera_device_id in self._active_cameras:
            self.close_camera(session.camera_device_id)
        self.events.emit("vision.session.closed", "vision", self._safe_session(session))
        return session

    def list_sources(self) -> list[Any]:
        return self.capture.list_sources() if self.capture else []

    def store_image(
        self,
        payload: bytes,
        mime: str,
        *,
        owner: str,
        policy_context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> VisionInput:
        if not self.capture:
            raise VisionAnalysisFailed("Capture runtime is not configured")
        image = self.capture.store_image(
            payload, mime, "uploaded_image", owner, policy_context, metadata
        )
        self._write_input(image)
        return image

    def capture_screenshot(
        self,
        *,
        owner: str,
        source_id: str = "primary",
        region: dict[str, int] | None = None,
        policy_context: dict[str, Any] | None = None,
    ) -> VisionInput:
        if not self.capture:
            raise VisionAnalysisFailed("Capture runtime is not configured")
        image = self.capture.capture_screenshot(
            owner=owner, source_id=source_id, region=region, policy_context=policy_context
        )
        self._write_input(image)
        return image

    def get_input(self, input_id: str) -> VisionInput:
        path = self._input_path(input_id)
        if not path.exists():
            raise NotFound(f"Vision input not found: {input_id}")
        return VisionInput(**load_structured_file(path))

    def analyze_image(
        self,
        image: VisionInput | str,
        *,
        session_id: str | None = None,
        use_ocr: bool | None = None,
        correlation_id: str | None = None,
        delete_raw_after: bool | None = None,
    ) -> VisionResult:
        item = self.get_input(image) if isinstance(image, str) else image
        session = self.get_session(session_id) if session_id else None
        if self.capture is None:
            raise VisionAnalysisFailed("Capture runtime is not configured")
        path = self.capture.resolve_path(item)
        if not path.exists():
            raise VisionAnalysisFailed("Raw visual input has expired or was deleted")
        active_marker = Path(f"{path}.active")
        active_marker.touch()
        self.events.emit(
            "vision.analysis_started",
            item.owner,
            {
                "input_id": item.id,
                "source_type": item.source_type,
                "correlation_id": correlation_id,
            },
        )
        started = perf_counter()
        try:
            result = self.vision_provider.analyze_image(item, path)
            result = self._sanitize_provider_result(result)
            warnings = list(result.warnings)
            detected_text = result.detected_text
            ocr_regions: list[dict[str, Any]] = []
            policy = self.capture.policy.load()
            should_ocr = use_ocr is True or (
                use_ocr is None and item.source_type == "screenshot" and not detected_text
            )
            if (
                should_ocr
                and policy.get("ocr_enabled", False)
                and self.ocr_provider.health().configured
            ):
                ocr = self.ocr_provider.analyze(item, path)
                detected_text = ocr.text
                ocr_regions = [
                    {
                        "source": "ocr",
                        "text": block.text,
                        "bounding_box": block.bounding_box,
                        "confidence": block.confidence,
                    }
                    for block in ocr.blocks
                    if block.bounding_box
                ]
                warnings.extend(ocr.warnings)
            elif should_ocr and use_ocr is True:
                warnings.append("OCR is disabled by policy or no OCR provider is configured.")
            result = replace(
                result,
                detected_text=detected_text,
                regions=[*result.regions, *ocr_regions],
                latency_ms=result.latency_ms or int((perf_counter() - started) * 1000),
                warnings=list(dict.fromkeys(warnings)),
            )
            persisted = result
            if detected_text and item.policy_context.get("persist_detected_text") is not True:
                persisted = replace(
                    result,
                    detected_text=None,
                    regions=[region for region in result.regions if region.get("source") != "ocr"],
                    warnings=[
                        *result.warnings,
                        "Detected text was omitted from persistence by policy.",
                    ],
                )
            self._write_result(persisted)
            self._publish_observations(item, result, session, correlation_id)
            self.events.emit(
                "vision.analysis_completed",
                item.owner,
                self._safe_result_event(item, result, correlation_id),
            )
            if delete_raw_after is True or (
                delete_raw_after is None and item.source_type == "screenshot"
            ):
                self.delete_raw(item.id)
            return result
        except Exception as exc:
            self.events.emit(
                "vision.analysis_failed",
                item.owner,
                {
                    "input_id": item.id,
                    "error_type": type(exc).__name__,
                    "correlation_id": correlation_id,
                },
            )
            if isinstance(exc, VisionAnalysisFailed):
                raise
            raise VisionAnalysisFailed(
                "Visual analysis failed", details={"error": type(exc).__name__}
            ) from exc
        finally:
            active_marker.unlink(missing_ok=True)

    def get_result(self, result_id: str) -> VisionResult:
        path = self._result_path(result_id)
        if not path.exists():
            raise NotFound(f"Vision result not found: {result_id}")
        raw = load_structured_file(path)
        raw["objects"] = [VisionObject(**item) for item in raw.get("objects", [])]
        return VisionResult(**raw)

    def cancel_analysis(self, analysis_id: str) -> bool:
        cancelled = self.vision_provider.cancel(analysis_id)
        self.events.emit(
            "vision.analysis_cancelled",
            "vision",
            {"analysis_id": analysis_id, "cancelled": cancelled},
        )
        return cancelled

    def delete_raw(self, input_id: str) -> bool:
        image = self.get_input(input_id)
        deleted = bool(self.capture and self.capture.delete_raw_asset(image))
        self.events.emit(
            "vision.raw_deleted", image.owner, {"input_id": input_id, "deleted": deleted}
        )
        return deleted

    def provider_capabilities(self) -> dict[str, list[str]]:
        return {
            "vision": self.vision_provider.capabilities(),
            "ocr": self.ocr_provider.health().capabilities,
            "camera": self.camera_provider.health().capabilities,
        }

    def health(self) -> dict[str, Any]:
        return {
            "vision": provider_descriptor(self.vision_provider),
            "ocr": provider_descriptor(self.ocr_provider),
            "camera": provider_descriptor(self.camera_provider),
            "screen_capture": self.capture.health()
            if self.capture
            else {"state": "not_configured"},
            "active_cameras": len(self._active_cameras),
        }

    def list_cameras(self) -> list[CameraDevice]:
        return self.camera_provider.list_devices()

    def open_camera(self, device_id: str) -> CameraDevice:
        policy = self.capture.policy.load() if self.capture else {}
        if not policy.get("camera_enabled", False):
            raise CameraPermissionDenied("Camera is disabled by policy")
        device = self._camera(device_id)
        try:
            self.camera_provider.open(device_id)
        except Exception as exc:
            self.events.emit(
                "camera.failed",
                "vision",
                {"device_id": device_id, "error_type": type(exc).__name__},
            )
            raise
        self._active_cameras.add(device_id)
        self.events.emit("camera.opened", "vision", {"device_id": device_id})
        return replace(device, status="active")

    def capture_camera_frame(self, device_id: str, *, owner: str) -> VisionInput:
        if device_id not in self._active_cameras:
            self.open_camera(device_id)
        try:
            payload = self.camera_provider.capture_frame(device_id)
        except Exception as exc:
            self.events.emit(
                "camera.failed", owner, {"device_id": device_id, "error_type": type(exc).__name__}
            )
            raise
        if not self.capture:
            raise VisionAnalysisFailed("Capture runtime is not configured")
        image = self.capture.store_image(
            payload, "image/png", "camera", owner, metadata={"device_id": device_id}
        )
        self._write_input(image)
        self.events.emit(
            "vision.camera_frame_captured", owner, {"device_id": device_id, "input_id": image.id}
        )
        return image

    def capture_camera_sequence(
        self, device_id: str, *, owner: str, count: int = 1
    ) -> list[VisionInput]:
        if count < 1 or count > 10:
            raise ValidationError("Camera sequence count must be between 1 and 10")
        return [self.capture_camera_frame(device_id, owner=owner) for _ in range(count)]

    def close_camera(self, device_id: str) -> None:
        try:
            self.camera_provider.close(device_id)
        finally:
            self._active_cameras.discard(device_id)
            self.events.emit("camera.closed", "vision", {"device_id": device_id})

    def preview_context_payload(self, result_id: str) -> dict[str, Any]:
        result = self.get_result(result_id)
        return {
            "source_type": "vision_observations",
            "source_id": result.id,
            "observations": result.observations,
            "confidence": result.confidence,
            "provenance": result.provenance,
            "warnings": result.warnings,
        }

    def _publish_observations(
        self,
        image: VisionInput,
        result: VisionResult,
        session: VisionSession | None,
        correlation_id: str | None,
    ) -> None:
        if not self.perception:
            return
        for index, observation in enumerate(result.observations):
            values = {
                "description": observation.get("description", {}),
                "entities": observation.get("entities", []),
                "attributes": observation.get("attributes", {}),
                "regions": observation.get("regions", []),
            }
            if result.detected_text and image.policy_context.get("persist_detected_text") is True:
                values["detected_text"] = result.detected_text
            self.perception.ingest_signal(
                PerceptionSignal(
                    type=str(observation.get("type", "vision.observed")),
                    modality="screen"
                    if image.source_type == "screenshot"
                    else image.source_type.replace("uploaded_image", "vision"),
                    source="vision",
                    session_id=session.session_id if session else None,
                    confidence=observation.get("confidence", result.confidence),
                    values=values,
                    provenance=[
                        {"input_id": image.id, "checksum": image.checksum},
                        {
                            "provider": result.provider,
                            "result_id": result.id,
                            "observation_index": index,
                        },
                    ],
                    sensitivity=image.sensitivity,
                    expires_at=image.expires_at,
                    correlation_id=correlation_id,
                    metadata={"vision_result_id": result.id, "source_type": image.source_type},
                    artifact_kind=(
                        PerceptionArtifactKind.MODEL_INFERENCE
                        if result.metadata.get("executes_semantic_analysis", True)
                        else PerceptionArtifactKind.DERIVED_FEATURE
                    ),
                    provider=result.provider,
                    model=result.model,
                    model_version=result.model_version,
                    input_references=[image.id],
                    external_processing=bool(result.metadata.get("external_processing", False)),
                )
            )

    def _camera(self, device_id: str) -> CameraDevice:
        for device in self.list_cameras():
            if device.device_id == device_id:
                return device
        raise CameraNotFound(f"Camera not found: {device_id}")

    def _set_session_status(self, session_id: str, status: str) -> VisionSession:
        if status not in VISION_SESSION_STATUSES:
            raise ValidationError(f"Invalid vision session status: {status}")
        session = self.get_session(session_id)
        if session.status == "closed" and status != "closed":
            raise ValidationError(f"Vision session is closed: {session_id}")
        updated = replace(session, status=status, updated_at=_now())
        self._write_session(updated)
        return updated

    def _read_session(self, session_id: str) -> VisionSession:
        raw = load_structured_file(self._session_path(session_id))
        raw.setdefault("session_id", session_id)
        raw.setdefault("multimodal_session_id", None)
        raw.setdefault("agent_id", None)
        raw.setdefault("status", "idle")
        raw.setdefault("camera_device_id", None)
        raw.setdefault("created_at", _now())
        raw.setdefault("updated_at", raw["created_at"])
        raw.setdefault("metadata", {})
        return VisionSession(**raw)

    def _write_session(self, session: VisionSession) -> None:
        dump_structured_file(self._session_path(session.session_id), asdict(session))

    def _write_input(self, image: VisionInput) -> None:
        dump_structured_file(self._input_path(image.id), asdict(image))

    def _write_result(self, result: VisionResult) -> None:
        dump_structured_file(self._result_path(result.id), asdict(result))

    @staticmethod
    def _safe_session(session: VisionSession) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "status": session.status,
            "agent_id": session.agent_id,
        }

    @staticmethod
    def _safe_result_event(
        image: VisionInput, result: VisionResult, correlation_id: str | None
    ) -> dict[str, Any]:
        return {
            "result_id": result.id,
            "input_id": image.id,
            "source_type": image.source_type,
            "provider": result.provider,
            "observation_count": len(result.observations),
            "confidence": result.confidence,
            "correlation_id": correlation_id,
        }

    @staticmethod
    def _sanitize_provider_result(result: VisionResult) -> VisionResult:
        return replace(
            result,
            observations=_safe_provider_value(result.observations),
            detected_text=_safe_provider_value(result.detected_text),
            objects=[
                replace(item, attributes=_safe_provider_value(item.attributes))
                for item in result.objects
            ],
            regions=_safe_provider_value(result.regions),
            scene_description=_safe_provider_value(result.scene_description),
            warnings=_safe_provider_value(result.warnings),
            provenance=_safe_provider_value(result.provenance),
            metadata=_safe_provider_value(result.metadata),
        )

    def _root(self, name: str) -> Path:
        root = self.data_dir.resolve(f"vision/{name}")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _sessions_root(self) -> Path:
        return self._root("sessions")

    def _session_path(self, session_id: str) -> Path:
        return self._sessions_root() / f"{session_id}.yaml"

    def _input_path(self, input_id: str) -> Path:
        return self._root("inputs") / f"{input_id}.yaml"

    def _result_path(self, result_id: str) -> Path:
        return self._root("results") / f"{result_id}.yaml"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_provider_value(value: Any, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {
            str(item_key): _safe_provider_value(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_safe_provider_value(item, key) for item in value]
    if isinstance(value, str):
        path_key = key and any(
            token in key.casefold() for token in ("path", "reference", "filename")
        )
        if path_key or Path(value).is_absolute() or PureWindowsPath(value).is_absolute():
            return "[REDACTED]"
    return value
