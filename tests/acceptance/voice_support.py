from __future__ import annotations

import base64
import io
import math
import struct
import sys
import tempfile
import wave
from pathlib import Path
from types import ModuleType, SimpleNamespace

from synapse.agents.provisioning import AgentCreateRequest
from synapse.audio.models import TextToSpeechResult
from synapse.core.app import create_runtime
from synapse.core.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def valid_wav(duration_ms: int = 300) -> bytes:
    sample_rate = 16_000
    frames = b"".join(
        struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / sample_rate)))
        for i in range(int(sample_rate * duration_ms / 1000))
    )
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(frames)
    return output.getvalue()


def install_controlled_whisper() -> None:
    module = ModuleType("faster_whisper")

    class ControlledWhisperModel:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def transcribe(self, *args, **kwargs):
            segment = SimpleNamespace(
                start=0.0,
                end=0.3,
                text="controlled speech",
                avg_logprob=-0.05,
                no_speech_prob=0.01,
                words=[],
            )
            info = SimpleNamespace(language="en", language_probability=0.98, duration=0.3)
            return iter([segment]), info

    module.WhisperModel = ControlledWhisperModel
    sys.modules["faster_whisper"] = module


class ControlledTTS:
    def health(self):
        return SimpleNamespace(status="available", message="controlled")

    def synthesize(self, request):
        return TextToSpeechResult(
            output_ref=f"inline://{request.session_id}",
            provider_id="piper",
            voice_id="controlled",
            audio_base64=base64.b64encode(valid_wav(100)).decode("ascii"),
            audio_format="audio/wav",
            duration_ms=100,
        )


def runtime_fixture(*, perception_sink=None):
    directory = tempfile.TemporaryDirectory()
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=Path(directory.name) / "data",
        host="127.0.0.1",
        port=8717,
        default_actor_id="local_owner",
    )
    runtime = create_runtime(settings, voice_perception_sink=perception_sink)
    runtime.provisioning.create_agent(
        AgentCreateRequest(
            agent_id="artemis",
            display_name="Artemis",
            role="orchestrator",
        )
    )
    install_controlled_whisper()
    runtime.speech_adapters._runtime_adapters["piper_tts_adapter"] = ControlledTTS()
    runtime.voice.update_settings(tts_provider_id="piper", tts_voice_id="controlled")
    return directory, settings, runtime


def completed_recording(runtime, session_id: str | None = None, key: str = "audio"):
    recording = runtime.voice.start_recording(
        session_id=session_id,
        conversation_id="voice-conversation" if session_id else None,
        agent_id="artemis" if session_id else None,
        audio_format="audio/wav",
    )
    runtime.voice.append_recording_chunk(
        recording.recording_id,
        valid_wav(),
        sequence=0,
        idempotency_key=key,
    )
    return runtime.voice.complete_recording(recording.recording_id)
