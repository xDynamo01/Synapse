from types import SimpleNamespace

import pytest

from synapse.bootstrap.adapters.voicestudio import VoiceStudioHttpTransport
from synapse.core.data_dir import DataDir
from synapse.core.exceptions import ValidationError
from synapse.health.contracts import HealthCheckContext
from synapse.health.contributors.voice import VoiceHealthContributor
from synapse.speech_adapters.registry import builtin_speech_adapter_registry
from synapse.speech_adapters.voicestudio_tts import VoiceStudioTextToSpeechAdapter


def test_voice_health_probes_diagnostics_once_and_counts_sessions():
    class Voice:
        calls = 0

        def provider_unavailable_count(self):
            return 0

        def list_sessions(self):
            return [SimpleNamespace(status="listening"), SimpleNamespace(status="closed")]

        def diagnostics(self):
            self.calls += 1
            return {"active_sessions": 1}

    voice = Voice()
    result = VoiceHealthContributor(voice, None, None, None, None).collect_health(
        HealthCheckContext("2026-10-23", None, "test", 1)
    )
    assert result.summary["voice_runtime_available"] is True
    assert result.metrics["active_voice_sessions"] == 1
    assert voice.calls == 1
    assert result.summary["voice_diagnostics"]["active_sessions"] == 1


@pytest.mark.parametrize("url", ["https://example.com", "http://example.com", "http://user:pass@127.0.0.1", "http://127.0.0.1?remote=yes"])
def test_voicestudio_transport_rejects_nonlocal_or_ambiguous_endpoints(url):
    with pytest.raises(ValidationError):
        VoiceStudioHttpTransport(url)


def test_voicestudio_uses_injected_transport_and_defaults_to_unconfigured(tmp_path):
    manifest = builtin_speech_adapter_registry().get_adapter("voicestudio_tts_adapter")
    engine = VoiceStudioTextToSpeechAdapter(manifest, DataDir(tmp_path))
    assert engine.health().status == "unconfigured"

    class Transport:
        def request(self, method, path, payload=None):
            assert (method, path) == ("GET", "/health")
            return {"status": "ok"}

    engine = VoiceStudioTextToSpeechAdapter(manifest, DataDir(tmp_path), Transport())
    assert engine.health().status == "available"
