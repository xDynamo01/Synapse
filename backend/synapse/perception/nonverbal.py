from __future__ import annotations

import io
import wave
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from synapse.audio.models import AudioPayload

LOCAL_DSP_PROVIDER = "synapse_local_dsp"
LOCAL_DSP_VERSION = "prosody-v1"


@dataclass(frozen=True)
class AcousticAnalysisConfig:
    frame_duration_ms: int = 20
    silence_rms_threshold: float = 0.01
    minimum_pause_ms: int = 200
    minimum_pitch_hz: float = 60.0
    maximum_pitch_hz: float = 400.0
    minimum_pitch_correlation: float = 0.3


@dataclass(frozen=True)
class AcousticFeature:
    name: str
    value: float | int | None
    unit: str
    available: bool = True
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AcousticFeatureSet:
    provider: str
    algorithm: str
    algorithm_version: str
    duration_ms: int
    features: list[AcousticFeature]


class AcousticFeatureProvider(Protocol):
    provider_id: str
    algorithm_version: str

    def analyze(self, payload: AudioPayload) -> AcousticFeatureSet: ...
    def health(self) -> dict[str, str]: ...


class LocalDSPAcousticFeatureProvider:
    provider_id = LOCAL_DSP_PROVIDER
    algorithm_version = LOCAL_DSP_VERSION

    def __init__(self, config: AcousticAnalysisConfig | None = None) -> None:
        self.config = config or AcousticAnalysisConfig()

    def analyze(self, payload: AudioPayload) -> AcousticFeatureSet:
        samples = _pcm16_samples(payload.audio_bytes)
        frame_size = max(1, payload.sample_rate * self.config.frame_duration_ms // 1000)
        frames = [samples[index : index + frame_size] for index in range(0, len(samples), frame_size)]
        frame_rms = np.array(
            [float(np.sqrt(np.mean(np.square(frame, dtype=np.float64)))) for frame in frames if len(frame)],
            dtype=np.float64,
        )
        voiced = frame_rms > self.config.silence_rms_threshold
        pause_lengths = _runs(~voiced)
        pause_durations = [
            length * self.config.frame_duration_ms
            for length in pause_lengths
            if length * self.config.frame_duration_ms >= self.config.minimum_pause_ms
        ]
        voiced_segments = len(_runs(voiced))
        voiced_duration_ms = int(np.count_nonzero(voiced) * self.config.frame_duration_ms)
        unvoiced_duration_ms = max(0, payload.duration_ms - voiced_duration_ms)
        pitch_values = self._pitch_values(samples, payload.sample_rate, frame_size)
        pitch = float(np.median(pitch_values)) if pitch_values else None
        pitch_range = float(max(pitch_values) - min(pitch_values)) if pitch_values else None
        speech_rate = (
            voiced_segments / (voiced_duration_ms / 1000.0) if voiced_duration_ms else None
        )
        pitch_limitations = [] if pitch_values else ["No frame met voiced pitch criteria."]
        return AcousticFeatureSet(
            provider=self.provider_id,
            algorithm="frame_energy_and_autocorrelation",
            algorithm_version=self.algorithm_version,
            duration_ms=payload.duration_ms,
            features=[
                AcousticFeature("rms_energy", payload.average_volume, "normalized_amplitude"),
                AcousticFeature("peak_amplitude", payload.peak_volume, "normalized_amplitude"),
                AcousticFeature("silence_ratio", payload.silence_ratio, "ratio"),
                AcousticFeature("pause_count", len(pause_durations), "count"),
                AcousticFeature("pause_duration", sum(pause_durations), "ms"),
                AcousticFeature("utterance_duration", payload.duration_ms, "ms"),
                AcousticFeature("speech_duration", voiced_duration_ms, "ms"),
                AcousticFeature("unvoiced_duration", unvoiced_duration_ms, "ms"),
                AcousticFeature(
                    "voiced_ratio",
                    voiced_duration_ms / payload.duration_ms if payload.duration_ms else None,
                    "ratio",
                ),
                AcousticFeature(
                    "voiced_segment_rate",
                    speech_rate,
                    "voiced_segments_per_second",
                    available=speech_rate is not None,
                    limitations=["This is not transcript-derived word or syllable rate."],
                ),
                AcousticFeature(
                    "pitch_f0",
                    pitch,
                    "Hz",
                    available=pitch is not None,
                    limitations=pitch_limitations,
                ),
                AcousticFeature(
                    "pitch_range",
                    pitch_range,
                    "Hz",
                    available=pitch_range is not None,
                    limitations=pitch_limitations,
                ),
            ],
        )

    def health(self) -> dict[str, str]:
        return {"status": "supported", "provider": self.provider_id}

    def _pitch_values(
        self, samples: np.ndarray, sample_rate: int, frame_size: int
    ) -> list[float]:
        minimum_lag = max(1, int(sample_rate / self.config.maximum_pitch_hz))
        maximum_lag = min(frame_size - 1, int(sample_rate / self.config.minimum_pitch_hz))
        result: list[float] = []
        for frame in (
            samples[index : index + frame_size]
            for index in range(0, len(samples) - frame_size + 1, frame_size)
        ):
            centered = frame - float(np.mean(frame))
            energy = float(np.dot(centered, centered))
            if energy <= self.config.silence_rms_threshold**2 * len(frame):
                continue
            correlation = np.correlate(centered, centered, mode="full")[len(frame) - 1 :]
            candidates = correlation[minimum_lag : maximum_lag + 1]
            if not candidates.size:
                continue
            lag = minimum_lag + int(np.argmax(candidates))
            if float(correlation[lag] / correlation[0]) < self.config.minimum_pitch_correlation:
                continue
            result.append(sample_rate / lag)
        return result


def _pcm16_samples(audio_bytes: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
        return np.frombuffer(wav_file.readframes(wav_file.getnframes()), dtype="<i2").astype(
            np.float32
        ) / 32768.0


def _runs(values: np.ndarray) -> list[int]:
    lengths: list[int] = []
    current = 0
    for value in values:
        if bool(value):
            current += 1
        elif current:
            lengths.append(current)
            current = 0
    if current:
        lengths.append(current)
    return lengths
