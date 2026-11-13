import base64
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from synapse_ai.voice_worker import Voice, WAKE_TAIL_BYTES, WAKE_WINDOW_BYTES, respond


class VoiceProtocolTests(unittest.TestCase):
    def setUp(self):
        self.voice = Voice(None)

    def request(self, action, **fields):
        return respond(self.voice, json.dumps({"id": 7, "action": action, **fields}).encode())

    def test_health_leaves_models_unloaded(self):
        result = self.request("health")["result"]
        self.assertEqual(result["languages"], ["pt-BR", "en-US"])
        self.assertFalse(result["stt"])
        self.assertFalse(result["tts"])
        self.assertIsNone(self.voice.detector)
        self.assertIsNone(self.voice.stt)
        self.assertIsNone(self.voice.tts)

    def test_pcm_and_extra_fields_rejected_before_runtime(self):
        self.voice.wake = Mock()
        self.assertEqual(self.request("wake", pcm="!x")['error']['code'], "invalid_audio")
        self.assertEqual(self.request("wake", pcm="AA==")['error']['code'], "invalid_audio")
        self.assertEqual(self.request("wake", pcm="AAA=", path="external.wav")['error']['code'], "invalid_request")
        self.voice.wake.assert_not_called()

    def test_armed_wake_only_uses_bounded_keyword_stream(self):
        detector = self.voice.detector = Mock()
        detector.hyp.return_value = None
        self.voice.transcribe = Mock()
        samples = base64.b64encode(b"\0" * 3200).decode()
        for _ in range(100):
            self.assertEqual(self.request("wake", pcm=samples)["result"], {"detected": False})
            self.assertLess(len(self.voice.wake_tail), WAKE_TAIL_BYTES + 1)
            self.assertLess(self.voice.wake_bytes, WAKE_WINDOW_BYTES)
        self.assertGreater(detector.end_utt.call_count, 0)
        self.voice.transcribe.assert_not_called()
        detector.hyp.return_value = object()
        self.assertEqual(self.request("wake", pcm=samples)["result"], {"detected": True})
        self.assertEqual(self.voice.wake_tail, bytearray())


if __name__ == "__main__":
    unittest.main()
