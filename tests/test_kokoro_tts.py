import wave
from pathlib import Path
from unittest.mock import patch

import pytest

from synapse.audio.models import AudioOutputRequest
from synapse.core.data_dir import DataDir
from synapse.core.exceptions import ValidationError
from synapse.speech_adapters.execution import SpeechExecutionOutcome, SpeechExecutionResult
from synapse.speech_adapters.kokoro_tts import KokoroTextToSpeechAdapter
from synapse.speech_adapters.registry import builtin_speech_adapter_registry


class SpeechFixture:
    def execute(self, request):
        assert request.tool_reference == "tool://kokoro"
        assert "-I" in request.argv
        output = Path(request.argv[-1])
        with wave.open(str(output), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(b"\x01\x00" * 240)
        return SpeechExecutionResult.create(
            request_id=request.request_id, request_fingerprint=request.fingerprint,
            outcome=SpeechExecutionOutcome.EXITED, accepted=True, started=True,
            exit_code=0, termination_proved=True,
            produced_artifact_references=request.expected_output_artifact_references,
        )


def adapter(root):
    manifest = builtin_speech_adapter_registry().get_adapter("kokoro_tts_adapter")
    return KokoroTextToSpeechAdapter(manifest, DataDir(root), SpeechFixture())


def test_dora_output_is_inline_and_temporary(tmp_path):
    engine = adapter(tmp_path)
    with patch.object(engine, "_verify", return_value=True):
        result = engine.synthesize(AudioOutputRequest(session_id="test", text="Olá."))
    assert result.voice_id == "pf_dora"
    assert result.audio_base64
    assert result.sample_rate == 24000
    assert not list((tmp_path / "voice/synthesis").glob("*.wav"))


def test_missing_assets_and_other_voices_are_not_silently_replaced(tmp_path):
    engine = adapter(tmp_path)
    assert engine.health().status == "unconfigured"
    with pytest.raises(ValidationError, match="ready-made feminine"):
        engine.synthesize(AudioOutputRequest(session_id="test", text="Olá", voice_id="synapse-cadu"))
    with pytest.raises(ValidationError, match="unavailable"):
        engine.synthesize(AudioOutputRequest(session_id="test", text="Olá"))


def test_ready_feminine_voice_and_language_are_forwarded(tmp_path):
    engine = adapter(tmp_path)
    with patch.object(engine, "_verify", return_value=True):
        result = engine.synthesize(AudioOutputRequest(
            session_id="test", text="Hello.", voice_id="af_heart", language="en-US"
        ))
    assert result.voice_id == "af_heart"


def test_feminine_voice_rejects_a_mismatched_language(tmp_path):
    engine = adapter(tmp_path)
    with pytest.raises(ValidationError, match="requires language en-US"):
        engine.synthesize(AudioOutputRequest(
            session_id="test", text="Hello.", voice_id="af_heart", language="pt-BR"
        ))


def test_partially_installed_kokoro_is_unavailable(tmp_path):
    engine = adapter(tmp_path)
    model = engine._paths()[2]
    model.parent.mkdir(parents=True)
    model.write_bytes(b"invalid model")
    assert engine.health().status == "unavailable"
