from __future__ import annotations

import base64
import hashlib
import inspect
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
from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.core.exceptions import ValidationError
from synapse.speech_adapters.models import SpeechAdapterHealth
from synapse.tools.models import ToolExecutionRequest


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
            "system": {"name": "Synapse V2 Voice Test", "mode": "test"},
            "models": {"default_provider": "mock", "providers": {"mock": {"model": "test"}}},
        },
    )
    write_json(
        settings.data_dir / "agents" / "artemis" / "CONFIG.yaml",
        {"id": "artemis", "name": "Artemis", "role": "voice test", "autonomy": "manual"},
    )
    write_json(
        settings.data_dir / "agents" / "researcher" / "CONFIG.yaml",
        {"id": "researcher", "name": "Researcher", "role": "voice test", "autonomy": "manual"},
    )
    with patch.dict("os.environ", {"SYNAPSE_DEV_MODE": "true"}):
        runtime = create_runtime(settings)
    runtime.audio.devices = DeviceRuntime(ControlledAudioDeviceBackend())
    return directory, settings, runtime


def input_device_id(runtime) -> str:
    return next(device.device_id for device in runtime.audio.list_devices() if device.device_type == "input")


def valid_wav(duration_ms: int = 250) -> bytes:
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


def write_voice_pack(
    data_dir: Path,
    *,
    voice_count: int = 6,
    corrupt_index: int | None = None,
) -> dict:
    pack_root = data_dir / "voice" / "voice-packs" / "default"
    asset_root = pack_root / "assets"
    asset_root.mkdir(parents=True, exist_ok=True)
    voices = []
    for index in range(voice_count):
        voice_id = f"synapse-default-voice-{index + 1}"
        asset_path = asset_root / f"{voice_id}.onnx"
        asset_path.write_bytes(f"voice asset {index + 1}".encode("utf-8"))
        checksum = "0" * 64 if corrupt_index == index else hashlib.sha256(asset_path.read_bytes()).hexdigest()
        voices.append(
            {
                "voice_id": voice_id,
                "display_name": f"Synapse Voice {index + 1}",
                "language": "Portuguese",
                "locale": "pt-BR",
                "voice_profile": {
                    "gender": "male" if index < 3 else "female",
                    "style": f"profile-{index + 1}",
                },
                "provider": "piper",
                "engine": "piper",
                "asset_reference": f"voice/voice-packs/default/assets/{voice_id}.onnx",
                "version": "1.0.0",
                "checksum": checksum,
                "license": "MIT",
                "provenance": "test fixture",
                "default": index == 3,
            }
        )
    manifest = {
        "pack_id": "synapse-default",
        "display_name": "Synapse Default Voice Pack",
        "version": "1.0.0",
        "provider": "piper",
        "engine": "piper",
        "expected_voice_count": 6,
        "voices": voices,
    }
    write_json(pack_root / "voice-pack.json", manifest)
    return manifest


