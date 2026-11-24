import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from synapse_ai.metrics import capture_usage, new_metrics, rss_bytes
from synapse_ai.providers import _infer, infer, ProviderError


class MetricsTests(unittest.TestCase):
    def test_provider_counters_preserve_unknown_and_measured_zero(self):
        for value, expected in ((None, None), (True, None), (-1, None), ("12", None), (0, 0), (12, 12)):
            with self.subTest(value=value):
                metrics = new_metrics()
                capture_usage({"usage": {"prompt_tokens": value, "completion_tokens": value}}, metrics)
                self.assertEqual(metrics["input_tokens"], expected)
                self.assertEqual(metrics["output_tokens"], expected)

    def test_actual_usage_is_forwarded_without_private_provider_fields(self):
        metrics = new_metrics()
        completion = {"choices": [{"message": {"role": "assistant", "content": "answer"}}],
                      "usage": {"prompt_tokens": 14, "completion_tokens": 3, "private": "CANARY-token"},
                      "private": "CANARY-token"}
        generation = {"max_output_tokens": 32, "reasoning_effort": "provider_default"}
        with patch("synapse_ai.providers._json", side_effect=[{"data": [{"id": "selected"}]}, completion]):
            self.assertEqual(_infer("http://127.0.0.1:1/v1", "selected", [{"role": "user", "content": "CANARY-prompt"}], generation, "conversation", 10, metrics), "answer")
        self.assertEqual((metrics["input_tokens"], metrics["output_tokens"]), (14, 3))
        self.assertEqual(metrics["inference_calls"], 1)
        self.assertNotIn("CANARY", json.dumps(metrics))

    def test_provider_failure_keeps_phase_and_dispatch_facts(self):
        metrics = new_metrics()
        generation = {"max_output_tokens": 32, "reasoning_effort": "provider_default", "timeout_ms": 1000}
        with patch("synapse_ai.providers._json", side_effect=[{"data": [{"id": "selected"}]}, ProviderError("provider_timeout")]):
            with self.assertRaisesRegex(ProviderError, "provider_timeout"):
                infer("http://127.0.0.1:1/v1", "selected", [{"role": "user", "content": "secret"}], generation, metrics=metrics)
        self.assertEqual(metrics["inference_calls"], 1)
        self.assertIn("inference", metrics["phases_ms"])
        self.assertIn("model_cleanup", metrics["phases_ms"])
        self.assertIsNone(metrics["input_tokens"])

    def test_native_worker_rss_truthfully_scoped(self):
        result = rss_bytes()
        self.assertTrue(result is None or result > 0)
        self.assertIsNone(new_metrics()["provider_ram_bytes"])


if __name__ == "__main__":
    unittest.main()
