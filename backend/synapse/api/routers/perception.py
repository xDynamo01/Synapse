from __future__ import annotations

import base64
import binascii
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from synapse.api.common import api_error, payload_dict, runtime_from
from synapse.core.exceptions import ValidationError
from synapse.perception.models import PerceptionSignal

router = APIRouter()


class MultimodalSessionCreatePayload(BaseModel):
    participants: list[str] = Field(default_factory=list)
    active_channels: list[str] = Field(default_factory=lambda: ["text"])
    metadata: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None


class VisionSessionCreatePayload(BaseModel):
    multimodal_session_id: str | None = None
    agent_id: str | None = None
    camera_device_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None


class PerceptionSignalPayload(BaseModel):
    type: str
    modality: str
    source: str
    values: dict[str, Any] = Field(default_factory=dict)
    id: str | None = None
    timestamp: str | None = None
    session_id: str | None = None
    conversation_id: str | None = None
    mission_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    confidence: float | None = None
    provenance: list[dict[str, Any]] = Field(default_factory=list)
    sensitivity: str = "internal"
    expires_at: str | None = None
    correlation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VisionImagePayload(BaseModel):
    image_base64: str
    mime: str
    owner: str = "api"
    session_id: str | None = None
    use_ocr: bool | None = None
    delete_raw_after: bool | None = None
    correlation_id: str | None = None
    policy_context: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VisionScreenshotPayload(BaseModel):
    owner: str = "api"
    source_id: str = "primary"
    region: dict[str, int] | None = None
    session_id: str | None = None
    analyze: bool = True
    use_ocr: bool | None = None
    correlation_id: str | None = None
    policy_context: dict[str, Any] = Field(default_factory=dict)


class CameraCapturePayload(BaseModel):
    owner: str = "api"
    count: int = 1


class MultimodalFusionPayload(BaseModel):
    observation_ids: list[str] | None = None
    correlation_id: str | None = None
    window_seconds: int = 15


@router.get("/multimodal/sessions")
def list_multimodal_sessions(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(session) for session in runtime.multimodal.list_sessions()]


