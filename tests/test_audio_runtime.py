from __future__ import annotations

import io
import json
import math
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from factories.audio import ControlledAudioDeviceBackend
from synapse.audio.devices import DeviceRuntime
from synapse.audio.errors import AudioValidationError
from synapse.audio.ingestion import AudioIngestionLimits
from synapse.audio.models import AudioInputRequest, AudioOutputRequest
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.exceptions import ValidationError


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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
            "system": {"name": "Synapse V2 Audio Test", "mode": "test"},
            "models": {"default_provider": "mock", "providers": {"mock": {"model": "test"}}},
        },
    )
    with patch.dict("os.environ", {"SYNAPSE_DEV_MODE": "true"}):
        runtime = create_runtime(settings)
    runtime.audio.devices = DeviceRuntime(ControlledAudioDeviceBackend())
    return directory, settings, runtime


def wav_audio(duration_ms: int = 250, frequency: float = 440.0, amplitude: float = 0.25) -> bytes:
    sample_rate = 48_000
    frame_count = int(sample_rate * duration_ms / 1000)
    frames = b"".join(
        struct.pack(
            "<h",
            int(32767 * amplitude * math.sin(2 * math.pi * frequency * index / sample_rate)),
        )
        for index in range(frame_count)
    )
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(frames)
    return output.getvalue()


