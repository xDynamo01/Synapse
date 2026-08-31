from __future__ import annotations

import base64
import io
import json
import math
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from factories.agents import seed_test_agent
from synapse.audio.models import AudioInputRequest, AudioOutputRequest, TextToSpeechResult
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.data_dir import DataDir
from synapse.providers.models import ProviderManifest
from synapse.speech_adapters.faster_whisper import (
    FasterWhisperSpeechToTextAdapter,
    _suffix_for_audio_format,
)
from synapse.speech_adapters.models import (
    SpeechAdapterCapability,
    SpeechAdapterManifest,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def valid_wav_base64(duration_ms: int = 1200) -> str:
    sample_rate = 16_000
    frames = b"".join(
        struct.pack(
            "<h",
            int(8000 * math.sin(2 * math.pi * 440 * index / sample_rate)),
        )
        for index in range(int(sample_rate * duration_ms / 1000))
    )
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(frames)
    return base64.b64encode(output.getvalue()).decode("ascii")


def runtime_in_tempdir():
    directory = tempfile.TemporaryDirectory()
    settings = Settings(
        project_root=PROJECT_ROOT,
        data_dir=Path(directory.name) / "data",
        host="127.0.0.1",
        port=8717,
        default_actor_id="local_owner",
    )
    with patch.dict("os.environ", {"SYNAPSE_DEV_MODE": "true"}):
        create_runtime(settings)
    write_json(
        settings.data_dir / "config" / "permissions.yaml",
        {"subjects": {"local_owner": ["*"], "user:local_owner": ["*"]}},
    )
    write_json(
        settings.data_dir / "config" / "system.yaml",
        {
            "system": {"name": "Synapse V2 Speech Adapter Test", "mode": "test"},
            "models": {"default_provider": "mock", "providers": {"mock": {"model": "test"}}},
        },
    )
    seed_test_agent(
        settings.data_dir,
        "artemis",
        name="Artemis",
        role="orchestrator",
        can_delegate=True,
        capabilities=["conversation", "voice"],
    )
    with patch.dict("os.environ", {"SYNAPSE_DEV_MODE": "true"}):
        runtime = create_runtime(settings)
    return directory, settings, runtime


def install_fake_faster_whisper() -> None:
    fake_module = ModuleType("faster_whisper")

    class FakeWhisperModel:
        def __init__(
            self,
            model_name: str,
            device: str = "cpu",
            compute_type: str = "int8",
            download_root: str | None = None,
            local_files_only: bool = False,
        ) -> None:
            self.model_name = model_name
            self.device = device
            self.compute_type = compute_type
            self.download_root = download_root
            self.local_files_only = local_files_only

        def transcribe(
            self,
            audio_path: str,
            language: str | None = None,
            vad_filter: bool = True,
            beam_size: int = 1,
            temperature: float = 0.0,
        ):
            segments = [
                SimpleNamespace(
                    start=0.0, end=0.6, text="olá", avg_logprob=-0.05, no_speech_prob=0.01, words=[]
                ),
                SimpleNamespace(
                    start=0.7,
                    end=1.2,
                    text="mundo",
                    avg_logprob=-0.02,
                    no_speech_prob=0.01,
                    words=[],
                ),
            ]
            info = SimpleNamespace(
                language=language or "pt",
                language_probability=0.97,
                duration=1.2,
                audio_path=audio_path,
            )
            return iter(segments), info

    fake_module.WhisperModel = FakeWhisperModel
    sys.modules["faster_whisper"] = fake_module


def install_empty_faster_whisper() -> None:
    fake_module = ModuleType("faster_whisper")

    class EmptyWhisperModel:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def transcribe(self, *args, **kwargs):
            info = SimpleNamespace(language="pt", language_probability=0.99, duration=1.2)
            return iter([]), info

    fake_module.WhisperModel = EmptyWhisperModel
    sys.modules["faster_whisper"] = fake_module


class SpeechAdapterRuntimeTests(unittest.TestCase):
    def test_barge_in_cancels_synthesis_and_starts_recording(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        class ControlledTTS:
            def health(self):
                return SimpleNamespace(status="available", message="controlled")

            def synthesize(self, request):
                return TextToSpeechResult(
                    output_ref=f"inline://{request.session_id}",
                    provider_id="piper",
                    audio_base64=valid_wav_base64(100),
                    audio_format="audio/wav",
                    duration_ms=100,
                )

        runtime.speech_adapters._runtime_adapters["piper_tts_adapter"] = ControlledTTS()
        runtime.voice.update_settings(tts_provider_id="piper")
        session = runtime.voice.create_session("artemis")
        utterance = runtime.voice.queue_utterance(session.session_id, "response")
        synthesis = runtime.voice.synthesize_utterance(
            session.session_id,
            utterance.utterance_id,
            utterance.text,
        )
        runtime.voice.transition_session(session.session_id, "speaking")

        recording = runtime.voice.interrupt_session(session.session_id)
        repeated = runtime.voice.cancel_synthesis(synthesis.synthesis_id)

        self.assertIsNotNone(recording)
        self.assertEqual(runtime.voice.get_session(session.session_id).status, "recording")
        self.assertEqual(repeated.status, "cancelled")
        self.assertFalse(repeated.metadata["provider_cancel_supported"])

    def test_barge_in_disabled_preserves_speaking_state(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        session = runtime.voice.create_session("artemis")
        runtime.voice._set_session_status(session.session_id, "speaking")

        recording = runtime.voice.interrupt_session(
            session.session_id,
            barge_in_enabled=False,
        )

        self.assertIsNone(recording)
        self.assertEqual(runtime.voice.get_session(session.session_id).status, "speaking")

    def test_conversation_mode_runs_two_turns_through_chat_submit_turn(self) -> None:
        previous = sys.modules.get("faster_whisper")
        install_fake_faster_whisper()
        self.addCleanup(
            lambda: (
                sys.modules.__setitem__("faster_whisper", previous)
                if previous is not None
                else sys.modules.pop("faster_whisper", None)
            )
        )
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        class ControlledTTS:
            def health(self):
                return SimpleNamespace(status="available", message="controlled")

            def synthesize(self, request):
                return TextToSpeechResult(
                    output_ref=f"inline://{request.session_id}",
                    provider_id="piper",
                    voice_id="controlled",
                    audio_base64=valid_wav_base64(200),
                    audio_format="audio/wav",
                    duration_ms=200,
                )

        runtime.speech_adapters._runtime_adapters["piper_tts_adapter"] = ControlledTTS()
        runtime.voice.update_settings(tts_provider_id="piper", tts_voice_id="controlled")
        runtime.chat.submit_turn = Mock(
            side_effect=[
                SimpleNamespace(
                    response="Resposta um",
                    conversation_id="voice-conversation",
                    message=SimpleNamespace(correlation_id="corr-1"),
                ),
                SimpleNamespace(
                    response="Resposta dois",
                    conversation_id="voice-conversation",
                    message=SimpleNamespace(correlation_id="corr-2"),
                ),
            ]
        )
        session = runtime.voice.create_session("artemis")
        session = runtime.voice.transition_session(session.session_id, "listening")

        results = []
        for index in range(2):
            runtime.voice.transition_session(session.session_id, "recording")
            recording = runtime.voice.start_recording(
                session_id=session.session_id,
                conversation_id="voice-conversation",
                agent_id="artemis",
                audio_format="audio/wav",
            )
            audio = base64.b64decode(valid_wav_base64())
            runtime.voice.append_recording_chunk(
                recording.recording_id,
                audio,
                sequence=0,
                idempotency_key=f"audio-{index}",
            )
            runtime.voice.complete_recording(recording.recording_id)
            results.append(
                runtime.voice.run_conversation_turn(
                    session.session_id,
                    recording.recording_id,
                    idempotency_key=f"turn-{index}",
                )
            )

        self.assertEqual(runtime.chat.submit_turn.call_count, 2)
        self.assertEqual([result.response for result in results], ["Resposta um", "Resposta dois"])
        self.assertNotEqual(results[0].recording_id, results[1].recording_id)
        self.assertNotEqual(results[0].utterance_id, results[1].utterance_id)
        self.assertNotEqual(results[0].synthesis_id, results[1].synthesis_id)
        self.assertEqual(runtime.voice.get_session(session.session_id).status, "listening")

    def test_voice_message_completes_without_calling_chat(self) -> None:
        previous = sys.modules.get("faster_whisper")
        install_fake_faster_whisper()
        self.addCleanup(
            lambda: (
                sys.modules.__setitem__("faster_whisper", previous)
                if previous is not None
                else sys.modules.pop("faster_whisper", None)
            )
        )
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.chat.local_chat = Mock()
        audio = base64.b64decode(valid_wav_base64())
        recording = runtime.voice.start_recording(audio_format="audio/wav")
        runtime.voice.append_recording_chunk(
            recording.recording_id,
            audio,
            sequence=0,
            idempotency_key="voice-message-audio",
        )
        runtime.voice.complete_recording(recording.recording_id)

        result = runtime.voice.complete_voice_message(recording.recording_id)
        repeated = runtime.voice.complete_voice_message(recording.recording_id)

        self.assertEqual(result.status, "success")
        self.assertEqual(result.text, "ol\u00e1 mundo")
        self.assertEqual(repeated.transcript_id, result.transcript_id)
        self.assertGreater(result.analysis["average_volume"], 0)
        runtime.chat.local_chat.assert_not_called()

    def test_local_voice_analysis_reports_only_objective_metrics(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.speech_adapters.analyze(
            AudioInputRequest(
                audio_base64=valid_wav_base64(),
                audio_format="audio/wav",
            )
        )

        self.assertEqual(result.provider_id, "local_acoustic_analysis")
        self.assertGreater(result.duration_ms, 0)
        self.assertGreater(result.average_volume or 0, 0)
        self.assertGreater(result.peak_volume or 0, 0)
        self.assertIsNone(result.pitch)
        self.assertIsNone(result.confidence)
        self.assertTrue(result.metadata["objective_metrics_only"])

    def test_faster_whisper_empty_result_is_no_speech_not_success(self) -> None:
        previous = sys.modules.get("faster_whisper")
        install_empty_faster_whisper()
        self.addCleanup(
            lambda: (
                sys.modules.__setitem__("faster_whisper", previous)
                if previous is not None
                else sys.modules.pop("faster_whisper", None)
            )
        )
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.audio.transcribe(
            AudioInputRequest(
                audio_base64=valid_wav_base64(),
                audio_format="audio/wav",
                provider_id="faster_whisper",
            )
        )

        self.assertEqual(result.status, "no_speech_detected")
        self.assertEqual(result.text, "")
        self.assertIsNone(result.confidence)

    def test_register_and_list_adapter(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        manifest = runtime.speech_adapters.register_adapter(
            SpeechAdapterManifest(
                adapter_id="local_test_stt",
                provider_id="mock_stt",
                adapter_type="stt",
                name="Local Test STT",
                description="Test adapter",
                version="0.1.0",
                supported_languages=["en-US"],
                supports_streaming=False,
                supports_file_input=False,
                supports_realtime=False,
                requires_gpu=False,
                requires_network=False,
            )
        )

        self.assertEqual(manifest.adapter_id, "local_test_stt")
        self.assertIn(
            "local_test_stt", [item.adapter_id for item in runtime.speech_adapters.list_adapters()]
        )

    def test_list_by_type(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        stt_adapters = runtime.speech_adapters.list_by_type("stt")

        self.assertEqual(
            [item.adapter_id for item in stt_adapters],
            ["faster_whisper_adapter", "mock_stt_adapter"],
        )

    def test_register_capability_and_resolve(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.speech_adapters.register_adapter(
            SpeechAdapterManifest(
                adapter_id="preferred_stt",
                provider_id="mock_stt",
                adapter_type="stt",
                name="Preferred STT",
                description="Test adapter",
                version="0.1.0",
                supported_languages=["en-US"],
                supports_streaming=False,
                supports_file_input=False,
                supports_realtime=False,
                requires_gpu=False,
                requires_network=False,
            )
        )
        runtime.speech_adapters.register_capability(
            SpeechAdapterCapability("preferred_stt", "speech_to_text", 1, True)
        )

        resolution = runtime.speech_adapters.resolve_adapter_for_capability("speech_to_text")

        self.assertEqual(resolution.selected_adapter_id, "preferred_stt")
        self.assertEqual(resolution.selected_provider_id, "mock_stt")

    def test_adapter_disabled_not_selected(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_json(
            settings.data_dir / "config" / "speech_adapter_policy.yaml",
            {
                "speech_adapters": {
                    "disabled_adapters": ["mock_stt_adapter", "faster_whisper_adapter"]
                }
            },
        )

        resolution = runtime.speech_adapters.explain_adapter_resolution("speech_to_text")

        self.assertIsNone(resolution.selected_adapter_id)
        self.assertEqual(resolution.reasons, ["no_eligible_adapter"])

    def test_adapter_health_unconfigured(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        health = runtime.speech_adapters.adapter_health("mock_tts_adapter")

        self.assertEqual(health.status, "unconfigured")
        self.assertEqual(health.provider_id, "mock_tts")

    def test_mock_stt_adapter_returns_deterministic_result(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.speech_adapters.mock_transcribe(
            AudioInputRequest(
                session_id="audio-session",
                provider_id="mock_stt",
                metadata={"text": "deterministic"},
            )
        )

        self.assertEqual(result.text, "deterministic")
        self.assertEqual(result.provider_id, "mock_stt")
        self.assertTrue(result.metadata["mock"])

    def test_faster_whisper_adapter_transcribes_audio(self) -> None:
        previous = sys.modules.get("faster_whisper")
        install_fake_faster_whisper()
        self.addCleanup(
            lambda: (
                sys.modules.__setitem__("faster_whisper", previous)
                if previous is not None
                else sys.modules.pop("faster_whisper", None)
            )
        )
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.audio.transcribe(
            AudioInputRequest(
                session_id=None,
                provider_id="faster_whisper",
                language="pt-BR",
                model="balanced",
                audio_base64=valid_wav_base64(),
                audio_format="audio/wav",
                metadata={"source": "test"},
            )
        )

        self.assertEqual(result.provider_id, "faster_whisper")
        self.assertEqual(result.text, "olá mundo")
        self.assertEqual(len(result.segments), 2)
        self.assertEqual(result.duration_ms, 1200)
        self.assertEqual(result.speech_features.duration_ms, 1200)
        self.assertEqual(result.speech_features.segment_count, 2)
        self.assertEqual(len(result.speech_features.timestamps), 2)
        self.assertEqual(result.speech_features.language_confidence, 0.97)
        self.assertEqual(result.speech_features.provider_metadata["provider"], "faster_whisper")
        adapter = runtime.speech_adapters._runtime_adapters["faster_whisper_adapter"]
        model = next(iter(adapter._models.values()))
        self.assertTrue(model.local_files_only)
        self.assertIsNotNone(result.speech_features.speech_rate)
        self.assertGreaterEqual(result.confidence or 0, 0.0)

    def test_faster_whisper_uses_packaged_tiny_model_when_available(self) -> None:
        previous = sys.modules.get("faster_whisper")
        install_fake_faster_whisper()
        self.addCleanup(
            lambda: (
                sys.modules.__setitem__("faster_whisper", previous)
                if previous is not None
                else sys.modules.pop("faster_whisper", None)
            )
        )
        with tempfile.TemporaryDirectory() as temporary:
            adapter = FasterWhisperSpeechToTextAdapter(
                SpeechAdapterManifest(
                    adapter_id="faster_whisper_adapter",
                    provider_id="faster_whisper",
                    adapter_type="stt",
                    name="Faster Whisper",
                    description="Packaged STT adapter.",
                    version="1.0.0",
                    supported_languages=["pt-BR"],
                    supports_streaming=False,
                    supports_file_input=True,
                    supports_realtime=False,
                    requires_gpu=False,
                    requires_network=False,
                ),
                DataDir(Path(temporary) / "data"),
            )

            result = adapter.transcribe(
                AudioInputRequest(
                    provider_id="faster_whisper",
                    language="pt-BR",
                    model="tiny",
                    audio_base64=valid_wav_base64(),
                    audio_format="audio/wav",
                )
            )

            model = next(iter(adapter._models.values()))
            self.assertTrue(model.local_files_only)
            self.assertTrue(Path(model.model_name).is_dir())
            self.assertEqual(Path(model.model_name).name, "tiny")
            self.assertEqual(result.metadata["model"], "tiny")

    def test_provider_metadata_selects_faster_whisper_factory(self) -> None:
        previous = sys.modules.get("faster_whisper")
        install_fake_faster_whisper()
        self.addCleanup(
            lambda: (
                sys.modules.__setitem__("faster_whisper", previous)
                if previous is not None
                else sys.modules.pop("faster_whisper", None)
            )
        )
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        runtime.providers.registry.register_provider(
            ProviderManifest(
                provider_id="custom_stt",
                name="Custom STT Provider",
                description="Custom STT provider using provider metadata.",
                provider_type="stt",
                capabilities=["speech_to_text"],
                version="1.0.0",
                enabled=True,
                local_only=True,
                requires_network=False,
                requires_gpu=False,
                supported_platforms=["windows", "linux", "darwin"],
                metadata={"adapter_factory": "faster_whisper", "executes_real_provider": True},
            )
        )
        runtime.speech_adapters.register_adapter(
            SpeechAdapterManifest(
                adapter_id="custom_stt_adapter",
                provider_id="custom_stt",
                adapter_type="stt",
                name="Custom STT Adapter",
                description="Adapter resolved from provider metadata.",
                version="0.1.0",
                supported_languages=["pt-BR"],
                supports_streaming=False,
                supports_file_input=True,
                supports_realtime=False,
                requires_gpu=False,
                requires_network=False,
            )
        )
        runtime.speech_adapters.register_capability(
            SpeechAdapterCapability("custom_stt_adapter", "speech_to_text", 5, True)
        )

        result = runtime.audio.transcribe(
            AudioInputRequest(
                provider_id="custom_stt",
                language="pt-BR",
                model="balanced",
                audio_base64=valid_wav_base64(),
                audio_format="audio/wav",
            )
        )

        self.assertEqual(result.provider_id, "custom_stt")
        self.assertEqual(result.text, "olá mundo")

    def test_audio_transcribe_api_uses_faster_whisper(self) -> None:
        previous = sys.modules.get("faster_whisper")
        install_fake_faster_whisper()
        self.addCleanup(
            lambda: (
                sys.modules.__setitem__("faster_whisper", previous)
                if previous is not None
                else sys.modules.pop("faster_whisper", None)
            )
        )
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        result = client.post(
            "/api/audio/transcribe",
            json={
                "audio_base64": valid_wav_base64(),
                "audio_format": "audio/wav",
                "language": "pt-BR",
                "provider_id": "faster_whisper",
                "model": "balanced",
            },
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["text"], "olá mundo")
        self.assertEqual(result.json()["speech_features"]["duration_ms"], 1200)
        self.assertEqual(result.json()["speech_features"]["segment_count"], 2)

    def test_voice_conversation_turn_composes_stt_chat_and_context(self) -> None:
        previous = sys.modules.get("faster_whisper")
        install_fake_faster_whisper()
        self.addCleanup(
            lambda: (
                sys.modules.__setitem__("faster_whisper", previous)
                if previous is not None
                else sys.modules.pop("faster_whisper", None)
            )
        )
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        runtime.chat.local_chat = Mock(
            return_value=SimpleNamespace(conversation_id="voice-conversation", response="Olá!")
        )
        runtime.context_fusion.build_conversation_context = Mock(
            return_value=SimpleNamespace(
                snapshot=SimpleNamespace(
                    interaction_context=SimpleNamespace(context_id="fused-context")
                )
            )
        )
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")

        response = TestClient(app).post(
            "/api/voice/conversation/turn",
            json={
                "audio_base64": valid_wav_base64(),
                "audio_format": "audio/wav",
                "language": "pt-BR",
                "provider_id": "faster_whisper",
                "model": "balanced",
                "auto_respond": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["transcript"], "olá mundo")
        self.assertEqual(response.json()["response"], "Olá!")
        self.assertEqual(response.json()["conversation_id"], "voice-conversation")
        self.assertEqual(response.json()["context_id"], "fused-context")
        runtime.chat.local_chat.assert_called_once()
        runtime.context_fusion.build_conversation_context.assert_called_once_with(
            "voice-conversation"
        )

    def test_mock_tts_adapter_returns_deterministic_result(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.speech_adapters.mock_synthesize(
            AudioOutputRequest(session_id="audio-session", text="hello", voice_id="voice")
        )

        self.assertEqual(result.output_ref, "mock://speech-adapter/audio-session")
        self.assertEqual(result.provider_id, "mock_tts")
        self.assertEqual(result.metadata["text"], "hello")

    def test_commands(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        adapters = runtime.commands.execute(runtime.context(), "/speech-adapters")
        adapter = runtime.commands.execute(runtime.context(), "/speech-adapter mock_stt_adapter")
        health = runtime.commands.execute(runtime.context(), "/speech-adapter-health")
        resolution = runtime.commands.execute(
            runtime.context(),
            "/speech-adapter-resolve speech_to_text",
        )

        self.assertEqual(adapters.status, "ok")
        self.assertEqual(adapter.data["adapter"]["adapter_id"], "mock_stt_adapter")
        self.assertEqual(health.status, "ok")
        self.assertEqual(
            resolution.data["resolution"]["selected_adapter_id"],
            "faster_whisper_adapter",
        )

    def test_api(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        self.assertEqual(client.get("/api/speech-adapters").status_code, 200)
        self.assertEqual(
            client.get("/api/speech-adapters/mock_stt_adapter").json()["adapter_id"],
            "mock_stt_adapter",
        )
        self.assertEqual(client.get("/api/speech-adapters/health").status_code, 200)
        self.assertEqual(
            client.get("/api/speech-adapters/resolve/speech_to_text").json()["selected_adapter_id"],
            "faster_whisper_adapter",
        )

    def test_health_and_readiness_include_speech_adapters(self) -> None:
        previous = sys.modules.get("faster_whisper")
        install_fake_faster_whisper()
        self.addCleanup(
            lambda: (
                sys.modules.__setitem__("faster_whisper", previous)
                if previous is not None
                else sys.modules.pop("faster_whisper", None)
            )
        )
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertTrue(health.speech_adapter_runtime_available)
        self.assertEqual(health.speech_adapters_unavailable_count, 0)
        self.assertIn("speech_adapters.ready", [check.id for check in readiness.checks])


class SpeechAdapterAudioFormatTests(unittest.TestCase):
    def test_audio_format_suffix_normalizes_codec_parameters(self) -> None:
        self.assertEqual(_suffix_for_audio_format("audio/webm;codecs=opus"), ".webm")
        self.assertEqual(_suffix_for_audio_format("audio/ogg;codecs=opus"), ".ogg")
        self.assertEqual(_suffix_for_audio_format("audio/wav"), ".wav")


if __name__ == "__main__":
    unittest.main()