@router.post("/multimodal/sessions")
def create_multimodal_session(
    payload: MultimodalSessionCreatePayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.multimodal.create_session(
                participants=payload.participants,
                active_channels=payload.active_channels,
                metadata=payload.metadata,
                session_id=payload.session_id,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/multimodal/sessions/{session_id}")
def get_multimodal_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.multimodal.get_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/multimodal/sessions/{session_id}/pause")
def pause_multimodal_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.multimodal.pause_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/multimodal/sessions/{session_id}/resume")
def resume_multimodal_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.multimodal.resume_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/multimodal/sessions/{session_id}/close")
def close_multimodal_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.multimodal.close_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/multimodal/sessions/{session_id}/events")
def list_multimodal_session_events(session_id: str, request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(event) for event in runtime.multimodal.list_session_events(session_id)]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/multimodal/channels")
def list_multimodal_channels(request: Request) -> list[str]:
    runtime = runtime_from(request)
    return runtime.multimodal.get_supported_channels()


@router.get("/vision/sessions")
def list_vision_sessions(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(session) for session in runtime.vision.list_sessions()]


@router.post("/vision/sessions")
def create_vision_session(payload: VisionSessionCreatePayload, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.vision.create_session(**payload_dict(payload)))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/vision/sessions/{session_id}")
def get_vision_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.vision.get_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/vision/sessions/{session_id}/pause")
def pause_vision_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.vision.pause_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/vision/sessions/{session_id}/resume")
def resume_vision_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.vision.resume_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/vision/sessions/{session_id}/close")
def close_vision_session(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.vision.close_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/vision/cameras")
def list_vision_cameras(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(camera) for camera in runtime.vision.list_cameras()]


@router.get("/vision/sources")
def list_vision_sources(request: Request) -> list[dict[str, Any]]:
    return [asdict(item) for item in runtime_from(request).vision.list_sources()]


@router.get("/vision/providers")
def vision_providers(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return {
        "health": runtime.vision.health(),
        "capabilities": runtime.vision.provider_capabilities(),
    }


@router.post("/vision/images/analyze")
def analyze_vision_image(payload: VisionImagePayload, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        try:
            raw = base64.b64decode(payload.image_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValidationError("Invalid base64 image payload") from exc
        image = runtime.vision.store_image(
            raw,
            payload.mime,
            owner=payload.owner,
            policy_context=payload.policy_context,
            metadata=payload.metadata,
        )
        return asdict(
            runtime.vision.analyze_image(
                image,
                session_id=payload.session_id,
                use_ocr=payload.use_ocr,
                correlation_id=payload.correlation_id,
                delete_raw_after=payload.delete_raw_after,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/vision/screenshots")
def capture_vision_screenshot(payload: VisionScreenshotPayload, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        image = runtime.vision.capture_screenshot(
            owner=payload.owner,
            source_id=payload.source_id,
            region=payload.region,
            policy_context=payload.policy_context,
        )
        if payload.analyze:
            return {
                "input_id": image.id,
                "result": asdict(
                    runtime.vision.analyze_image(
                        image,
                        session_id=payload.session_id,
                        use_ocr=payload.use_ocr,
                        correlation_id=payload.correlation_id,
                    )
                ),
            }
        return {"input_id": image.id, "checksum": image.checksum, "expires_at": image.expires_at}
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/vision/results/{result_id}")
def get_vision_result(result_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).vision.get_result(result_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/vision/analyses/{analysis_id}/cancel")
def cancel_vision_analysis(analysis_id: str, request: Request) -> dict[str, Any]:
    return {
        "analysis_id": analysis_id,
        "cancelled": runtime_from(request).vision.cancel_analysis(analysis_id),
    }


@router.delete("/vision/inputs/{input_id}/raw")
def delete_vision_raw(input_id: str, request: Request) -> dict[str, Any]:
    try:
        return {"input_id": input_id, "deleted": runtime_from(request).vision.delete_raw(input_id)}
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/vision/cameras/{device_id}/open")
def open_vision_camera(device_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).vision.open_camera(device_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/vision/cameras/{device_id}/capture")
def capture_vision_camera(
    device_id: str, payload: CameraCapturePayload, request: Request
) -> list[dict[str, Any]]:
    try:
        images = runtime_from(request).vision.capture_camera_sequence(
            device_id, owner=payload.owner, count=payload.count
        )
        return [
            {"input_id": item.id, "checksum": item.checksum, "expires_at": item.expires_at}
            for item in images
        ]
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/vision/cameras/{device_id}/close")
def close_vision_camera(device_id: str, request: Request) -> dict[str, Any]:
    runtime_from(request).vision.close_camera(device_id)
    return {"device_id": device_id, "status": "closed"}


@router.get("/perception/signals")
def list_perception_signals(
    request: Request,
    session_id: str | None = None,
    conversation_id: str | None = None,
    mission_id: str | None = None,
    correlation_id: str | None = None,
) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [
        asdict(signal)
        for signal in runtime.perception.list_signals(
            session_id=session_id,
            conversation_id=conversation_id,
            mission_id=mission_id,
            correlation_id=correlation_id,
        )
    ]


@router.post("/perception/signals")
def ingest_perception_signal(payload: PerceptionSignalPayload, request: Request) -> dict[str, Any]:
    try:
        values = payload_dict(payload)
        values = {key: value for key, value in values.items() if value is not None}
        return asdict(runtime_from(request).perception.ingest_signal(PerceptionSignal(**values)))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/perception/signals/{signal_id}")
def get_perception_signal(signal_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).perception.get_signal(signal_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/perception/observations")
def list_perception_observations(
    request: Request,
    session_id: str | None = None,
    conversation_id: str | None = None,
    mission_id: str | None = None,
    correlation_id: str | None = None,
    include_expired: bool = False,
) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [
        asdict(item)
        for item in runtime.perception.list_observations(
            session_id=session_id,
            conversation_id=conversation_id,
            mission_id=mission_id,
            correlation_id=correlation_id,
            include_expired=include_expired,
        )
    ]


@router.get("/perception/observations/{observation_id}")
def get_perception_observation(observation_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).perception.get_observation(observation_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/perception/observations/{observation_id}/expire")
def expire_perception_observation(observation_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).perception.expire_observation(observation_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.delete("/perception/observations/{observation_id}")
def delete_perception_observation(observation_id: str, request: Request) -> dict[str, Any]:
    try:
        runtime_from(request).perception.delete_observation(observation_id)
        return {"observation_id": observation_id, "deleted": True}
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/perception/conflicts")
def list_perception_conflicts(request: Request) -> list[dict[str, Any]]:
    return [asdict(item) for item in runtime_from(request).perception.list_conflicts()]


@router.get("/perception/retention")
def perception_retention(request: Request) -> dict[str, Any]:
    return runtime_from(request).perception.retention_status()


@router.post("/perception/retention/cleanup")
def cleanup_perception_retention(request: Request, dry_run: bool = True) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).perception.cleanup(dry_run=dry_run))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/multimodal/fusions")
def create_multimodal_fusion(payload: MultimodalFusionPayload, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).multimodal.fuse(**payload_dict(payload)))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/multimodal/fusions/{fusion_id}")
def get_multimodal_fusion(fusion_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).multimodal.get_fusion(fusion_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/multimodal/fusions")
def list_multimodal_fusions(
    request: Request, correlation_id: str | None = None
) -> list[dict[str, Any]]:
    return [asdict(item) for item in runtime_from(request).multimodal.list_fusions(correlation_id)]


@router.get("/multimodal/fusions/{fusion_id}/context-preview")
def preview_multimodal_fusion(fusion_id: str, request: Request) -> dict[str, Any]:
    try:
        return runtime_from(request).multimodal.preview_context_payload(fusion_id)
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/perception/signals/session/{session_id}")
def list_perception_signals_by_session(session_id: str, request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(signal) for signal in runtime.perception.list_signals_by_session(session_id)]


@router.get("/perception/signals/type/{signal_type}")
def list_perception_signals_by_type(signal_type: str, request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(signal) for signal in runtime.perception.list_signals_by_type(signal_type)]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/perception/summary/{session_id}")
def perception_summary(session_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.perception.summarize_session(session_id))
    except Exception as exc:
        raise api_error(exc) from exc