class AudioRuntimeTests(unittest.TestCase):
    def test_device_runtime_discovers_and_diagnoses_controlled_hardware(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        devices = runtime.audio.devices.list_devices()
        input_device = next(item for item in devices if item.direction == "input")
        output_device = next(item for item in devices if item.direction == "output")
        input_result = runtime.audio.devices.test_input(input_device.stable_id, duration_ms=100)
        output_result = runtime.audio.devices.test_output(output_device.stable_id, duration_ms=50)

        self.assertTrue(input_device.is_default)
        self.assertEqual(len(input_device.stable_id), 24)
        self.assertTrue(input_result.opened)
        self.assertGreater(input_result.frames_received, 0)
        self.assertTrue(input_result.signal_detected)
        self.assertTrue(output_result.playback_completed)

    def test_device_runtime_reports_removed_device(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        result = runtime.audio.devices.test_input("removed-device")

        self.assertFalse(result.found)
        self.assertFalse(result.opened)
        self.assertIn("removed", result.error or "")

    def test_ingest_wav_normalizes_content_and_calculates_metadata(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        payload = runtime.audio.ingest(wav_audio(), "audio/wav")

        self.assertEqual(payload.mime_type, "audio/wav")
        self.assertEqual(payload.source_mime_type, "audio/wav")
        self.assertEqual(payload.sample_rate, 16_000)
        self.assertEqual(payload.channels, 1)
        self.assertEqual(payload.encoding, "pcm_s16le")
        self.assertGreaterEqual(payload.duration_ms, 240)
        self.assertLessEqual(payload.duration_ms, 260)
        self.assertEqual(len(payload.checksum), 64)
        self.assertGreater(payload.average_volume or 0, 0)
        self.assertGreater(payload.peak_volume or 0, 0)

    def test_ingest_rejects_empty_short_corrupt_and_mime_mismatch(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        cases = [
            (b"", "audio/wav", "invalid_audio"),
            (wav_audio(duration_ms=10), "audio/wav", "audio_too_short"),
            (b"RIFF\x00\x00\x00\x00WAVE", "audio/wav", "invalid_audio"),
            (wav_audio(), "audio/webm", "audio_mime_mismatch"),
        ]
        for content, mime_type, code in cases:
            with self.subTest(code=code):
                with self.assertRaises(AudioValidationError) as raised:
                    runtime.audio.ingest(content, mime_type)
                self.assertEqual(raised.exception.code, code)

    def test_ingest_can_reject_complete_silence(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        with self.assertRaises(AudioValidationError) as raised:
            runtime.audio.ingest(
                wav_audio(amplitude=0.0),
                "audio/wav",
                limits=AudioIngestionLimits(reject_silence=True),
            )

        self.assertEqual(raised.exception.code, "no_speech_detected")

    def test_create_audio_session(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        session = runtime.audio.create_session(agent_id="agent", input_device_id="mock_input")

        self.assertEqual(session.status, "idle")
        self.assertEqual(session.agent_id, "agent")
        self.assertEqual(runtime.audio.get_session(session.session_id).session_id, session.session_id)

    def test_pause_resume_close_session(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        session = runtime.audio.create_session()

        paused = runtime.audio.pause_session(session.session_id)
        resumed = runtime.audio.resume_session(session.session_id)
        closed = runtime.audio.close_session(session.session_id)

        self.assertEqual(paused.status, "paused")
        self.assertEqual(resumed.status, "idle")
        self.assertEqual(closed.status, "closed")

    def test_list_controlled_devices(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        devices = runtime.audio.list_devices()

        device_ids = {device.device_id for device in devices}
        self.assertEqual(len(device_ids), 2)
        self.assertEqual({device.device_type for device in devices}, {"input", "output"})

    def test_register_mock_device(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        device = runtime.audio.register_mock_device("virtual_loopback", "Virtual Loopback", "virtual")

        self.assertEqual(device.device_type, "virtual")
        self.assertTrue(device.metadata["mock"])

    def test_resolve_stt_provider_mock(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        provider = runtime.audio.resolve_stt_provider()

        self.assertEqual(provider.provider_id, "mock_stt")
        self.assertEqual(provider.capability_id, "speech_to_text")

    def test_resolve_tts_provider_mock(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        provider = runtime.audio.resolve_tts_provider()

        self.assertEqual(provider.provider_id, "kokoro")
        self.assertEqual(provider.capability_id, "text_to_speech")

    def test_transcribe_mock_returns_result(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        session = runtime.audio.create_session()

        result = runtime.audio.transcribe_mock(
            AudioInputRequest(session_id=session.session_id, language="pt-BR"),
            "texto falado",
        )

        self.assertEqual(result.text, "texto falado")
        self.assertEqual(result.language, "pt-BR")
        self.assertEqual(result.provider_id, "mock_stt")
        self.assertTrue(result.metadata["mock"])

    def test_transcribe_mock_requires_session_id(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        with self.assertRaisesRegex(ValidationError, "requires a session_id"):
            runtime.audio.transcribe_mock(AudioInputRequest(), "texto falado")

    def test_synthesize_mock_returns_result(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        session = runtime.audio.create_session()

        result = runtime.audio.synthesize_mock(
            AudioOutputRequest(session_id=session.session_id, text="hello", voice_id="mock_voice")
        )

        self.assertEqual(result.provider_id, "mock_tts")
        self.assertEqual(result.voice_id, "mock_voice")
        self.assertTrue(result.output_ref.startswith("mock://tts/"))

    def test_synthesize_uses_global_voice_configuration(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_json(
            runtime.data_dir.root / "agents" / "speaker" / "CONFIG.yaml",
            {"id": "speaker", "name": "Speaker", "role": "assistant", "autonomy": "manual"},
        )
        settings = runtime.voice.update_settings(
            tts_provider_id="mock_tts",
            default_tts_voice="system-default",
            language="en-US",
        )
        provider = runtime.voice.resolve_tts_provider()

        self.assertEqual(provider.provider_id, "mock_tts")
        self.assertEqual(settings.default_tts_voice, "system-default")

    def test_piper_is_explicitly_unavailable_when_not_configured(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        health = runtime.speech_adapters.adapter_health("piper_tts_adapter")

        self.assertIn(health.status, {"unavailable", "unconfigured"})
        with self.assertRaises(Exception):
            runtime.audio.synthesize(
                AudioOutputRequest(
                    session_id="tts-session",
                    text="hello world",
                    provider_id="piper",
                )
            )

    def test_multimodal_event_emitted_when_linked(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        multimodal = runtime.multimodal.create_session(["user"], ["text"])
        session = runtime.audio.create_session(multimodal_session_id=multimodal.session_id)

        runtime.audio.transcribe_mock(AudioInputRequest(session_id=session.session_id), "hello")

        events = runtime.multimodal.list_session_events(multimodal.session_id)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].channel, "voice")
        self.assertEqual(events[0].metadata["audio_session_id"], session.session_id)

    def test_commands(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        session = runtime.audio.create_session()

        sessions = runtime.commands.execute(runtime.context(), "/audio-sessions")
        detail = runtime.commands.execute(runtime.context(), f"/audio-session {session.session_id}")
        devices = runtime.commands.execute(runtime.context(), "/audio-devices")

        self.assertEqual(sessions.status, "ok")
        self.assertEqual(detail.data["session"]["session_id"], session.session_id)
        self.assertEqual(devices.status, "ok")

    def test_api(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"FastAPI test dependencies unavailable: {exc}")

        from synapse.api.routes import router

        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        app = FastAPI()
        app.state.runtime = runtime
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        created = client.post("/api/audio/sessions", json={"agent_id": "agent"})
        session_id = created.json()["session_id"]

        self.assertEqual(created.status_code, 200)
        self.assertEqual(client.get("/api/audio/sessions").status_code, 200)
        self.assertEqual(client.get(f"/api/audio/sessions/{session_id}").status_code, 200)
        self.assertEqual(client.post(f"/api/audio/sessions/{session_id}/pause").json()["status"], "paused")
        self.assertEqual(client.post(f"/api/audio/sessions/{session_id}/resume").json()["status"], "idle")
        self.assertEqual(client.get("/api/audio/devices").status_code, 200)
        write_json(
            settings.data_dir / "agents" / "speaker" / "CONFIG.yaml",
            {"id": "speaker", "name": "Speaker", "role": "assistant", "autonomy": "manual"},
        )
        runtime.voice.update_settings(
            tts_provider_id="mock_tts",
            default_tts_voice="system-default",
            language="en-US",
        )
        self.assertEqual(client.post("/api/audio/mock/transcribe").status_code, 404)
        self.assertEqual(client.post("/api/audio/mock/synthesize").status_code, 404)
        synth = client.post(
            "/api/audio/synthesize",
            json={"session_id": "tts-session", "text": "hello", "agent_id": "speaker"},
        )
        self.assertEqual(synth.status_code, 200)
        self.assertEqual(synth.json()["provider_id"], "mock_tts")
        self.assertIn("audio_base64", synth.json())
        self.assertEqual(client.post(f"/api/audio/sessions/{session_id}/close").json()["status"], "closed")

    def test_health_and_readiness_include_audio(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertTrue(health.audio_runtime_available)
        self.assertEqual(health.audio_provider_unavailable_count, 0)
        self.assertIn("audio.ready", [check.id for check in readiness.checks])

    def test_audio_capabilities_registered(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        capability_ids = {item.capability_id for item in runtime.capabilities.list_capabilities()}

        self.assertIn("audio.session", capability_ids)
        self.assertIn("speech_to_text", capability_ids)
        self.assertIn("text_to_speech", capability_ids)
        self.assertIn("voice_analysis", capability_ids)
