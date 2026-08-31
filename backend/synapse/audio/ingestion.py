from __future__ import annotations

import base64
import binascii
import hashlib
import io
import wave
from dataclasses import dataclass

import av
import numpy as np

from synapse.audio.errors import AudioValidationError
from synapse.audio.models import AudioPayload

CANONICAL_SAMPLE_RATE = 16_000
MAX_AUDIO_BYTES = 50 * 1024 * 1024
MAX_DURATION_MS = 10 * 60 * 1000
MIN_DURATION_MS = 40
SILENCE_RMS_THRESHOLD = 0.001


@dataclass(frozen=True)
class AudioIngestionLimits:
    max_bytes: int = MAX_AUDIO_BYTES
    max_duration_ms: int = MAX_DURATION_MS
    min_duration_ms: int = MIN_DURATION_MS
    reject_silence: bool = False


def decode_base64_audio(value: str) -> bytes:
    encoded = value.strip()
    if encoded.startswith("data:") and "," in encoded:
        encoded = encoded.split(",", 1)[1]
    try:
        return base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise AudioValidationError("invalid_audio", "Audio payload is not valid base64.") from exc


def ingest_audio(
    audio_bytes: bytes,
    declared_mime_type: str | None = None,
    *,
    limits: AudioIngestionLimits | None = None,
) -> AudioPayload:
    active_limits = limits or AudioIngestionLimits()
    if not audio_bytes:
        raise AudioValidationError("invalid_audio", "Audio payload is empty.")
    if len(audio_bytes) > active_limits.max_bytes:
        raise AudioValidationError("audio_too_large", "Audio payload exceeds the size limit.")

    detected_mime = _detect_mime(audio_bytes)
    declared = _normalize_mime(declared_mime_type)
    if declared and declared != detected_mime:
        raise AudioValidationError(
            "audio_mime_mismatch",
            f"Declared MIME {declared} does not match detected MIME {detected_mime}.",
        )

    samples = _decode_samples(audio_bytes)
    if samples.size == 0:
        raise AudioValidationError("invalid_audio", "Audio container has no decodable frames.")
    duration_ms = int(round(samples.size / CANONICAL_SAMPLE_RATE * 1000))
    if duration_ms < active_limits.min_duration_ms:
        raise AudioValidationError("audio_too_short", "Audio does not contain enough frames.")
    if duration_ms > active_limits.max_duration_ms:
        raise AudioValidationError("audio_too_long", "Audio exceeds the duration limit.")

    normalized = np.clip(samples, -1.0, 1.0)
    rms = float(np.sqrt(np.mean(np.square(normalized, dtype=np.float64))))
    peak = float(np.max(np.abs(normalized)))
    silence_ratio = float(np.mean(np.abs(normalized) <= SILENCE_RMS_THRESHOLD))
    if active_limits.reject_silence and rms <= SILENCE_RMS_THRESHOLD:
        raise AudioValidationError("no_speech_detected", "Audio contains only silence.")

    pcm = (normalized * 32767.0).astype("<i2").tobytes()
    canonical_wav = _encode_wav(pcm)
    return AudioPayload(
        audio_bytes=canonical_wav,
        mime_type="audio/wav",
        sample_rate=CANONICAL_SAMPLE_RATE,
        channels=1,
        encoding="pcm_s16le",
        duration_ms=duration_ms,
        checksum=hashlib.sha256(canonical_wav).hexdigest(),
        frame_count=normalized.size,
        average_volume=rms,
        peak_volume=peak,
        silence_ratio=silence_ratio,
        source_mime_type=detected_mime,
        metadata={"source_size_bytes": len(audio_bytes)},
    )


def _detect_mime(audio_bytes: bytes) -> str:
    if audio_bytes.startswith(b"RIFF") and audio_bytes[8:12] == b"WAVE":
        return "audio/wav"
    if audio_bytes.startswith(b"OggS"):
        return "audio/ogg"
    if audio_bytes.startswith(b"\x1aE\xdf\xa3"):
        return "audio/webm"
    raise AudioValidationError("unsupported_audio", "Unsupported or unrecognized audio container.")


def _normalize_mime(value: str | None) -> str | None:
    if not value:
        return None
    mime = value.split(";", 1)[0].strip().lower()
    aliases = {
        "audio/x-wav": "audio/wav",
        "audio/wave": "audio/wav",
        "audio/webm": "audio/webm",
        "video/webm": "audio/webm",
        "application/ogg": "audio/ogg",
    }
    return aliases.get(mime, mime)


def _decode_samples(audio_bytes: bytes) -> np.ndarray:
    try:
        with av.open(io.BytesIO(audio_bytes), mode="r") as container:
            streams = [stream for stream in container.streams if stream.type == "audio"]
            if not streams:
                raise AudioValidationError("invalid_audio", "Container has no audio stream.")
            resampler = av.AudioResampler(
                format="s16",
                layout="mono",
                rate=CANONICAL_SAMPLE_RATE,
            )
            chunks: list[np.ndarray] = []
            for frame in container.decode(streams[0]):
                if not isinstance(frame, av.AudioFrame):
                    continue
                converted = resampler.resample(frame)
                frames = converted if isinstance(converted, list) else [converted]
                for output in frames:
                    if output is not None:
                        chunks.append(output.to_ndarray().reshape(-1).astype(np.float32) / 32768.0)
            flushed = resampler.resample(None)
            flush_frames = flushed if isinstance(flushed, list) else [flushed]
            for output in flush_frames:
                if output is not None:
                    chunks.append(output.to_ndarray().reshape(-1).astype(np.float32) / 32768.0)
    except AudioValidationError:
        raise
    except Exception as exc:
        raise AudioValidationError(
            "invalid_audio", "Audio container is corrupt or truncated."
        ) from exc
    return np.concatenate(chunks) if chunks else np.array([], dtype=np.float32)


def _encode_wav(pcm: bytes) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(CANONICAL_SAMPLE_RATE)
        wav_file.writeframes(pcm)
    return output.getvalue()
