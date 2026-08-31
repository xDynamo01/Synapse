from __future__ import annotations

import hashlib
import math
from typing import Any, Protocol

import numpy as np

from synapse.audio.models import (
    DeviceDescriptor,
    InputDeviceTestResult,
    OutputDeviceTestResult,
)
from synapse.core.exceptions import NotFound


class AudioDeviceBackend(Protocol):
    name: str

    def query_devices(self) -> tuple[list[dict[str, Any]], tuple[int | None, int | None]]: ...

    def record(self, frames: int, sample_rate: int, channels: int, device: int) -> np.ndarray: ...

    def play(self, samples: np.ndarray, sample_rate: int, device: int) -> None: ...


class SoundDeviceBackend:
    name = "portaudio"

    def query_devices(self) -> tuple[list[dict[str, Any]], tuple[int | None, int | None]]:
        import sounddevice as sd

        devices = [dict(item) for item in sd.query_devices()]
        default = sd.default.device
        return devices, (int(default[0]), int(default[1]))

    def record(self, frames: int, sample_rate: int, channels: int, device: int) -> np.ndarray:
        import sounddevice as sd

        samples = sd.rec(
            frames,
            samplerate=sample_rate,
            channels=channels,
            dtype="float32",
            device=device,
            blocking=True,
        )
        return np.asarray(samples)

    def play(self, samples: np.ndarray, sample_rate: int, device: int) -> None:
        import sounddevice as sd

        sd.play(samples, samplerate=sample_rate, device=device, blocking=True)


class DeviceRuntime:
    def __init__(self, backend: AudioDeviceBackend | None = None) -> None:
        self.backend = backend or SoundDeviceBackend()
        self.last_error: str | None = None

    def health(self) -> dict[str, Any]:
        try:
            devices = self.list_devices()
        except Exception as exc:
            self.last_error = str(exc)
            return {"status": "unavailable", "backend": self.backend.name, "error": str(exc)}
        return {
            "status": "ready" if devices else "unavailable",
            "backend": self.backend.name,
            "input_count": len([item for item in devices if item.direction == "input"]),
            "output_count": len([item for item in devices if item.direction == "output"]),
            "error": None,
        }

    def list_devices(self, direction: str | None = None) -> list[DeviceDescriptor]:
        raw_devices, defaults = self.backend.query_devices()
        descriptors: list[DeviceDescriptor] = []
        for index, raw in enumerate(raw_devices):
            for candidate, channel_key, default_index in (
                ("input", "max_input_channels", defaults[0]),
                ("output", "max_output_channels", defaults[1]),
            ):
                channels = int(raw.get(channel_key, 0) or 0)
                if channels <= 0 or (direction and direction != candidate):
                    continue
                name = str(raw.get("name", f"Audio device {index}"))
                host_api = str(raw.get("hostapi", "unknown"))
                stable = hashlib.sha256(
                    f"{self.backend.name}|{host_api}|{name}|{candidate}|{channels}".encode()
                ).hexdigest()[:24]
                descriptors.append(
                    DeviceDescriptor(
                        id=f"{self.backend.name}:{index}:{candidate}",
                        stable_id=stable,
                        name=name,
                        direction=candidate,
                        backend=self.backend.name,
                        is_default=index == default_index,
                        channels=channels,
                        default_sample_rate=float(raw.get("default_samplerate", 0) or 0),
                        metadata={"runtime_index": index, "host_api": host_api},
                    )
                )
        return descriptors

    def resolve(self, device_id: str, direction: str | None = None) -> DeviceDescriptor:
        for device in self.list_devices(direction):
            if device.id == device_id or device.stable_id == device_id:
                return device
        raise NotFound(f"Audio device is unavailable or removed: {device_id}")

    def test_input(self, device_id: str, duration_ms: int = 500) -> InputDeviceTestResult:
        try:
            device = self.resolve(device_id, "input")
            sample_rate = int(device.default_sample_rate or 16_000)
            frames = max(1, int(sample_rate * duration_ms / 1000))
            samples = self.backend.record(frames, sample_rate, 1, _runtime_index(device))
            values = np.asarray(samples, dtype=np.float32).reshape(-1)
            rms = float(np.sqrt(np.mean(np.square(values, dtype=np.float64))))
            peak = float(np.max(np.abs(values))) if values.size else 0.0
            silence_ratio = float(np.mean(np.abs(values) <= 0.001)) if values.size else 1.0
            return InputDeviceTestResult(
                device_id=device.id,
                found=True,
                opened=True,
                frames_received=int(values.size),
                duration_ms=int(round(values.size / sample_rate * 1000)),
                signal_detected=rms > 0.001,
                rms=rms,
                peak=peak,
                clipping=peak >= 0.999,
                silence_ratio=silence_ratio,
            )
        except Exception as exc:
            return InputDeviceTestResult(
                device_id=device_id,
                found=not isinstance(exc, NotFound),
                opened=False,
                error=str(exc),
            )

    def test_output(self, device_id: str, duration_ms: int = 250) -> OutputDeviceTestResult:
        try:
            device = self.resolve(device_id, "output")
            sample_rate = int(device.default_sample_rate or 48_000)
            frames = max(1, int(sample_rate * duration_ms / 1000))
            timeline = np.arange(frames, dtype=np.float32) / sample_rate
            sample = (0.05 * np.sin(2 * math.pi * 440 * timeline)).astype(np.float32)
            self.backend.play(sample, sample_rate, _runtime_index(device))
            return OutputDeviceTestResult(
                device_id=device.id,
                found=True,
                opened=True,
                playback_started=True,
                playback_completed=True,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            return OutputDeviceTestResult(
                device_id=device_id,
                found=not isinstance(exc, NotFound),
                opened=False,
                error=str(exc),
            )


def _runtime_index(device: DeviceDescriptor) -> int:
    return int(device.metadata["runtime_index"])