class VoiceRuntimeTests(unittest.TestCase):
    def test_voice_pack_discovery_requires_six_usable_checksum_verified_voices(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_voice_pack(settings.data_dir)

        packs = runtime.voice.list_voice_packs()
        voices = runtime.voice.list_tts_voices()
        pack = next(item for item in packs if item.pack_id == "synapse-default")
        fixture_voices = [voice for voice in voices if voice.voice_id.startswith("synapse-default-voice-")]

        self.assertEqual(pack.status, "ready")
        self.assertEqual(len(fixture_voices), 6)
        self.assertEqual(sum(1 for voice in fixture_voices if voice.voice_profile["gender"] == "male"), 3)
        self.assertEqual(sum(1 for voice in fixture_voices if voice.voice_profile["gender"] == "female"), 3)
        self.assertTrue(all(voice.usable for voice in fixture_voices))
        self.assertTrue(all(voice.provider == "piper" for voice in fixture_voices))

    def test_packaged_default_voice_pack_contains_six_usable_redistributable_voices(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        pack = next(
            item
            for item in runtime.voice.list_voice_packs()
            if item.pack_id == "synapse-default-v0.01"
        )

        self.assertEqual(pack.status, "ready")
        self.assertEqual(len(pack.voices), 6)
        self.assertEqual(sum(1 for voice in pack.voices if voice.voice_profile["gender"] == "masculine"), 3)
        self.assertEqual(sum(1 for voice in pack.voices if voice.voice_profile["gender"] == "feminine"), 3)
        self.assertTrue(all(voice.usable for voice in pack.voices))
        self.assertTrue(all(voice.asset_reference.startswith("resource://voice/") for voice in pack.voices))
        self.assertTrue(all(voice.license.lower() in {"public domain", "cc0"} for voice in pack.voices))

    def test_voice_pack_corrupt_asset_is_not_usable(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_voice_pack(settings.data_dir, corrupt_index=2)

        pack = runtime.voice.list_voice_packs()[0]
        corrupt = next(voice for voice in pack.voices if voice.voice_id == "synapse-default-voice-3")

        self.assertEqual(pack.status, "incomplete")
        self.assertFalse(corrupt.usable)
        self.assertEqual(corrupt.status, "corrupt")
        self.assertEqual(corrupt.reason, "voice_asset_checksum_mismatch")

    def test_default_tts_voice_persists_as_logical_voice_id(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        manifest = write_voice_pack(settings.data_dir)
        selected_voice_id = manifest["voices"][4]["voice_id"]

        updated = runtime.voice.update_settings(default_tts_voice=selected_voice_id)
        reloaded = create_runtime(settings).voice.get_settings()

        self.assertEqual(updated.default_tts_voice, selected_voice_id)
        self.assertEqual(reloaded.default_tts_voice, selected_voice_id)

    def test_voice_retention_dry_run_cleanup_and_idempotency(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        recording = runtime.voice.create_recording(
            audio_base64=base64.b64encode(valid_wav()).decode("ascii"),
            audio_format="wav",
            transcript="retained transcript",
        )
        audio_path = runtime.data_dir.resolve(recording.audio_ref or "")
        self.assertIsNone(recording.audio_ref)

        dry_run = runtime.voice.cleanup_voice_storage(dry_run=True)
        cleaned = runtime.voice.cleanup_voice_storage()
        repeated = runtime.voice.cleanup_voice_storage()

        self.assertEqual(dry_run.recordings_deleted, 0)
        self.assertTrue(audio_path.exists())
        self.assertEqual(cleaned.recordings_deleted, 0)
        self.assertEqual(cleaned.reclaimed_bytes, 0)
        self.assertEqual(repeated.recordings_deleted, 0)
        self.assertEqual(runtime.voice.get_recording(recording.recording_id).transcript, "retained transcript")

    def test_voice_session_state_machine_validates_transition_and_revision(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        session = runtime.voice.create_session("artemis")

        listening = runtime.voice.transition_session(
            session.session_id,
            "listening",
            expected_revision=session.revision,
        )
        recording = runtime.voice.transition_session(
            session.session_id,
            "recording",
            expected_revision=listening.revision,
        )
        same = runtime.voice.transition_session(session.session_id, "recording")

        self.assertEqual(listening.previous_state, "idle")
        self.assertEqual(recording.previous_state, "listening")
        self.assertEqual(same.revision, recording.revision)
        with self.assertRaises(ValidationError):
            runtime.voice.transition_session(session.session_id, "speaking")
        with self.assertRaises(ValidationError):
            runtime.voice.transition_session(
                session.session_id,
                "processing",
                expected_revision=1,
            )

    def test_recording_lifecycle_sequence_idempotency_complete_cancel_and_delete(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        audio = valid_wav()

        recording = runtime.voice.start_recording(audio_format="audio/wav")
        first = runtime.voice.append_recording_chunk(
            recording.recording_id,
            audio[:100],
            sequence=0,
            idempotency_key="chunk-0",
            expected_revision=recording.revision,
        )
        duplicate = runtime.voice.append_recording_chunk(
            recording.recording_id,
            audio[:100],
            sequence=0,
            idempotency_key="chunk-0",
        )
        second = runtime.voice.append_recording_chunk(
            recording.recording_id,
            audio[100:],
            sequence=1,
            idempotency_key="chunk-1",
            expected_revision=first.revision,
        )
        completed = runtime.voice.complete_recording(recording.recording_id)
        completed_again = runtime.voice.complete_recording(recording.recording_id)

        self.assertEqual(duplicate.revision, first.revision)
        self.assertEqual(second.chunks, 2)
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed_again.revision, completed.revision)
        self.assertGreater(completed.duration_ms or 0, 0)
        self.assertEqual(len(completed.checksum or ""), 64)
        self.assertFalse(Path(completed.audio_ref or "").is_absolute())

        cancelled = runtime.voice.cancel_recording(
            runtime.voice.start_recording(audio_format="audio/wav").recording_id
        )
        deleted = runtime.voice.delete_recording(cancelled.recording_id)
        self.assertEqual(deleted.status, "deleted")

    def test_recording_rejects_out_of_order_chunk(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        recording = runtime.voice.start_recording(audio_format="audio/wav")

        with self.assertRaises(ValidationError):
            runtime.voice.append_recording_chunk(
                recording.recording_id,
                b"chunk",
                sequence=1,
                idempotency_key="wrong-order",
            )

    def test_legacy_piper_stt_settings_fall_back_to_faster_whisper(self) -> None:
        directory, settings, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        write_json(
            settings.data_dir / "voice" / "settings.yaml",
            {
                "provider_id": "piper",
                "device_id": None,
                "language": "pt-BR",
                "model": "auto",
                "tts_provider_id": "piper",
                "tts_voice_id": None,
                "tts_speed": None,
                "enabled": True,
                "metadata": {}
            },
        )

        loaded = runtime.voice.get_settings()

        self.assertEqual(loaded.provider_id, "faster_whisper")
        self.assertEqual(loaded.stt_provider_id, "faster_whisper")
        self.assertEqual(loaded.tts_provider_id, "piper")

    def test_create_voice_session(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        session = runtime.voice.create_session("artemis")

        self.assertEqual(session.agent_id, "artemis")
        self.assertEqual(session.status, "idle")
        self.assertFalse(hasattr(session, "embodiment_id"))
        self.assertFalse(hasattr(session, "avatar_session_id"))
        self.assertFalse(
            (runtime.data_dir.root / "voice" / "sessions" / f"{session.session_id}.yaml").exists()
        )
        persisted = runtime.voice.journal.replay(f"session:{session.session_id}").records[-1].payload
        self.assertNotIn("embodiment_id", persisted)
        self.assertNotIn("avatar_session_id", persisted)

    def test_list_sessions(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        first = runtime.voice.create_session("artemis")
        second = runtime.voice.create_session("researcher")

        session_ids = {session.session_id for session in runtime.voice.list_sessions()}

        self.assertEqual(session_ids, {first.session_id, second.session_id})

    def test_queue_and_list_utterances(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        session = runtime.voice.create_session("artemis")

        utterance = runtime.voice.queue_utterance(session.session_id, "Hello there", priority=10)
        utterances = runtime.voice.list_utterances(session.session_id)

        self.assertEqual(utterance.state, "pending")
        self.assertEqual(utterances[0].text, "Hello there")
        self.assertEqual(runtime.voice.get_session(session.session_id).status, "queued")

    def test_update_states(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        session = runtime.voice.create_session("artemis")
        utterance = runtime.voice.queue_utterance(session.session_id, "Hello")

        ready = runtime.voice.mark_ready(utterance.utterance_id)
        completed = runtime.voice.mark_completed(utterance.utterance_id)

        self.assertEqual(ready.state, "ready")
        self.assertEqual(completed.state, "completed")
        self.assertEqual(runtime.voice.get_session(session.session_id).status, "idle")

    def test_summary_and_mock_provider_resolution(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.voice.update_settings(tts_provider_id="mock_tts")
        session = runtime.voice.create_session("artemis")

        provider = runtime.voice.resolve_tts_provider(session.session_id)
        summary = runtime.voice.summarize_session(session.session_id)

        self.assertEqual(provider.provider_id, "mock_tts")
        self.assertEqual(provider.state, "configured")
        self.assertTrue(provider.metadata["mock"])
        self.assertIn("text_to_speech", summary.provider_status)
        self.assertFalse(summary.metadata["executes_real_provider"])
        self.assertFalse(summary.metadata["plays_audio"])

    def test_provider_absent_is_reported(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.voice.update_settings(tts_provider_id="missing_tts_provider")
        session = runtime.voice.create_session("artemis")

        summary = runtime.voice.summarize_session(session.session_id)

        self.assertEqual(summary.provider_status["text_to_speech"]["state"], "unavailable")
        self.assertEqual(runtime.voice.provider_unavailable_count(), 1)

    def test_default_voice_configuration_is_global_and_explicit(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        settings = runtime.voice.get_settings()

        self.assertEqual(settings.schema_version, 3)
        self.assertEqual(settings.stt_provider_id, "faster_whisper")
        self.assertEqual(settings.stt_model, "tiny")
        self.assertEqual(settings.tts_provider_id, "piper")
        self.assertEqual(settings.preferred_voice_gender, "female")
        self.assertNotIn("voice_profile_id", inspect.signature(runtime.voice.queue_utterance).parameters)

    def test_provider_resolution_has_no_embodiment_dependency_or_fallback(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.voice.update_settings(tts_provider_id="missing_tts_provider")

        selection = runtime.voice.resolve_tts_provider()

        self.assertEqual(selection.state, "unavailable")
        self.assertIsNone(selection.provider_id)
        self.assertFalse(hasattr(runtime.voice, "embodiment"))
        self.assertFalse(hasattr(runtime.voice, "avatar"))

    def test_stt_resolution_uses_exact_global_configuration(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.voice.update_settings(stt_provider_id="mock_stt")

        selection = runtime.voice.resolve_stt_provider()

        self.assertEqual(selection.provider_id, "mock_stt")
        self.assertEqual(selection.state, "configured")

    def test_degraded_provider_remains_degraded(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        runtime.voice.update_settings(tts_provider_id="mock_tts")
        degraded = SpeechAdapterHealth(
            adapter_id="mock_tts_adapter",
            provider_id="mock_tts",
            status="degraded",
            checked_at="2026-01-01T00:00:00+00:00",
        )

        with patch.object(runtime.speech_adapters, "adapter_health", return_value=degraded):
            selection = runtime.voice.resolve_tts_provider()

        self.assertEqual(selection.state, "degraded")

    def test_speaking_fact_is_owned_by_voice(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        voice_session = runtime.voice.create_session("artemis")
        utterance = runtime.voice.queue_utterance(voice_session.session_id, "Hello")

        runtime.voice.mark_ready(utterance.utterance_id)
        speaking = runtime.voice.get_session(voice_session.session_id)
        runtime.voice.mark_completed(utterance.utterance_id)
        idle = runtime.voice.get_session(voice_session.session_id)

        self.assertEqual(speaking.status, "speaking")
        self.assertEqual(idle.status, "idle")

    def test_legacy_visual_bindings_are_read_only_and_discarded(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        session = runtime.voice.create_session("artemis")
        restored = runtime.voice.get_session(session.session_id)
        self.assertFalse(hasattr(restored, "embodiment_id"))
        runtime.voice.transition_session(session.session_id, "listening")
        rewritten = runtime.voice.journal.replay(f"session:{session.session_id}").records[-1].payload
        self.assertNotIn("embodiment_id", rewritten)

    def test_commands(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        session = runtime.voice.create_session("artemis")

        sessions = runtime.commands.execute(runtime.context(), "/voice-sessions")
        detail = runtime.commands.execute(runtime.context(), f"/voice-session {session.session_id}")
        queued = runtime.commands.execute(
            runtime.context(),
            f'/voice-queue {session.session_id} "Hello world"',
        )
        utterances = runtime.commands.execute(
            runtime.context(),
            f"/voice-utterances {session.session_id}",
        )

        self.assertEqual(sessions.status, "ok")
        self.assertEqual(detail.data["summary"]["session"]["session_id"], session.session_id)
        self.assertEqual(queued.data["utterance"]["text"], "Hello world")
        self.assertEqual(len(utterances.data["utterances"]), 1)

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
        device_id = input_device_id(runtime)

        created = client.post("/api/voice/sessions", json={"agent_id": "artemis"})
        session_id = created.json()["session_id"]
        queued = client.post(
            f"/api/voice/sessions/{session_id}/queue",
            json={"text": "Hello from API"},
        )

        self.assertEqual(created.status_code, 200)
        self.assertEqual(client.get("/api/voice/sessions").status_code, 200)
        self.assertEqual(client.get(f"/api/voice/sessions/{session_id}").status_code, 200)
        self.assertEqual(queued.json()["text"], "Hello from API")
        self.assertEqual(
            len(client.get(f"/api/voice/sessions/{session_id}/utterances").json()),
            1,
        )
        self.assertEqual(client.post(f"/api/voice/sessions/{session_id}/pause").json()["status"], "paused")
        self.assertEqual(client.post(f"/api/voice/sessions/{session_id}/resume").json()["status"], "queued")
        self.assertEqual(client.post(f"/api/voice/sessions/{session_id}/close").json()["status"], "closed")
        self.assertEqual(client.get("/api/voice/settings").status_code, 200)
        self.assertEqual(client.get("/api/voice/devices").status_code, 200)
        self.assertEqual(client.get("/api/voice/providers").status_code, 200)
        self.assertEqual(client.get("/api/voice/packs").status_code, 200)
        self.assertEqual(client.get("/api/voice/voices").status_code, 200)
        self.assertEqual(client.post(f"/api/voice/devices/{device_id}/test").status_code, 200)
        recording = client.post(
            "/api/voice/recordings",
            json={
                "device_id": device_id,
                "provider_id": "mock_stt_adapter",
                "language": "pt-BR",
                "audio_base64": base64.b64encode(b"audio").decode("ascii"),
                "transcript": "audio salvo",
            },
        ).json()
        self.assertEqual(client.get("/api/voice/recordings").status_code, 200)
        self.assertEqual(client.get(f"/api/voice/recordings/{recording['recording_id']}").status_code, 200)
        self.assertEqual(
            client.post(
                f"/api/voice/recordings/{recording['recording_id']}/transcribe",
                json={"transcript": "texto final", "provider_id": "mock_stt_adapter"},
            ).json()["transcript"],
            "texto final",
        )

    def test_voice_settings_devices_recordings_and_transcription(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        device_id = input_device_id(runtime)

        settings = runtime.voice.update_settings(
            provider_id="mock_stt_adapter",
            device_id=device_id,
            language="pt-BR",
            model="mock-stt",
        )
        devices = runtime.voice.list_devices()
        providers = runtime.voice.list_providers()
        recording = runtime.voice.create_recording(
            device_id=device_id,
            provider_id="mock_stt_adapter",
            language="pt-BR",
            model="mock-stt",
            audio_base64=base64.b64encode(b"fake-audio").decode("ascii"),
        )
        transcription = runtime.voice.transcribe_recording(
            recording.recording_id,
            transcript="ola mundo",
            provider_id="mock_stt_adapter",
            language="pt-BR",
        )

        self.assertTrue(settings.enabled)
        self.assertTrue(any(device.device_id == device_id for device in devices))
        self.assertTrue(any(provider.adapter_type == "stt" for provider in providers))
        self.assertEqual(recording.status, "recorded")
        self.assertEqual(transcription.transcript, "ola mundo")
        self.assertIsNone(runtime.voice.get_recording(recording.recording_id).audio_ref)

    def test_voice_model_presets_translate_to_backend_models(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        self.assertEqual(runtime.voice.resolve_model_name("auto"), "small")
        self.assertEqual(runtime.voice.resolve_model_name("fast"), "tiny")
        self.assertEqual(runtime.voice.resolve_model_name("balanced"), "base")
        self.assertEqual(runtime.voice.resolve_model_name("high_quality"), "large-v3")

    def test_voice_transcribe_tool_is_read_only(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)
        device_id = input_device_id(runtime)
        recording = runtime.voice.create_recording(
            device_id=device_id,
            provider_id="mock_stt_adapter",
            transcript="transcripto salvo",
        )

        result = runtime.tool_runtime.execute(
            ToolExecutionRequest(
                tool_id="voice.transcribe",
                caller="local_owner",
                caller_type="user",
                arguments={"recording_id": recording.recording_id},
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output["transcript"], "transcripto salvo")

    def test_health_and_readiness_include_voice(self) -> None:
        directory, _, runtime = runtime_in_tempdir()
        self.addCleanup(directory.cleanup)

        health = runtime.health.summary()
        readiness = runtime.readiness.evaluate()

        self.assertTrue(health.voice_runtime_available)
        self.assertEqual(health.voice_provider_unavailable_count, 0)
        self.assertIn("voice.ready", [check.id for check in readiness.checks])


if __name__ == "__main__":
    unittest.main()
