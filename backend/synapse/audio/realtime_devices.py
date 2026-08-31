from __future__ import annotations

import io
import wave
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from synapse.audio.devices import DeviceRuntime, _runtime_index
from synapse.core.exceptions import ValidationError


class PCMInputStream(Protocol):
    def read_frame(self) -> bytes: ...

    def close(self) -> None: ...


class _SoundDeviceStream(Protocol):
    def read(self, frames: int) -> tuple[object, bool]: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...


class MicrophoneInputPort(Protocol):
    def capabilities(self) -> dict[str, object]: ...

    def list_input_devices(self) -> tuple[str, ...]: ...

    def open_stream(
        self,
        device_reference: str,
        *,
        sample_rate: int,
        frame_duration_ms: int,
    ) -> PCMInputStream: ...


@dataclass(frozen=True, slots=True)
class PlaybackRequest:
    playback_id: str
    session_id: str
    correlation_reference: str
    output_device_reference: str
    audio_reference: str
    wav_bytes: bytes


@dataclass(frozen=True, slots=True)
class PlaybackResult:
    playback_id: str
    requested: bool
    started: bool
    completed: bool
    interrupted: bool = False
    stop_requested: bool = False
    stop_confirmed: bool = False
    error: str | None = None


class AudioOutputPort(Protocol):
    def capabilities(self) -> dict[str, object]: ...

    def list_output_devices(self) -> tuple[str, ...]: ...

    def play(self, request: PlaybackRequest) -> PlaybackResult: ...

    def request_stop(self, playback_id: str) -> PlaybackResult: ...


class _SoundDeviceInputStream:
    def __init__(self, stream: _SoundDeviceStream, frame_samples: int) -> None:
        self._stream = stream
        self._frame_samples = frame_samples
        self._closed = False

    def read_frame(self) -> bytes:
        if self._closed:
            raise ValidationError("Microphone stream is closed.")
        samples, overflowed = self._stream.read(self._frame_samples)
        if overflowed:
            raise ValidationError("Microphone input overflowed.")
        normalized = np.asarray(samples, dtype=np.float32).reshape(-1)
        return (np.clip(normalized, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()

    def close(self) -> None:
        if self._closed:
            return
        self._stream.stop()
        self._stream.close()
        self._closed = True


class SoundDeviceMicrophonePort:
    def __init__(self, devices: DeviceRuntime | None = None) -> None:
        self._devices = devices or DeviceRuntime()

    def capabilities(self) -> dict[str, object]:
        return {
            "backend": "portaudio",
            "pcm_format": "pcm_s16le",
            "channels": 1,
            "streaming": True,
        }

    def list_input_devices(self) -> tuple[str, ...]:
        return tuple(device.stable_id for device in self._devices.list_devices("input"))

    def open_stream(
        self,
        device_reference: str,
        *,
        sample_rate: int,
        frame_duration_ms: int,
    ) -> PCMInputStream:
        import sounddevice as sd

        device = self._devices.resolve(device_reference, "input")
        frame_samples = sample_rate * frame_duration_ms // 1000
        stream = sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            device=_runtime_index(device),
            blocksize=frame_samples,
        )
        stream.start()
        return _SoundDeviceInputStream(stream, frame_samples)


class SoundDeviceOutputPort:
    def __init__(self, devices: DeviceRuntime | None = None) -> None:
        self._devices = devices or DeviceRuntime()
        self._active_playback_id: str | None = None

    def capabilities(self) -> dict[str, object]:
        return {"backend": "portaudio", "wav": True, "interruption": True}

    def list_output_devices(self) -> tuple[str, ...]:
        return tuple(device.stable_id for device in self._devices.list_devices("output"))

    def play(self, request: PlaybackRequest) -> PlaybackResult:
        import sounddevice as sd

        try:
            device = self._devices.resolve(request.output_device_reference, "output")
            samples, sample_rate = _decode_wav(request.wav_bytes)
            self._active_playback_id = request.playback_id
            sd.play(
                samples,
                samplerate=sample_rate,
                device=_runtime_index(device),
                blocking=False,
            )
            return PlaybackResult(request.playback_id, True, True, False)
        except Exception as exc:
            self._active_playback_id = None
            return PlaybackResult(
                request.playback_id,
                True,
                False,
                False,
                error=str(exc),
            )

    def request_stop(self, playback_id: str) -> PlaybackResult:
        import sounddevice as sd

        if self._active_playback_id != playback_id:
            return PlaybackResult(
                playback_id,
                True,
                False,
                False,
                stop_requested=True,
                stop_confirmed=False,
                error="Playback is not active.",
            )
        try:
            sd.stop()
            self._active_playback_id = None
            return PlaybackResult(
                playback_id,
                True,
                True,
                False,
                interrupted=True,
                stop_requested=True,
                stop_confirmed=True,
            )
        except Exception as exc:
            return PlaybackResult(
                playback_id,
                True,
                True,
                False,
                stop_requested=True,
                stop_confirmed=False,
                error=str(exc),
            )


def _decode_wav(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            if wav_file.getnchannels() != 1 or wav_file.getsampwidth() != 2:
                raise ValidationError("Playback requires mono PCM16 WAV audio.")
            sample_rate = wav_file.getframerate()
            frames = wav_file.readframes(wav_file.getnframes())
    except (OSError, wave.Error) as exc:
        raise ValidationError("Playback WAV is invalid.") from exc
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0, sample_rate
