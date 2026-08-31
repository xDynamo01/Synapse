from __future__ import annotations

from typing import Any

import numpy as np


class ControlledAudioDeviceBackend:
    name = "controlled-test-audio"

    def __init__(self) -> None:
        self.played = False

    def query_devices(self) -> tuple[list[dict[str, Any]], tuple[int | None, int | None]]:
        return (
            [
                {
                    "name": "Controlled Input",
                    "hostapi": "test",
                    "max_input_channels": 1,
                    "max_output_channels": 0,
                    "default_samplerate": 16_000,
                },
                {
                    "name": "Controlled Output",
                    "hostapi": "test",
                    "max_input_channels": 0,
                    "max_output_channels": 2,
                    "default_samplerate": 48_000,
                },
            ],
            (0, 1),
        )

    def record(self, frames: int, sample_rate: int, channels: int, device: int) -> np.ndarray:
        timeline = np.arange(frames, dtype=np.float32) / sample_rate
        return (0.1 * np.sin(2 * np.pi * 440 * timeline)).reshape(-1, channels)

    def play(self, samples: np.ndarray, sample_rate: int, device: int) -> None:
        self.played = True
