from __future__ import annotations

import base64
import binascii
import math
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Any

from synapse.audio.models import (
    AudioInputRequest,
    SpeechFeatures,
    TranscriptResult,
    TranscriptSegment,
)
from synapse.core.data_dir import DataDir
from synapse.core.exceptions import ValidationError
from synapse.core.package_resources import packaged_resources_root
from synapse.speech_adapters.models import SpeechAdapterHealth, SpeechAdapterManifest

MODEL_PRESETS: dict[str, str] = {
    "auto": "small",
    "fast": "tiny",
    "balanced": "base",
    "quality": "medium",
    "high_quality": "large-v3",
    "tiny": "tiny",
    "base": "base",
    "small": "small",
    "medium": "medium",
    "large-v3": "large-v3",
    "large-v3-turbo": "large-v3",
}


class FasterWhisperSpeechToTextAdapter:
    def __init__(self, manifest: SpeechAdapterManifest, data_dir: DataDir) -> None:
        self._manifest = manifest
        self._data_dir = data_dir
        self._model_root = self._data_dir.resolve("voice/models/faster-whisper")
        self._model_root.mkdir(parents=True, exist_ok=True)
        self._temp_root = self._data_dir.resolve("voice/transcriptions/tmp")
        self._temp_root.mkdir(parents=True, exist_ok=True)
        self._models: dict[str, object] = {}

    def manifest(self) -> SpeechAdapterManifest:
        return self._manifest

    def capabilities(self) -> dict[str, object]:
        return {
            "streaming": False,
            "cancellation": False,
            "timestamps": True,
            "language_detection": True,
            "devices": ["cpu", "cuda"],
        }

    def health(self) -> SpeechAdapterHealth:
        if not self._module_available():
            return SpeechAdapterHealth(
                adapter_id=self._manifest.adapter_id,
                provider_id=self._manifest.provider_id,
                status="unavailable",
                checked_at=_now(),
                message="faster_whisper is not installed.",
                metadata={
                    "provider": self._manifest.provider_id,
                    "model_root": str(self._model_root),
                    "executes_real_provider": False,
                },
            )
        return SpeechAdapterHealth(
            adapter_id=self._manifest.adapter_id,
            provider_id=self._manifest.provider_id,
            status="available",
            checked_at=_now(),
            message="Faster-Whisper provider is available.",
            metadata={
                "provider": self._manifest.provider_id,
                "model_root": str(self._model_root),
                "executes_real_provider": True,
            },
        )

    def transcribe(self, request: AudioInputRequest) -> TranscriptResult:
        if not request.audio_base64:
            raise ValidationError("Audio payload is required.")
        if not self._module_available():
            raise ValidationError("faster_whisper is not installed.")

        started = perf_counter()
        audio_path = self._write_audio_blob(request.audio_base64, request.audio_format)
        try:
            model_name = self._resolve_model_name(request.model)
            device = str(request.metadata.get("stt_device", "cpu"))
            compute_type = str(
                request.metadata.get(
                    "stt_compute_type",
                    "int8" if device == "cpu" else "float16",
                )
            )
            model_reference = self._resolve_model_reference(model_name)
            model = self._load_model(model_reference, device, compute_type)
            language = _normalize_language(request.language or "pt")
            segments_iter, info = model.transcribe(
                str(audio_path),
                language=language,
                vad_filter=bool(request.metadata.get("vad_filter", False)),
                beam_size=1,
                temperature=0.0,
            )
            segments: list[TranscriptSegment] = []
            for segment in segments_iter:
                segment_confidence = _segment_confidence(segment)
                segments.append(
                    TranscriptSegment(
                        start=float(getattr(segment, "start", 0.0)),
                        end=float(getattr(segment, "end", 0.0)),
                        text=str(getattr(segment, "text", "")).strip(),
                        confidence=segment_confidence,
                        metadata={
                            "words": getattr(segment, "words", None),
                            "avg_logprob": getattr(segment, "avg_logprob", None),
                            "no_speech_prob": getattr(segment, "no_speech_prob", None),
                        },
                    )
                )
            text = " ".join(segment.text for segment in segments if segment.text).strip()
            duration_ms = request.duration_ms
            if duration_ms is None:
                duration_ms = int((segments[-1].end if segments else 0.0) * 1000)
            confidence = _average_confidence(segments, info)
            status = "success" if text else "no_speech_detected"
            if not text:
                confidence = None
            speech_features = _speech_features(
                segments,
                duration_ms,
                confidence,
                language_confidence=_language_probability(info),
                provider_metadata={
                    "provider": self._manifest.provider_id,
                    "model": model_name,
                    "model_reference": model_reference,
                    "download_root": str(self._model_root),
                    "device": device,
                    "compute_type": compute_type,
                    "executes_real_provider": True,
                },
            )
            result = TranscriptResult(
                text=text,
                status=status,
                language=getattr(info, "language", None) or request.language or "pt-BR",
                segments=segments,
                duration_ms=duration_ms,
                confidence=confidence,
                provider_id=self._manifest.provider_id,
                latency_ms=int((perf_counter() - started) * 1000),
                speech_features=speech_features,
                metadata={
                    **request.metadata,
                    "provider": self._manifest.provider_id,
                    "model": model_name,
                    "resolved_model": model_reference,
                    "download_root": str(self._model_root),
                    "device": device,
                    "compute_type": compute_type,
                    "executes_real_provider": True,
                },
            )
            return result
        finally:
            try:
                audio_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _load_model(self, model_reference: str, device: str, compute_type: str):
        cache_key = f"{model_reference}:{device}:{compute_type}"
        model = self._models.get(cache_key)
        if model is not None:
            return model
        whisper_model = self._whisper_model_class()
        model = whisper_model(
            model_reference,
            device=device,
            compute_type=compute_type,
            download_root=str(self._model_root),
            local_files_only=True,
        )
        self._models[cache_key] = model
        return model

    def _resolve_model_reference(self, model_name: str) -> str:
        packaged = packaged_resources_root() / "voice" / "models" / "faster-whisper" / model_name
        if (packaged / "model.bin").is_file():
            return str(packaged)
        return model_name

    @staticmethod
    def _resolve_model_name(model_hint: str | None) -> str:
        if not model_hint:
            return MODEL_PRESETS["auto"]
        normalized = model_hint.strip().lower()
        return MODEL_PRESETS.get(normalized, model_hint.strip())

    @staticmethod
    def _module_available() -> bool:
        try:
            FasterWhisperSpeechToTextAdapter._whisper_model_class()
        except ValidationError:
            return False
        return True

    @staticmethod
    def _whisper_model_class():
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:  # pragma: no cover - exercised via health checks/tests
            raise ValidationError("faster_whisper is not installed.") from exc
        return WhisperModel

    def _write_audio_blob(self, audio_base64: str, audio_format: str | None) -> Path:
        audio_bytes = _decode_audio(audio_base64)
        suffix = _suffix_for_audio_format(audio_format)
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=self._temp_root)
        try:
            handle.write(audio_bytes)
            handle.flush()
            return Path(handle.name)
        finally:
            handle.close()


