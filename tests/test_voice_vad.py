from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.core.exceptions import ValidationError
from synapse.voice.vad import VADConfig, WebRTCVADProvider


class SequenceClassifier:
    def __init__(self, values: list[bool]) -> None:
        self.values = iter(values)

    def is_speech(self, frame: bytes, sample_rate: int) -> bool:
        return next(self.values)


def frame(duration_ms: int = 20, sample_rate: int = 16_000) -> bytes:
    return bytes(sample_rate * duration_ms // 1000 * 2)


class WebRTCVADProviderTests(unittest.TestCase):
    def test_speech_lifecycle_and_silence(self) -> None:
        provider = WebRTCVADProvider(
            VADConfig(
                frame_duration_ms=20,
                min_speech_duration_ms=40,
                min_silence_duration_ms=40,
            ),
            SequenceClassifier([False, True, True, True, False, False]),
        )

        events = [provider.process_frame(frame()).type for _ in range(6)]

        self.assertEqual(
            events,
            [
                "silence",
                "silence",
                "speech_started",
                "speech_continued",
                "speech_continued",
                "speech_ended",
            ],
        )

    def test_max_duration_closes_utterance(self) -> None:
        provider = WebRTCVADProvider(
            VADConfig(
                frame_duration_ms=20,
                min_speech_duration_ms=20,
                min_silence_duration_ms=40,
                max_utterance_duration_ms=60,
            ),
            SequenceClassifier([True, True, True]),
        )

        events = [provider.process_frame(frame()).type for _ in range(3)]

        self.assertEqual(events[-1], "max_duration_reached")

    def test_reset_prevents_state_leak_between_utterances(self) -> None:
        provider = WebRTCVADProvider(
            VADConfig(min_speech_duration_ms=20),
            SequenceClassifier([True, False]),
        )
        self.assertEqual(provider.process_frame(frame()).type, "speech_started")

        provider.reset()

        self.assertEqual(provider.process_frame(frame()).type, "silence")

    def test_rejects_invalid_frame_size_and_configuration(self) -> None:
        with self.assertRaises(ValidationError):
            WebRTCVADProvider(VADConfig(frame_duration_ms=15), SequenceClassifier([]))
        provider = WebRTCVADProvider(classifier=SequenceClassifier([]))
        with self.assertRaises(ValidationError):
            provider.process_frame(b"short")

    def test_real_provider_health_and_capabilities(self) -> None:
        provider = WebRTCVADProvider()

        self.assertEqual(provider.health()["status"], "ready")
        self.assertFalse(provider.capabilities()["confidence"])
        self.assertTrue(provider.capabilities()["streaming"])


if __name__ == "__main__":
    unittest.main()
