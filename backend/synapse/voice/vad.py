from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from synapse.core.exceptions import ValidationError


class FrameClassifier(Protocol):
    def is_speech(self, frame: bytes, sample_rate: int) -> bool: ...


@dataclass(frozen=True)
class VADConfig:
    aggressiveness: int = 2
    frame_duration_ms: int = 20
    min_speech_duration_ms: int = 200
    min_silence_duration_ms: int = 400
    max_utterance_duration_ms: int = 120_000
    pre_roll_ms: int = 200
    post_roll_ms: int = 100


@dataclass(frozen=True)
class VADEvent:
    type: str
    timestamp_ms: int
    frame_start: int
    frame_end: int
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class WebRTCVADProvider:
    def __init__(
        self,
        config: VADConfig | None = None,
        classifier: FrameClassifier | None = None,
    ) -> None:
        self.config = config or VADConfig()
        self._validate_config()
        self.classifier = classifier or self._create_classifier()
        self.reset()

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider": "webrtcvad",
            "sample_rates": [8000, 16000, 32000, 48000],
            "frame_durations_ms": [10, 20, 30],
            "confidence": False,
            "streaming": True,
        }

    def health(self) -> dict[str, Any]:
        return {
            "status": "ready" if self.classifier is not None else "unavailable",
            "provider": "webrtcvad",
            "checked_at": datetime.now(UTC).isoformat(),
            "capabilities": self.capabilities(),
        }

    def reset(self) -> None:
        self.frame_index = 0
        self.speech_ms = 0
        self.silence_ms = 0
        self.utterance_ms = 0
        self.in_speech = False

    def process_frame(self, frame: bytes, sample_rate: int = 16_000) -> VADEvent:
        expected_bytes = sample_rate * self.config.frame_duration_ms // 1000 * 2
        if len(frame) != expected_bytes:
            raise ValidationError(f"VAD frame must contain exactly {expected_bytes} PCM16 bytes.")
        start = self.frame_index
        self.frame_index += 1
        timestamp_ms = self.frame_index * self.config.frame_duration_ms
        speech = self.classifier.is_speech(frame, sample_rate)
        event_type = "silence"
        if speech:
            self.speech_ms += self.config.frame_duration_ms
            self.silence_ms = 0
            if not self.in_speech and self.speech_ms >= self.config.min_speech_duration_ms:
                self.in_speech = True
                self.utterance_ms = self.speech_ms
                event_type = "speech_started"
            elif self.in_speech:
                self.utterance_ms += self.config.frame_duration_ms
                event_type = "speech_continued"
        else:
            self.speech_ms = 0
            if self.in_speech:
                self.silence_ms += self.config.frame_duration_ms
                self.utterance_ms += self.config.frame_duration_ms
                event_type = "speech_continued"
                if self.silence_ms >= self.config.min_silence_duration_ms:
                    event_type = "speech_ended"
                    self.in_speech = False
                    self.silence_ms = 0
                    self.utterance_ms = 0
        if self.in_speech and self.utterance_ms >= self.config.max_utterance_duration_ms:
            event_type = "max_duration_reached"
            self.in_speech = False
            self.speech_ms = 0
            self.silence_ms = 0
            self.utterance_ms = 0
        return VADEvent(
            type=event_type,
            timestamp_ms=timestamp_ms,
            frame_start=start,
            frame_end=self.frame_index,
            metadata={
                "provider": "webrtcvad",
                "frame_duration_ms": self.config.frame_duration_ms,
            },
        )

    def _validate_config(self) -> None:
        if self.config.frame_duration_ms not in {10, 20, 30}:
            raise ValidationError("WebRTC VAD frame duration must be 10, 20, or 30 ms.")
        if self.config.aggressiveness not in {0, 1, 2, 3}:
            raise ValidationError("WebRTC VAD aggressiveness must be between 0 and 3.")
        if self.config.min_speech_duration_ms <= 0:
            raise ValidationError("Minimum speech duration must be positive.")
        if self.config.min_silence_duration_ms <= 0:
            raise ValidationError("Minimum silence duration must be positive.")

    def _create_classifier(self) -> FrameClassifier:
        try:
            import webrtcvad
        except ImportError as exc:
            raise ValidationError("vad_unavailable: WebRTC VAD is not installed.") from exc
        return webrtcvad.Vad(self.config.aggressiveness)