def _decode_audio(audio_base64: str) -> bytes:
    if audio_base64.strip().startswith("data:") and "," in audio_base64:
        audio_base64 = audio_base64.split(",", 1)[1]
    try:
        return base64.b64decode(audio_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValidationError("Invalid audio payload.") from exc


def _suffix_for_audio_format(audio_format: str | None) -> str:
    if not audio_format:
        return ".webm"
    value = audio_format.strip().lower()
    if "/" in value:
        value = value.split("/", 1)[1]
    if ";" in value:
        value = value.split(";", 1)[0]
    if not value.startswith("."):
        value = f".{value}"
    return value


def _normalize_language(language: str) -> str:
    normalized = language.strip().lower().replace("_", "-")
    if "-" in normalized:
        normalized = normalized.split("-", 1)[0]
    return normalized or "pt"


def _segment_confidence(segment: Any) -> float | None:
    avg_logprob = getattr(segment, "avg_logprob", None)
    if avg_logprob is None:
        return None
    try:
        confidence = math.exp(float(avg_logprob))
    except Exception:
        return None
    return max(0.0, min(1.0, confidence))


def _average_confidence(segments: list[TranscriptSegment], info: Any) -> float | None:
    confidences = [segment.confidence for segment in segments if segment.confidence is not None]
    if confidences:
        return sum(confidences) / len(confidences)
    language_probability = getattr(info, "language_probability", None)
    if language_probability is None:
        return None
    try:
        return max(0.0, min(1.0, float(language_probability)))
    except Exception:
        return None


def _language_probability(info: Any) -> float | None:
    value = getattr(info, "language_probability", None)
    if value is None:
        return None
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return None


def _speech_features(
    segments: list[TranscriptSegment],
    duration_ms: int | None,
    confidence: float | None,
    language_confidence: float | None = None,
    provider_metadata: dict[str, Any] | None = None,
) -> SpeechFeatures:
    duration_seconds = (duration_ms or 0) / 1000 if duration_ms else None
    spoken_seconds = sum(max(0.0, segment.end - segment.start) for segment in segments)
    silence_duration = None
    pause_ratio = None
    pause_count = None
    pause_duration_ms = None
    speech_rate = None
    if duration_seconds and duration_seconds > 0:
        silence_duration = max(0.0, duration_seconds - spoken_seconds)
        pause_ratio = silence_duration / duration_seconds
        pause_duration_ms = int(round(silence_duration * 1000))
        gaps: list[float] = []
        previous_end = None
        for segment in segments:
            if previous_end is not None:
                gap = max(0.0, float(segment.start) - float(previous_end))
                if gap > 0:
                    gaps.append(gap)
            previous_end = segment.end
        pause_count = len(gaps)
        word_count = len([word for segment in segments for word in segment.text.split() if word])
        speech_rate = (word_count / duration_seconds) * 60 if word_count else 0.0
    timestamps = [
        {
            "start": segment.start,
            "end": segment.end,
            "text": segment.text,
            "confidence": segment.confidence,
        }
        for segment in segments
    ]
    return SpeechFeatures(
        duration_ms=duration_ms,
        average_volume=None,
        peak_volume=None,
        speech_rate=speech_rate,
        pause_count=pause_count,
        pause_duration_ms=pause_duration_ms,
        silence_ratio=pause_ratio,
        segment_count=len(segments),
        timestamps=timestamps,
        language_confidence=language_confidence,
        provider_metadata=provider_metadata or {},
        pause_ratio=pause_ratio,
        silence_duration=silence_duration,
        confidence=confidence,
        metadata={"segments": len(segments)},
    )


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
