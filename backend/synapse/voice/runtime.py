from __future__ import annotations

import base64
import hashlib
import logging
import os
import re
from binascii import Error as BinasciiError
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from synapse.agents.registry import AgentRegistry
from synapse.audio.models import AudioDevice, AudioInputRequest, AudioOutputRequest
from synapse.audio.runtime import AudioRuntime
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound, ValidationError
from synapse.core.package_resources import (
    package_resource_reference,
    packaged_resources_root,
    resolve_package_resource_reference,
)
from synapse.core.permissions import PermissionContext
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.providers.runtime import ProviderRuntime
from synapse.retrieval_intent import detect_voice_retrieval_intent
from synapse.speech_adapters.runtime import SpeechAdapterRuntime
from synapse.voice.models import (
    VOICE_MODEL_PRESETS,
    VOICE_PROVIDER_SELECTION_STATES,
    VOICE_RECORDING_STATUSES,
    VOICE_SESSION_STATUSES,
    VOICE_UTTERANCE_STATES,
    VoiceCleanupReport,
    VoiceConversationTurnResult,
    VoiceMessageResult,
    VoicePackEntry,
    VoicePackManifest,
    VoicePlaybackState,
    VoiceProviderSelection,
    VoiceProviderSummary,
    VoiceRecording,
    VoiceSession,
    VoiceSettings,
    VoiceSummary,
    VoiceSynthesis,
    VoiceTranscription,
    VoiceUtterance,
)
from synapse.voice.perception import (
    NullVoicePerceptionSink,
    VoicePerceptionSignal,
    VoicePerceptionSink,
)
from synapse.voice.persistence_models import VoiceRecordDraft, canonical_json
from synapse.voice.sqlite_persistence import SQLiteVoiceJournal
from synapse.voice.vad import WebRTCVADProvider

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from synapse.chat.runtime import ChatRuntime


class VoiceRuntime:
    SESSION_TRANSITIONS: dict[str, set[str]] = {
        "idle": {"listening", "paused", "cancelling", "closed"},
        "listening": {"recording", "paused", "cancelling", "closed", "error"},
        "recording": {"processing", "paused", "cancelling", "closed", "error"},
        "processing": {"thinking", "paused", "cancelling", "closed", "error"},
        "thinking": {"speaking", "paused", "cancelling", "closed", "error"},
        "speaking": {"listening", "recording", "paused", "cancelling", "closed", "error"},
        "paused": {"idle", "listening", "cancelling", "closed", "error"},
        "cancelling": {"cancelled", "error"},
        "cancelled": {"closed"},
        "error": {"paused", "closed"},
        "queued": {"speaking", "paused", "cancelling", "closed", "failed"},
        "failed": {"paused", "closed"},
        "reconciliation_required": {"idle", "listening", "cancelling", "closed", "error"},
        "closed": set(),
    }

    def __init__(
        self,
        data_dir: DataDir,
        agents: AgentRegistry,
        providers: ProviderRuntime,
        events: EventBus,
        audio: AudioRuntime | None = None,
        speech_adapters: SpeechAdapterRuntime | None = None,
        default_actor_id: str = "local_owner",
        perception_sink: VoicePerceptionSink | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.agents = agents
        # Retained only for constructor compatibility until legacy wiring is removed.
        # Provider selection is owned by Voice and uses speech adapter capabilities.
        _ = providers
        self.events = events
        self.audio = audio
        self.speech_adapters = speech_adapters
        self.chat: ChatRuntime | None = None
        self.default_actor_id = default_actor_id
        self.perception_sink = perception_sink or NullVoicePerceptionSink()
        self.settings_path = self.data_dir.resolve("voice/settings.yaml")
        self.recordings_root = self.data_dir.resolve("voice/recordings")
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.recordings_root.mkdir(parents=True, exist_ok=True)
        self._transient_audio_refs: dict[str, str] = {}
        self.journal = SQLiteVoiceJournal(self.data_dir.resolve("voice/voice-journal-v1.sqlite3"))
        self._import_legacy_persistence_if_needed()
        self._recover_interrupted_sessions()

    def create_session(
        self,
        agent_id: str,
        conversation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> VoiceSession:
        normalized_agent_id = agent_id.strip().lower()
        self.agents.get(normalized_agent_id)
        session = VoiceSession(
            agent_id=normalized_agent_id,
            session_id=session_id or VoiceSession(agent_id=normalized_agent_id).session_id,
            conversation_id=conversation_id,
            settings_snapshot=asdict(self.get_settings()),
            metadata=metadata or {},
        )
        self._write_session(session)
        self.events.emit("voice.session.created", "voice", asdict(session))
        return session

    def transition_session(
        self,
        session_id: str,
        target_state: str,
        *,
        expected_revision: int | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> VoiceSession:
        if target_state not in VOICE_SESSION_STATUSES:
            raise ValidationError(f"Invalid voice session state: {target_state}")
        session = self.get_session(session_id)
        if expected_revision is not None and session.revision != expected_revision:
            raise ValidationError("Voice session revision conflict.")
        if session.status == target_state:
            return session
        allowed = self.SESSION_TRANSITIONS.get(session.status, set())
        if target_state not in allowed:
            raise ValidationError(
                f"Invalid voice session transition: {session.status} -> {target_state}"
            )
        updated = replace(
            session,
            status=target_state,
            previous_state=session.status,
            revision=session.revision + 1,
            updated_at=_now(),
            closed_at=_now() if target_state == "closed" else session.closed_at,
            last_error=error if target_state in {"error", "failed"} else session.last_error,
            metadata={**session.metadata, **(metadata or {})},
        )
        self._write_session(updated)
        self.events.emit(
            f"voice.session.{target_state}",
            "voice",
            {
                "session_id": session_id,
                "previous_state": session.status,
                "state": target_state,
                "revision": updated.revision,
                "error": error,
            },
        )
        perception_type = {
            "recording": "speech.started",
            "processing": "speech.ended",
            "paused": "voice.pause",
        }.get(target_state)
        if perception_type:
            self._emit_perception_signal(
                VoicePerceptionSignal(
                    type=perception_type,
                    session_id=updated.session_id,
                    conversation_id=updated.conversation_id,
                    utterance_id=updated.active_utterance_id,
                    recording_id=updated.active_recording_id,
                    values={"previous_state": session.status},
                    provenance="voice.session_state_machine",
                    metadata={"state": target_state},
                )
            )
        return updated

    def get_session(self, session_id: str) -> VoiceSession:
        return self._read_session(session_id)

    def list_sessions(self, status: str | None = None) -> list[VoiceSession]:
        if status and status not in VOICE_SESSION_STATUSES:
            raise ValidationError(f"Invalid voice session status: {status}")
        sessions = [
            self._read_session(stream_id.removeprefix("session:"))
            for stream_id in self.journal.stream_ids("session:")
        ]
        if status:
            sessions = [session for session in sessions if session.status == status]
        return sorted(sessions, key=lambda item: (item.updated_at, item.session_id))

    def queue_utterance(
        self,
        session_id: str,
        text: str,
        provider_id: str | None = None,
        priority: int = 100,
        metadata: dict[str, Any] | None = None,
    ) -> VoiceUtterance:
        session = self.get_session(session_id)
        if session.status == "closed":
            raise ValidationError(f"Voice session is closed: {session_id}")
        if not text.strip():
            raise ValidationError("Voice utterance text is required.")
        utterance = VoiceUtterance(
            session_id=session_id,
            text=text,
            provider_id=provider_id,
            priority=priority,
            metadata=metadata or {},
        )
        self._write_utterance(utterance)
        self._write_session(replace(session, status="queued", updated_at=_now()))
        self.events.emit("voice.utterance.queued", "voice", asdict(utterance))
        return utterance

    def list_utterances(self, session_id: str) -> list[VoiceUtterance]:
        self.get_session(session_id)
        utterances = [
            self._read_utterance(stream_id.removeprefix("utterance:"))
            for stream_id in self.journal.stream_ids("utterance:")
        ]
        return sorted(
            [utterance for utterance in utterances if utterance.session_id == session_id],
            key=lambda item: (item.priority, item.created_at, item.utterance_id),
        )

    def pause_session(self, session_id: str) -> VoiceSession:
        current = self.get_session(session_id)
        if current.status == "recording" and current.active_recording_id:
            self.cancel_recording(current.active_recording_id)
        session = self.transition_session(session_id, "paused")
        self.events.emit("voice.session.paused", "voice", asdict(session))
        return session

    def resume_session(self, session_id: str) -> VoiceSession:
        current = self.get_session(session_id)
        if current.status != "paused":
            raise ValidationError("Only a paused voice session can be resumed.")
        target = (
            "listening"
            if current.previous_state
            in {
                "listening",
                "recording",
                "processing",
                "thinking",
                "speaking",
            }
            else ("queued" if self._queued_count(session_id) else "idle")
        )
        if target == "queued":
            session = self._set_session_status(session_id, target)
        else:
            session = self.transition_session(session_id, target)
        self.events.emit("voice.session.resumed", "voice", asdict(session))
        return session

    def close_session(self, session_id: str) -> VoiceSession:
        current = self.get_session(session_id)
        if current.active_recording_id:
            recording = self.get_recording(current.active_recording_id)
            if recording.status == "recording":
                self.cancel_recording(recording.recording_id)
        if current.active_synthesis_id:
            synthesis = self.get_synthesis(current.active_synthesis_id)
            if synthesis.status in {"created", "running"}:
                self.cancel_synthesis(synthesis.synthesis_id)
        session = self.transition_session(session_id, "closed")
        self.events.emit("voice.session.closed", "voice", asdict(session))
        return session

    def cancel_session(self, session_id: str) -> VoiceSession:
        current = self.get_session(session_id)
        if current.status == "cancelled":
            return current
        if current.active_recording_id:
            recording = self.get_recording(current.active_recording_id)
            if recording.status == "recording":
                self.cancel_recording(recording.recording_id)
        if current.active_synthesis_id:
            synthesis = self.get_synthesis(current.active_synthesis_id)
            if synthesis.status in {"created", "running", "completed"}:
                self.cancel_synthesis(synthesis.synthesis_id)
        cancelling = self.transition_session(session_id, "cancelling")
        return self.transition_session(cancelling.session_id, "cancelled")

    def mark_ready(self, utterance_id: str) -> VoiceUtterance:
        utterance = self._set_utterance_state(utterance_id, "ready")
        self._set_session_status(utterance.session_id, "speaking")
        self.events.emit("voice.utterance.ready", "voice", asdict(utterance))
        return utterance

    def mark_completed(self, utterance_id: str) -> VoiceUtterance:
        utterance = self._set_utterance_state(utterance_id, "completed")
        self._set_session_status(
            utterance.session_id,
            "queued" if self._queued_count(utterance.session_id) else "idle",
        )
        self.events.emit("voice.utterance.completed", "voice", asdict(utterance))
        return utterance

    def summarize_session(self, session_id: str) -> VoiceSummary:
        session = self.get_session(session_id)
        provider_status: dict[str, Any] = {}
        provider_status["text_to_speech"] = asdict(self.resolve_tts_provider())
        return VoiceSummary(
            session=session,
            playback=self._playback_state(session_id),
            provider_status=provider_status,
            metadata={"executes_real_provider": False, "plays_audio": False},
        )

    def get_settings(self) -> VoiceSettings:
        raw = load_structured_file(self.settings_path)
        raw.setdefault("schema_version", 1)
        raw.setdefault("provider_id", None)
        raw.setdefault("stt_provider_id", "faster_whisper")
        raw.setdefault("device_id", None)
        raw.setdefault("language", "pt-BR")
        raw.setdefault("model", "base")
        raw.setdefault("tts_provider_id", "piper")
        raw.setdefault("tts_model", None)
        raw.setdefault("default_tts_voice", raw.pop("tts_voice_id", None))
        raw.setdefault("preferred_voice_gender", "female")
        raw.setdefault("provider_configuration_references", {})
        raw.setdefault("policy_version", "voice-configuration-v1")
        raw.setdefault("tts_speed", None)
        raw.setdefault("enabled", True)
        raw.setdefault("metadata", {})
        raw = self._normalize_voice_settings(raw)
        return VoiceSettings(**raw)

    def update_settings(
        self,
        *,
        provider_id: str | None = None,
        stt_provider_id: str | None = None,
        device_id: str | None = None,
        language: str | None = None,
        model: str | None = None,
        tts_provider_id: str | None = None,
        tts_voice_id: str | None = None,
        tts_model: str | None = None,
        default_tts_voice: str | None = None,
        preferred_voice_gender: str | None = None,
        provider_configuration_references: dict[str, str] | None = None,
        tts_speed: float | None = None,
        stt_model: str | None = None,
        stt_device: str | None = None,
        stt_compute_type: str | None = None,
        input_device_id: str | None = None,
        output_device_id: str | None = None,
        voice_analysis_provider_id: str | None = None,
        vad_provider_id: str | None = None,
        vad_enabled: bool | None = None,
        silence_threshold: float | None = None,
        min_speech_duration_ms: int | None = None,
        min_silence_duration_ms: int | None = None,
        max_utterance_duration_ms: int | None = None,
        recording_retention: str | None = None,
        store_raw_audio: bool | None = None,
        delete_after_transcription: bool | None = None,
        retention_days: int | None = None,
        keep_transcripts: bool | None = None,
        keep_analysis: bool | None = None,
        keep_synthesis_audio: bool | None = None,
        conversation_mode_defaults: dict[str, Any] | None = None,
        enabled: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> VoiceSettings:
        current = self.get_settings()
        normalized_stt_provider_id = self._normalize_stt_provider_id(
            stt_provider_id if stt_provider_id is not None else provider_id,
            current.stt_provider_id or current.provider_id,
        )
        updated = VoiceSettings(
            schema_version=3,
            provider_id=normalized_stt_provider_id,
            stt_provider_id=normalized_stt_provider_id,
            stt_model=stt_model if stt_model is not None else current.stt_model,
            stt_device=stt_device if stt_device is not None else current.stt_device,
            stt_compute_type=(
                stt_compute_type if stt_compute_type is not None else current.stt_compute_type
            ),
            device_id=device_id if device_id is not None else current.device_id,
            input_device_id=(
                input_device_id if input_device_id is not None else current.input_device_id
            ),
            output_device_id=(
                output_device_id if output_device_id is not None else current.output_device_id
            ),
            language=(language if language is not None else current.language).strip() or "pt-BR",
            model=model if model is not None else current.model,
            tts_provider_id=tts_provider_id
            if tts_provider_id is not None
            else current.tts_provider_id,
            tts_model=tts_model if tts_model is not None else current.tts_model,
            default_tts_voice=(
                default_tts_voice
                if default_tts_voice is not None
                else tts_voice_id
                if tts_voice_id is not None
                else current.default_tts_voice
            ),
            preferred_voice_gender=(
                preferred_voice_gender
                if preferred_voice_gender is not None
                else current.preferred_voice_gender
            ),
            tts_speed=tts_speed if tts_speed is not None else current.tts_speed,
            provider_configuration_references=(
                provider_configuration_references
                if provider_configuration_references is not None
                else current.provider_configuration_references
            ),
            policy_version=current.policy_version,
            voice_analysis_provider_id=(
                voice_analysis_provider_id
                if voice_analysis_provider_id is not None
                else current.voice_analysis_provider_id
            ),
            vad_provider_id=(
                vad_provider_id if vad_provider_id is not None else current.vad_provider_id
            ),
            vad_enabled=current.vad_enabled if vad_enabled is None else vad_enabled,
            silence_threshold=(
                silence_threshold if silence_threshold is not None else current.silence_threshold
            ),
            min_speech_duration_ms=(
                min_speech_duration_ms
                if min_speech_duration_ms is not None
                else current.min_speech_duration_ms
            ),
            min_silence_duration_ms=(
                min_silence_duration_ms
                if min_silence_duration_ms is not None
                else current.min_silence_duration_ms
            ),
            max_utterance_duration_ms=(
                max_utterance_duration_ms
                if max_utterance_duration_ms is not None
                else current.max_utterance_duration_ms
            ),
            recording_retention=(
                recording_retention
                if recording_retention is not None
                else current.recording_retention
            ),
            store_raw_audio=(
                current.store_raw_audio if store_raw_audio is None else store_raw_audio
            ),
            delete_after_transcription=(
                current.delete_after_transcription
                if delete_after_transcription is None
                else delete_after_transcription
            ),
            retention_days=(current.retention_days if retention_days is None else retention_days),
            keep_transcripts=(
                current.keep_transcripts if keep_transcripts is None else keep_transcripts
            ),
            keep_analysis=(current.keep_analysis if keep_analysis is None else keep_analysis),
            keep_synthesis_audio=(
                current.keep_synthesis_audio
                if keep_synthesis_audio is None
                else keep_synthesis_audio
            ),
            temp_file_max_age_hours=current.temp_file_max_age_hours,
            failed_recording_retention_days=current.failed_recording_retention_days,
            conversation_mode_defaults=(
                conversation_mode_defaults
                if conversation_mode_defaults is not None
                else current.conversation_mode_defaults
            ),
            enabled=current.enabled if enabled is None else enabled,
            metadata={**current.metadata, **(metadata or {})},
        )
        dump_structured_file(self.settings_path, asdict(updated))
        self.events.emit("voice.settings.updated", "voice", asdict(updated))
        return updated

    def resolve_model_name(self, model: str | None) -> str:
        if not model:
            return VOICE_MODEL_PRESETS["auto"]
        normalized = model.strip().lower()
        return VOICE_MODEL_PRESETS.get(normalized, model.strip())

    def list_devices(self) -> list[AudioDevice]:
        if self.audio is None:
            return []
        return self.audio.list_devices()

    def list_providers(self) -> list[VoiceProviderSummary]:
        if self.speech_adapters is None:
            return []
        providers: list[VoiceProviderSummary] = []
        for manifest in self.speech_adapters.list_adapters():
            if manifest.adapter_type not in {"stt", "tts", "voice_analysis"}:
                continue
            health = self.speech_adapters.adapter_health(manifest.adapter_id)
            providers.append(
                VoiceProviderSummary(
                    provider_id=manifest.provider_id,
                    adapter_id=manifest.adapter_id,
                    adapter_type=manifest.adapter_type,
                    status=health.status,
                    enabled=health.status != "unavailable",
                    health=asdict(health),
                    metadata=manifest.metadata,
                )
            )
        return sorted(providers, key=lambda item: (item.adapter_type, item.provider_id))

    def list_voice_packs(self) -> list[VoicePackManifest]:
        packs: list[VoicePackManifest] = []
        for packs_root in self._voice_pack_roots():
            if not packs_root.exists():
                continue
            for manifest_path in sorted(packs_root.glob("*/voice-pack.json")):
                packs.append(self._read_voice_pack_manifest(manifest_path))
        return packs

    def list_tts_voices(self) -> list[VoicePackEntry]:
        voices = [voice for pack in self.list_voice_packs() for voice in pack.voices]
        if self.speech_adapters is not None:
            for raw in self.speech_adapters.list_tts_voices():
                voice_id = str(raw.get("id") or raw.get("voice_id") or raw.get("profile_id") or "").strip()
                if not voice_id:
                    continue
                voices.append(VoicePackEntry(
                    voice_id=voice_id,
                    display_name=str(raw.get("name") or raw.get("display_name") or voice_id),
                    language=str(raw.get("language") or "Auto"),
                    locale=str(raw.get("language") or ""),
                    voice_profile={"gender": raw.get("gender") or "custom", "source": "voicestudio"},
                    provider="voicestudio", engine="voicestudio", asset_reference="external://voicestudio",
                    version="local", checksum="", license="user-provided", provenance="VoiceStudio local profile",
                    usable=True, status="ready", metadata=raw,
                ))
        return sorted(voices, key=lambda item: (item.locale, item.display_name, item.voice_id))

    def create_voicestudio_profile(self, *, name: str, audio: bytes, filename: str, language: str, ref_text: str = "") -> dict[str, Any]:
        if self.speech_adapters is None:
            raise ValidationError("Speech runtime is unavailable.")
        adapter = self.speech_adapters.get_runtime_adapter("voicestudio_tts_adapter")
        if adapter is None or not hasattr(adapter, "create_profile"):
            raise ValidationError("VoiceStudio adapter is unavailable.")
        return adapter.create_profile(name=name, audio=audio, filename=filename, language=language, ref_text=ref_text)

    def test_microphone(self, device_id: str) -> dict[str, Any]:
        device = self._get_device(device_id)
        if not device.enabled:
            raise ValidationError(f"Microphone is disabled: {device_id}")
        if self.audio is None:
            raise ValidationError("Audio runtime is unavailable.")
        diagnostic = self.audio.devices.test_input(device_id)
        status = {
            "device_id": device.device_id,
            "name": device.name,
            "device_type": device.device_type,
            "available": diagnostic.opened,
            "checked_at": _now(),
            "message": (
                "Microphone capture completed."
                if diagnostic.opened
                else diagnostic.error or "Microphone capture failed."
            ),
            "diagnostic": asdict(diagnostic),
        }
        self.events.emit("voice.device.tested", "voice", status)
        return status

    def create_recording(
        self,
        *,
        device_id: str | None = None,
        provider_id: str | None = None,
        language: str = "pt-BR",
        model: str | None = None,
        audio_base64: str | None = None,
        audio_format: str | None = None,
        duration_ms: int | None = None,
        transcript: str | None = None,
        metadata: dict[str, Any] | None = None,
        recording_id: str | None = None,
    ) -> VoiceRecording:
        if device_id:
            self._get_device(device_id)
        if provider_id:
            self._resolve_provider_summary(provider_id)
        recording = VoiceRecording(
            recording_id=recording_id
            or f"voice-{int(datetime.now(UTC).timestamp() * 1_000_000_000)}",
            device_id=device_id,
            provider_id=provider_id,
            language=(language or "pt-BR").strip() or "pt-BR",
            model=model,
            audio_ref=None,
            audio_format=audio_format,
            duration_ms=duration_ms,
            transcript=transcript.strip() if transcript else None,
            status="transcribed" if transcript else "recorded",
            metadata=metadata or {},
        )
        if audio_base64 and self.get_settings().store_raw_audio:
            audio_ref = self._write_audio_blob(recording.recording_id, audio_base64, audio_format)
            recording = replace(recording, audio_ref=audio_ref)
        self._write_recording(recording)
        self.events.emit("voice.recording.created", "voice", asdict(recording))
        return recording

    def list_recordings(self) -> list[VoiceRecording]:
        recordings = [
            self._read_recording(stream_id.removeprefix("recording:"))
            for stream_id in self.journal.stream_ids("recording:")
        ]
        return sorted(
            recordings, key=lambda item: (item.created_at, item.recording_id), reverse=True
        )

    def get_recording(self, recording_id: str) -> VoiceRecording:
        return self._read_recording(recording_id)

    def start_recording(
        self,
        *,
        session_id: str | None = None,
        conversation_id: str | None = None,
        agent_id: str | None = None,
        audio_format: str = "audio/webm",
        language: str | None = None,
        recording_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> VoiceRecording:
        if session_id:
            self.get_session(session_id)
        recording = VoiceRecording(
            recording_id=recording_id
            or f"voice-{int(datetime.now(UTC).timestamp() * 1_000_000_000)}",
            session_id=session_id,
            conversation_id=conversation_id,
            agent_id=agent_id,
            audio_format=audio_format,
            language=(language or self.get_settings().language).strip() or "pt-BR",
            status="recording",
            metadata=metadata or {},
        )
        self._write_recording(recording)
        if session_id:
            session = self.get_session(session_id)
            self._write_session(
                replace(
                    session,
                    active_recording_id=recording.recording_id,
                    revision=session.revision + 1,
                    updated_at=_now(),
                )
            )
        self.events.emit("voice.recording.started", "voice", asdict(recording))
        return recording

    def append_recording_chunk(
        self,
        recording_id: str,
        chunk: bytes,
        *,
        sequence: int,
        idempotency_key: str,
        expected_revision: int | None = None,
    ) -> VoiceRecording:
        if not chunk:
            raise ValidationError("Recording chunk is empty.")
        recording = self._read_recording(recording_id)
        if recording.status != "recording":
            raise ValidationError(f"Recording does not accept chunks: {recording.status}")
        if expected_revision is not None and recording.revision != expected_revision:
            raise ValidationError("Recording revision conflict.")
        if idempotency_key in recording.idempotency_keys:
            return recording
        if sequence != recording.sequence:
            raise ValidationError(
                f"Recording chunk sequence conflict: expected {recording.sequence}, got {sequence}."
            )
        chunk_path = self._recording_chunks_root(recording_id) / f"{sequence:08d}.chunk"
        chunk_path.write_bytes(chunk)
        updated = replace(
            recording,
            chunks=recording.chunks + 1,
            sequence=recording.sequence + 1,
            total_bytes=recording.total_bytes + len(chunk),
            revision=recording.revision + 1,
            idempotency_keys=[*recording.idempotency_keys, idempotency_key],
            updated_at=_now(),
        )
        self._write_recording(updated)
        self.events.emit(
            "voice.recording.chunk_appended",
            "voice",
            {
                "recording_id": recording_id,
                "sequence": sequence,
                "bytes": len(chunk),
                "revision": updated.revision,
            },
        )
        return updated

    def complete_recording(self, recording_id: str) -> VoiceRecording:
        recording = self._read_recording(recording_id)
        if recording.status == "completed":
            return recording
        if recording.status != "recording":
            raise ValidationError(f"Recording cannot be completed: {recording.status}")
        chunks = sorted(self._recording_chunks_root(recording_id).glob("*.chunk"))
        assembled = b"".join(path.read_bytes() for path in chunks)
        if self.audio is None:
            raise ValidationError("Audio runtime is unavailable.")
        payload = self.audio.ingest(assembled, recording.audio_format)
        audio_ref = None
        if self.get_settings().store_raw_audio:
            audio_path = self._recordings_root() / f"{recording_id}.wav"
            audio_path.write_bytes(payload.audio_bytes)
            audio_ref = f"voice/recordings/{audio_path.name}"
        else:
            audio_path = self._recordings_root() / f"{recording_id}.transient.wav"
            audio_path.write_bytes(payload.audio_bytes)
            self._transient_audio_refs[recording_id] = f"voice/recordings/{audio_path.name}"
        updated = replace(
            recording,
            status="completed",
            audio_format=payload.mime_type,
            audio_ref=audio_ref,
            duration_ms=payload.duration_ms,
            checksum=payload.checksum,
            completed_at=_now(),
            updated_at=_now(),
            revision=recording.revision + 1,
        )
        self._write_recording(updated)
        for path in chunks:
            path.unlink(missing_ok=True)
        self.events.emit("voice.recording.completed", "voice", asdict(updated))
        return updated

    def cancel_recording(self, recording_id: str) -> VoiceRecording:
        recording = self._read_recording(recording_id)
        if recording.status == "cancelled":
            return recording
        if recording.status in {"deleted", "transcribed"}:
            raise ValidationError(f"Recording cannot be cancelled: {recording.status}")
        updated = replace(
            recording,
            status="cancelled",
            revision=recording.revision + 1,
            updated_at=_now(),
        )
        self._write_recording(updated)
        for path in self._recording_chunks_root(recording_id).glob("*.chunk"):
            path.unlink(missing_ok=True)
        self.events.emit("voice.recording.cancelled", "voice", asdict(updated))
        return updated

    def delete_recording(self, recording_id: str) -> VoiceRecording:
        recording = self._read_recording(recording_id)
        if recording.status == "recording":
            raise ValidationError("Active recording must be cancelled before deletion.")
        if recording.audio_ref:
            self.data_dir.resolve(recording.audio_ref).unlink(missing_ok=True)
        deleted = replace(
            recording,
            status="deleted",
            audio_ref=None,
            revision=recording.revision + 1,
            updated_at=_now(),
        )
        self._write_recording(deleted)
        self.events.emit("voice.recording.deleted", "voice", {"recording_id": recording_id})
        return deleted

    def complete_voice_message(self, recording_id: str) -> VoiceMessageResult:
        recording = self._read_recording(recording_id)
        if recording.status == "transcribed" and recording.transcript_id:
            return self._read_voice_message_result(recording.transcript_id)
        transient_audio_ref = self._transient_audio_refs.get(recording_id)
        if recording.status != "completed" or not (recording.audio_ref or transient_audio_ref):
            raise ValidationError("Voice message recording must be completed before transcription.")
        if self.audio is None or self.speech_adapters is None:
            raise ValidationError("Speech runtime is unavailable.")
        audio_path = self.data_dir.resolve(recording.audio_ref or transient_audio_ref or "")
        if not audio_path.is_file():
            raise ValidationError("Voice message audio is unavailable.")
        processing = replace(
            recording,
            status="processing",
            revision=recording.revision + 1,
            updated_at=_now(),
        )
        self._write_recording(processing)
        request = AudioInputRequest(
            session_id=recording.session_id,
            provider_id=recording.provider_id or self._get_stt_provider_id(),
            language=recording.language,
            model=recording.model or self.get_settings().stt_model,
            audio_base64=base64.b64encode(audio_path.read_bytes()).decode("ascii"),
            audio_format="audio/wav",
            duration_ms=recording.duration_ms,
            metadata={
                "stt_device": self.get_settings().stt_device,
                "stt_compute_type": self.get_settings().stt_compute_type,
                **recording.metadata,
            },
        )
        analysis = self.speech_adapters.analyze(request)
        transcript = self.audio.transcribe(request)
        transcript_id = f"transcript-{recording.recording_id}"
        analysis_id = f"analysis-{recording.recording_id}"
        result = VoiceMessageResult(
            recording_id=recording.recording_id,
            transcript_id=transcript_id,
            text=transcript.text,
            language=transcript.language,
            segments=[asdict(item) for item in transcript.segments],
            confidence=transcript.confidence,
            analysis=asdict(analysis),
            duration_ms=transcript.duration_ms or recording.duration_ms or 0,
            warnings=[],
            status=transcript.status,
        )
        dump_structured_file(self._transcripts_root() / f"{transcript_id}.yaml", asdict(result))
        dump_structured_file(self._analyses_root() / f"{analysis_id}.yaml", asdict(analysis))
        updated = replace(
            processing,
            status="transcribed",
            transcript=transcript.text,
            transcript_id=transcript_id,
            analysis_id=analysis_id,
            provider_id=transcript.provider_id,
            revision=processing.revision + 1,
            updated_at=_now(),
        )
        self._write_recording(updated)
        if transient_audio_ref:
            audio_path.unlink(missing_ok=True)
            self._transient_audio_refs.pop(recording_id, None)
        self.events.emit(
            "voice.message.completed",
            "voice",
            {
                "recording_id": recording.recording_id,
                "transcript_id": transcript_id,
                "analysis_id": analysis_id,
                "status": result.status,
            },
        )
        signal_type = "speech.transcribed" if result.status == "success" else "speech.no_speech"
        self._emit_perception_signal(
            VoicePerceptionSignal(
                type=signal_type,
                session_id=recording.session_id,
                conversation_id=recording.conversation_id,
                recording_id=recording.recording_id,
                confidence=result.confidence,
                values={
                    "duration_ms": result.duration_ms,
                    "language": result.language,
                    "segment_count": len(result.segments),
                },
                provenance="voice.message",
                metadata={"transcript_id": transcript_id, "text_redacted": True},
            )
        )
        for signal_type, value in (
            ("voice.volume", result.analysis.get("average_volume")),
            ("voice.peak", result.analysis.get("peak_volume")),
            ("voice.speech_rate", result.analysis.get("speech_rate")),
        ):
            if value is not None:
                self._emit_perception_signal(
                    VoicePerceptionSignal(
                        type=signal_type,
                        session_id=recording.session_id,
                        conversation_id=recording.conversation_id,
                        recording_id=recording.recording_id,
                        values={"value": value},
                        provenance="local_acoustic_analysis",
                        metadata={"analysis_id": analysis_id},
                    )
                )
        self._emit_perception_signal(
            VoicePerceptionSignal(
                type="voice.analysis_completed",
                session_id=recording.session_id,
                conversation_id=recording.conversation_id,
                recording_id=recording.recording_id,
                values={"duration_ms": result.duration_ms},
                provenance="local_acoustic_analysis",
                metadata={"analysis_id": analysis_id},
            )
        )
        return result

    def _read_voice_message_result(self, transcript_id: str) -> VoiceMessageResult:
        raw = load_structured_file(self._transcripts_root() / f"{transcript_id}.yaml")
        if not raw:
            raise NotFound(f"Voice message result not found: {transcript_id}")
        return VoiceMessageResult(**raw)

    def run_conversation_turn(
        self,
        session_id: str,
        recording_id: str,
        *,
        idempotency_key: str,
        model_provider_id: str | None = None,
        model_name: str | None = None,
        manual_model_selection: bool | None = None,
    ) -> VoiceConversationTurnResult:
        session = self.get_session(session_id)
        if session.status == "recording":
            session = self.transition_session(session_id, "processing")
        if session.status != "processing":
            raise ValidationError("Voice conversation turn requires processing state.")
        turn_receipt_name = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        existing_path = self._turns_root() / f"{turn_receipt_name}.yaml"
        existing = load_structured_file(existing_path)
        if existing:
            return VoiceConversationTurnResult(**existing)
        message = self.complete_voice_message(recording_id)
        if message.status != "success" or not message.text.strip():
            self.transition_session(session_id, "error", error=message.status)
            raise ValidationError(f"Voice transcription did not produce speech: {message.status}")
        # Provider confidence is a heuristic, not a calibrated probability.
        # Reject only clearly weak supplied scores; absent scores remain unknown.
        low_confidence = message.confidence is not None and message.confidence < 0.2
        if low_confidence or _is_likely_repeated_transcription_echo(message.text):
            rejection_reason = "low_transcription_confidence" if low_confidence else "likely_repeated_transcription_echo"
            utterance = VoiceUtterance(
                session_id=session_id,
                text="[ignored uncertain transcription]" if low_confidence else "[ignored repeated audio echo]",
                state="cancelled",
                metadata={"reason": rejection_reason},
            )
            self._write_utterance(utterance)
            synthesis_id = f"synthesis-{utterance.utterance_id}"
            self._write_synthesis(
                VoiceSynthesis(
                    synthesis_id=synthesis_id,
                    session_id=session_id,
                    utterance_id=utterance.utterance_id,
                    message_id=None,
                    provider_id=None,
                    voice_id=None,
                    status="skipped",
                    text_checksum=hashlib.sha256(b"").hexdigest(),
                    metadata={"reason": rejection_reason},
                )
            )
            self.transition_session(session_id, "thinking")
            speaking = self.transition_session(session_id, "speaking")
            listening = self.transition_session(speaking.session_id, "listening")
            result = VoiceConversationTurnResult(
                voice_session_id=session_id,
                recording_id=recording_id,
                transcript_id=message.transcript_id,
                utterance_id=utterance.utterance_id,
                conversation_id=session.conversation_id,
                user_message_id=None,
                assistant_message_id=None,
                synthesis_id=synthesis_id,
                correlation_id=None,
                transcript=message.text,
                response="",
                status="needs_repetition" if low_confidence else "ignored_echo",
            )
            dump_structured_file(existing_path, asdict(result))
            self.events.emit(
                "voice.conversation.transcription_rejected" if low_confidence else "voice.conversation.echo_ignored",
                "voice",
                {
                    "voice_session_id": listening.session_id,
                    "recording_id": recording_id,
                    "transcript_id": message.transcript_id,
                },
            )
            return result
        if self.chat is None:
            self.transition_session(session_id, "error", error="chat_unavailable")
            raise ValidationError("Chat runtime is unavailable.")
        retrieval_directive = detect_voice_retrieval_intent(message.text)
        project_id = self._conversation_project_id(session.conversation_id)
        self.transition_session(session_id, "thinking")
        chat_result = self.chat.submit_turn(
            self._permission_context(),
            content=message.text,
            conversation_id=session.conversation_id,
            target_agent_id=session.agent_id,
            idempotency_key=idempotency_key,
            project_id=project_id,
            retrieval_intent=retrieval_directive,
            model_provider_id=model_provider_id,
            model_name=model_name,
            manual_model_selection=manual_model_selection,
        )
        response = str(chat_result.response)
        conversation_id = getattr(chat_result, "conversation_id", None) or session.conversation_id
        user_message_id, assistant_message_id = self._conversation_message_ids(conversation_id)
        utterance = self.queue_utterance(session_id, response)
        try:
            synthesis = self.synthesize_utterance(
                session_id,
                utterance.utterance_id,
                response,
                message_id=assistant_message_id,
            )
            turn_status = "completed"
        except Exception:
            synthesis = self.get_synthesis(f"synthesis-{utterance.utterance_id}")
            turn_status = "completed_without_audio"
        speaking = self.transition_session(session_id, "speaking")
        self.transition_session(speaking.session_id, "listening")
        result = VoiceConversationTurnResult(
            voice_session_id=session_id,
            recording_id=recording_id,
            transcript_id=message.transcript_id,
            utterance_id=utterance.utterance_id,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            synthesis_id=synthesis.synthesis_id,
            correlation_id=getattr(getattr(chat_result, "message", None), "correlation_id", None),
            transcript=message.text,
            response=response,
            status=turn_status,
        )
        dump_structured_file(existing_path, asdict(result))
        self.events.emit(
            "voice.conversation.turn_completed",
            "voice",
            {
                "voice_session_id": session_id,
                "recording_id": recording_id,
                "transcript_id": message.transcript_id,
                "utterance_id": utterance.utterance_id,
                "conversation_id": conversation_id,
                "synthesis_id": synthesis.synthesis_id,
            },
        )
        return result

    def _conversation_project_id(self, conversation_id: str | None) -> str | None:
        if not conversation_id or self.chat is None or self.chat.conversations is None:
            return None
        try:
            conversation = self.chat.conversations.get_conversation(conversation_id)
        except Exception:
            return None
        value = conversation.metadata.get("project_id")
        return str(value) if value else None

    def synthesize_utterance(
        self,
        session_id: str,
        utterance_id: str,
        text: str,
        *,
        message_id: str | None = None,
    ) -> VoiceSynthesis:
        if self.speech_adapters is None:
            raise ValidationError("Speech runtime is unavailable.")
        active = [item for item in self.list_syntheses(session_id) if item.status == "running"]
        if active:
            raise ValidationError("A synthesis is already running for this voice session.")
        synthesis_id = f"synthesis-{utterance_id}"
        text_checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        created = VoiceSynthesis(
            synthesis_id=synthesis_id,
            session_id=session_id,
            utterance_id=utterance_id,
            message_id=message_id,
            provider_id=None,
            voice_id=self.get_settings().default_tts_voice,
            status="running",
            text_checksum=text_checksum,
        )
        self._write_synthesis(created)
        session = self.get_session(session_id)
        self._write_session(
            replace(
                session,
                active_utterance_id=utterance_id,
                active_synthesis_id=synthesis_id,
                revision=session.revision + 1,
                updated_at=_now(),
            )
        )
        settings = self.get_settings()
        tts_selection = self.resolve_tts_provider()
        provider_id = (
            tts_selection.provider_id
            if tts_selection.state != "unavailable" and tts_selection.provider_id
            else None
        )
        try:
            output = self.speech_adapters.synthesize(
                AudioOutputRequest(
                    session_id=session_id,
                    text=text,
                    provider_id=provider_id,
                    voice_id=settings.default_tts_voice,
                    language=settings.language,
                )
            )
            logger.info(
                "voice_tts_diag:synthesize_returned session_id=%s synthesis_id=%s provider_id=%s audio_base64_chars=%s",
                session_id,
                synthesis_id,
                output.provider_id,
                len(output.audio_base64 or ""),
            )
        except Exception as exc:
            logger.exception(
                "voice_tts_diag:synthesize_error session_id=%s synthesis_id=%s",
                session_id,
                synthesis_id,
            )
            failed = replace(created, status="failed", error=str(exc), revision=2)
            self._write_synthesis(failed)
            raise
        audio_reference = None
        if output.audio_base64:
            audio_path = self._syntheses_root() / f"{synthesis_id}.wav"
            audio_bytes = base64.b64decode(output.audio_base64)
            audio_path.write_bytes(audio_bytes)
            audio_reference = f"voice/syntheses/{audio_path.name}"
            logger.info(
                "voice_tts_diag:synthesis_saved session_id=%s synthesis_id=%s path=%s bytes=%s",
                session_id,
                synthesis_id,
                audio_path,
                len(audio_bytes),
            )
        else:
            logger.warning(
                "voice_tts_diag:synthesis_empty session_id=%s synthesis_id=%s provider_id=%s",
                session_id,
                synthesis_id,
                output.provider_id,
            )
        completed = replace(
            created,
            provider_id=output.provider_id,
            voice_id=output.voice_id,
            status="completed",
            audio_reference=audio_reference,
            duration_ms=output.duration_ms,
            completed_at=_now(),
            revision=2,
            metadata={
                "streaming": False,
                "capabilities": {"streaming": False},
                **{
                    key: output.metadata[key]
                    for key in (
                        "execution_request_id",
                        "execution_request_fingerprint",
                        "execution_result_fingerprint",
                        "process_exited",
                        "output_verified",
                    )
                    if key in output.metadata
                },
            },
        )
        self._write_synthesis(completed)
        return completed

    def cancel_synthesis(self, synthesis_id: str) -> VoiceSynthesis:
        synthesis = self.get_synthesis(synthesis_id)
        if synthesis.status == "cancelled":
            return synthesis
        if synthesis.status not in {"created", "running", "completed"}:
            raise ValidationError(f"Synthesis cannot be cancelled: {synthesis.status}")
        cancelled = replace(
            synthesis,
            status="cancelled",
            cancelled_at=_now(),
            revision=synthesis.revision + 1,
            metadata={**synthesis.metadata, "provider_cancel_supported": False},
        )
        self._write_synthesis(cancelled)
        self.events.emit(
            "voice.synthesis.cancelled",
            "voice",
            {"synthesis_id": synthesis_id, "session_id": synthesis.session_id},
        )
        return cancelled

    def interrupt_session(
        self,
        session_id: str,
        *,
        audio_format: str = "audio/wav",
        barge_in_enabled: bool = True,
    ) -> VoiceRecording | None:
        session = self.get_session(session_id)
        if not barge_in_enabled:
            return None
        if session.status != "speaking":
            raise ValidationError("Voice interruption requires speaking state.")
        if session.active_synthesis_id:
            self.cancel_synthesis(session.active_synthesis_id)
        recording = self.start_recording(
            session_id=session_id,
            conversation_id=session.conversation_id,
            agent_id=session.agent_id,
            audio_format=audio_format,
        )
        current = self.get_session(session_id)
        interrupted = self.transition_session(
            session_id,
            "recording",
            expected_revision=current.revision,
            metadata={"interrupted_synthesis_id": session.active_synthesis_id},
        )
        self._write_session(
            replace(
                interrupted,
                active_recording_id=recording.recording_id,
                active_synthesis_id=None,
                revision=interrupted.revision + 1,
                updated_at=_now(),
            )
        )
        self.events.emit(
            "voice.user_interrupted",
            "voice",
            {
                "session_id": session_id,
                "synthesis_id": session.active_synthesis_id,
                "recording_id": recording.recording_id,
            },
        )
        self._emit_perception_signal(
            VoicePerceptionSignal(
                type="voice.interruption",
                session_id=session_id,
                conversation_id=session.conversation_id,
                recording_id=recording.recording_id,
                utterance_id=session.active_utterance_id,
                values={"interrupted": True},
                provenance="voice.barge_in",
                metadata={"synthesis_id": session.active_synthesis_id},
            )
        )
        return recording

    def _emit_perception_signal(self, signal: VoicePerceptionSignal) -> None:
        try:
            self.perception_sink.emit(signal)
        except Exception as exc:
            self.events.emit(
                "voice.perception_sink.failed",
                "voice",
                {"signal_type": signal.type, "error": str(exc)},
            )

    def get_synthesis(self, synthesis_id: str) -> VoiceSynthesis:
        replay = self.journal.replay(f"synthesis:{synthesis_id}")
        if not replay.records:
            raise NotFound(f"Voice synthesis not found: {synthesis_id}")
        return VoiceSynthesis(**replay.records[-1].payload)

    def read_synthesis_audio_base64(self, synthesis_id: str) -> str | None:
        synthesis = self.get_synthesis(synthesis_id)
        if not synthesis.audio_reference:
            logger.warning(
                "voice_tts_diag:synthesis_read_missing_reference synthesis_id=%s status=%s",
                synthesis_id,
                synthesis.status,
            )
            return None
        path = self.data_dir.resolve(synthesis.audio_reference)
        if not path.is_file():
            logger.error(
                "voice_tts_diag:synthesis_read_missing_file synthesis_id=%s path=%s",
                synthesis_id,
                path,
            )
            raise ValidationError("Synthesized audio is unavailable.")
        audio_bytes = path.read_bytes()
        audio_base64 = base64.b64encode(audio_bytes).decode("ascii")
        logger.info(
            "voice_tts_diag:synthesis_read_success synthesis_id=%s path=%s bytes=%s audio_base64_chars=%s",
            synthesis_id,
            path,
            len(audio_bytes),
            len(audio_base64),
        )
        return audio_base64

    def list_syntheses(self, session_id: str | None = None) -> list[VoiceSynthesis]:
        items = [
            self.get_synthesis(stream_id.removeprefix("synthesis:"))
            for stream_id in self.journal.stream_ids("synthesis:")
        ]
        return [item for item in items if session_id is None or item.session_id == session_id]

    def _write_synthesis(self, synthesis: VoiceSynthesis) -> None:
        self._append_snapshot(f"synthesis:{synthesis.synthesis_id}", "synthesis", asdict(synthesis))

    def _conversation_message_ids(
        self, conversation_id: str | None
    ) -> tuple[str | None, str | None]:
        if not conversation_id or self.chat is None or self.chat.conversations is None:
            return None, None
        try:
            messages = self.chat.conversations.list_conversation_messages(conversation_id)
        except Exception:
            return None, None
        if len(messages) < 2:
            return None, None
        return messages[-2].message_id, messages[-1].message_id

    def cleanup_voice_storage(
        self,
        *,
        now: datetime | None = None,
        dry_run: bool = False,
    ) -> VoiceCleanupReport:
        current_time = now or datetime.now(UTC)
        settings = self.get_settings()
        report = VoiceCleanupReport(dry_run=dry_run)
        values = asdict(report)
        data_root = self.data_dir.root.resolve()

        for recording in self.list_recordings():
            values["scanned"] += 1
            if recording.status in {"recording", "processing"}:
                continue
            created = datetime.fromisoformat(recording.created_at)
            age_days = (current_time - created).total_seconds() / 86_400
            remove_audio = bool(
                recording.audio_ref
                and (
                    (recording.status == "transcribed" and settings.delete_after_transcription)
                    or age_days >= settings.retention_days
                    or (
                        recording.status == "failed"
                        and age_days >= settings.failed_recording_retention_days
                    )
                )
            )
            if not remove_audio or not recording.audio_ref:
                continue
            try:
                path = self.data_dir.resolve(recording.audio_ref)
                resolved = path.resolve()
                if data_root not in resolved.parents or resolved.is_symlink():
                    raise ValidationError("Unsafe voice retention path.")
                size = resolved.stat().st_size if resolved.exists() else 0
                if not dry_run:
                    resolved.unlink(missing_ok=True)
                    self._write_recording(
                        replace(
                            recording,
                            audio_ref=None,
                            revision=recording.revision + 1,
                            updated_at=_now(),
                        )
                    )
                values["recordings_deleted"] += 1
                values["reclaimed_bytes"] += size
            except Exception as exc:
                values["failed"] += 1
                values["warnings"].append(str(exc))

        for synthesis in self.list_syntheses():
            values["scanned"] += 1
            if not synthesis.audio_reference or settings.keep_synthesis_audio:
                continue
            path = self.data_dir.resolve(synthesis.audio_reference)
            try:
                resolved = path.resolve()
                if data_root not in resolved.parents or resolved.is_symlink():
                    raise ValidationError("Unsafe synthesis retention path.")
                size = resolved.stat().st_size if resolved.exists() else 0
                if not dry_run:
                    resolved.unlink(missing_ok=True)
                    self._write_synthesis(
                        replace(
                            synthesis,
                            audio_reference=None,
                            revision=synthesis.revision + 1,
                        )
                    )
                values["synthesis_deleted"] += 1
                values["reclaimed_bytes"] += size
            except Exception as exc:
                values["failed"] += 1
                values["warnings"].append(str(exc))

        values["transcripts_retained"] = (
            len(list(self._transcripts_root().glob("*.yaml"))) if settings.keep_transcripts else 0
        )
        values["analyses_retained"] = (
            len(list(self._analyses_root().glob("*.yaml"))) if settings.keep_analysis else 0
        )
        completed = VoiceCleanupReport(**values)
        self.events.emit("voice.storage.cleanup_completed", "voice", asdict(completed))
        return completed

    def _permission_context(self):
        return PermissionContext(actor_id=self.default_actor_id)

    def transcribe_recording(
        self,
        recording_id: str,
        *,
        transcript: str,
        provider_id: str | None = None,
        language: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> VoiceTranscription:
        if not transcript.strip():
            raise ValidationError("Transcript text is required.")
        recording = self._read_recording(recording_id)
        resolved_provider_id = provider_id or recording.provider_id
        if resolved_provider_id == "piper":
            resolved_provider_id = None
        provider = self._resolve_provider_summary(
            resolved_provider_id or self._get_stt_provider_id()
        )
        updated = replace(
            recording,
            transcript=transcript.strip(),
            provider_id=provider.provider_id,
            language=(language or recording.language or self.get_settings().language).strip()
            or "pt-BR",
            status="transcribed",
            updated_at=_now(),
            metadata={**recording.metadata, **(metadata or {})},
        )
        self._write_recording(updated)
        transcription = VoiceTranscription(
            recording_id=recording_id,
            transcript=updated.transcript or "",
            provider_id=provider.provider_id,
            language=updated.language,
            status="transcribed",
            metadata=updated.metadata,
        )
        self.events.emit("voice.recording.transcribed", "voice", asdict(transcription))
        return transcription

    def resolve_stt_provider(self) -> VoiceProviderSelection:
        return self._resolve_configured_provider(
            capability="speech_to_text",
            adapter_type="stt",
            configured_provider_id=self.get_settings().stt_provider_id,
        )

    def resolve_tts_provider(self, session_id: str | None = None) -> VoiceProviderSelection:
        # session_id is accepted for read compatibility only; selection is system-wide.
        _ = session_id
        return self._resolve_configured_provider(
            capability="text_to_speech",
            adapter_type="tts",
            configured_provider_id=self.get_settings().tts_provider_id,
        )

    def provider_unavailable_count(self) -> int:
        count = 0
        for session in self.list_sessions():
            status = self.summarize_session(session.session_id).provider_status.get(
                "text_to_speech",
                {},
            )
            if status.get("state") == "unavailable":
                count += 1
        return count

    def diagnostics(self) -> dict[str, Any]:
        """Return operational state without opening capture or playback devices."""
        try:
            import av  # noqa: F401

            decoder = {"status": "ready", "provider": "pyav"}
        except Exception as exc:
            decoder = {"status": "unavailable", "provider": "pyav", "error": str(exc)}

        device_health = (
            self.audio.device_health()
            if self.audio is not None
            else {"status": "unavailable", "error": "audio runtime unavailable"}
        )
        try:
            vad = WebRTCVADProvider().health()
        except Exception as exc:
            vad = {"status": "unavailable", "provider": "webrtcvad", "error": str(exc)}

        providers: dict[str, dict[str, Any]] = {}
        recent_latencies_ms: dict[str, int] = {}
        for item in self.list_providers():
            status = {"available": "ready", "unconfigured": "not_configured"}.get(
                item.status,
                item.status,
            )
            providers[item.provider_id] = {
                "status": status,
                "adapter_id": item.adapter_id,
                "adapter_type": item.adapter_type,
                "enabled": item.enabled,
                "health": item.health,
            }
            latency = item.health.get("metadata", {}).get("latency_ms")
            if isinstance(latency, int):
                recent_latencies_ms[item.provider_id] = latency

        sessions = self.list_sessions()
        failed = [item for item in sessions if item.status in {"error", "failed"}]
        last_error_session = next((item for item in reversed(sessions) if item.last_error), None)
        settings = self.get_settings()
        storage_ready = self.data_dir.root.exists() and os.access(self.data_dir.root, os.W_OK)
        return {
            "decoder": decoder,
            "input_device": {**device_health, "configured_id": settings.input_device_id},
            "output_device": {**device_health, "configured_id": settings.output_device_id},
            "providers": providers,
            "vad": vad,
            "storage": {
                "status": "ready" if storage_ready else "unavailable",
                "persistence": asdict(self.journal.health()),
            },
            "retention": {
                "status": "configured",
                "retention_days": settings.retention_days,
                "delete_after_transcription": settings.delete_after_transcription,
                "keep_transcripts": settings.keep_transcripts,
            },
            "active_sessions": sum(
                item.status not in {"closed", "cancelled", "error", "failed"} for item in sessions
            ),
            "failed_sessions": len(failed),
            "last_error": last_error_session.last_error if last_error_session else None,
            "recent_latencies_ms": recent_latencies_ms,
        }

    def _set_session_status(self, session_id: str, status: str) -> VoiceSession:
        if status not in VOICE_SESSION_STATUSES:
            raise ValidationError(f"Invalid voice session status: {status}")
        session = self.get_session(session_id)
        if session.status == "closed" and status != "closed":
            raise ValidationError(f"Voice session is closed: {session_id}")
        updated = replace(session, status=status, updated_at=_now())
        self._write_session(updated)
        return updated

    def _set_utterance_state(self, utterance_id: str, state: str) -> VoiceUtterance:
        if state not in VOICE_UTTERANCE_STATES:
            raise ValidationError(f"Invalid voice utterance state: {state}")
        utterance = self._read_utterance(utterance_id)
        updated = replace(utterance, state=state)
        self._write_utterance(updated)
        return updated

    def _playback_state(self, session_id: str) -> VoicePlaybackState:
        utterances = self.list_utterances(session_id)
        current = next(
            (
                utterance.utterance_id
                for utterance in utterances
                if utterance.state in {"synthesizing", "ready", "playing"}
            ),
            None,
        )
        return VoicePlaybackState(
            session_id=session_id,
            current_utterance=current,
            speaking=current is not None,
            queued_items=len(
                [
                    utterance
                    for utterance in utterances
                    if utterance.state in {"pending", "synthesizing", "ready", "playing"}
                ]
            ),
        )

    def _queued_count(self, session_id: str) -> int:
        return len(
            [
                utterance
                for utterance in self.list_utterances(session_id)
                if utterance.state in {"pending", "synthesizing", "ready", "playing"}
            ]
        )

    def _read_session(self, session_id: str) -> VoiceSession:
        replay = self.journal.replay(f"session:{session_id}")
        if not replay.records:
            raise NotFound(f"Voice session not found: {session_id}")
        if not replay.complete:
            raise ValidationError("Voice session journal is incomplete.")
        raw = dict(replay.records[-1].payload)
        raw.setdefault("session_id", session_id)
        # One-way legacy read: historical visual bindings are ignored and never rewritten.
        raw.pop("embodiment_id", None)
        raw.pop("avatar_session_id", None)
        raw.pop("animation_state", None)
        raw.setdefault("status", "idle")
        raw.setdefault("conversation_id", None)
        raw.setdefault("previous_state", None)
        raw.setdefault("active_recording_id", None)
        raw.setdefault("active_utterance_id", None)
        raw.setdefault("active_synthesis_id", None)
        raw.setdefault("closed_at", None)
        raw.setdefault("revision", 1)
        raw.setdefault("settings_snapshot", {})
        raw.setdefault("last_error", None)
        raw.setdefault("created_at", _now())
        raw.setdefault("updated_at", raw["created_at"])
        raw.setdefault("metadata", {})
        return VoiceSession(**raw)

    def _write_session(self, session: VoiceSession) -> None:
        if session.status not in VOICE_SESSION_STATUSES:
            raise ValidationError(f"Invalid voice session status: {session.status}")
        self._append_snapshot(f"session:{session.session_id}", "session", asdict(session))

    def _recover_interrupted_sessions(self) -> None:
        active_states = {
            "listening",
            "recording",
            "processing",
            "thinking",
            "speaking",
            "cancelling",
        }
        for stream_id in self.journal.stream_ids("session:"):
            session = self._read_session(stream_id.removeprefix("session:"))
            if session.status not in active_states:
                continue
            self._write_session(
                replace(
                    session,
                    status="reconciliation_required",
                    previous_state=session.status,
                    revision=session.revision + 1,
                    updated_at=_now(),
                    metadata={
                        **session.metadata,
                        "restart_observed": True,
                        "external_state": "unknown",
                        "reconciliation_required": (
                            "input_device",
                            "output_device",
                            "stt_provider",
                            "tts_provider",
                            "pending_transcription",
                            "pending_synthesis",
                            "speaking_output",
                            "interruption_cancellation",
                            "artifact_availability",
                        ),
                    },
                )
            )

    def reconcile_session(
        self, session_id: str, *, target_state: str, evidence: dict[str, Any]
    ) -> VoiceSession:
        session = self.get_session(session_id)
        if session.status != "reconciliation_required":
            raise ValidationError("Voice session does not require reconciliation.")
        if target_state not in {"idle", "listening", "error", "closed"} or not evidence:
            raise ValidationError("Voice reconciliation requires explicit evidence and outcome.")
        return self.transition_session(
            session_id,
            target_state,
            expected_revision=session.revision,
            metadata={"reconciliation_evidence": evidence, "external_state": "revalidated"},
        )

    def _read_utterance(self, utterance_id: str) -> VoiceUtterance:
        replay = self.journal.replay(f"utterance:{utterance_id}")
        if not replay.records:
            raise NotFound(f"Voice utterance not found: {utterance_id}")
        raw = dict(replay.records[-1].payload)
        raw.setdefault("utterance_id", utterance_id)
        raw.setdefault("provider_id", None)
        raw.pop("voice_profile_id", None)
        raw.setdefault("priority", 100)
        raw.setdefault("state", "pending")
        raw.setdefault("created_at", _now())
        raw.setdefault("metadata", {})
        return VoiceUtterance(**raw)

    def _write_utterance(self, utterance: VoiceUtterance) -> None:
        if utterance.state not in VOICE_UTTERANCE_STATES:
            raise ValidationError(f"Invalid voice utterance state: {utterance.state}")
        self._append_snapshot(f"utterance:{utterance.utterance_id}", "utterance", asdict(utterance))

    def _recordings_root(self):
        self.recordings_root.mkdir(parents=True, exist_ok=True)
        return self.recordings_root

    def _recording_path(self, recording_id: str) -> Path:
        return self._recordings_root() / f"{recording_id}.yaml"

    def _recording_audio_path(self, recording_id: str, audio_format: str | None) -> Path:
        suffix = (audio_format or "webm").lower().lstrip(".")
        return self._recordings_root() / f"{recording_id}.{suffix}"

    def _write_recording(self, recording: VoiceRecording) -> None:
        if recording.status not in VOICE_RECORDING_STATUSES:
            raise ValidationError(f"Invalid voice recording status: {recording.status}")
        payload = asdict(recording)
        payload["audio_ref"] = recording.audio_ref
        self._append_snapshot(f"recording:{recording.recording_id}", "recording", payload)

    def _read_recording(self, recording_id: str) -> VoiceRecording:
        replay = self.journal.replay(f"recording:{recording_id}")
        if not replay.records:
            raise NotFound(f"Voice recording not found: {recording_id}")
        raw = dict(replay.records[-1].payload)
        raw.setdefault("recording_id", recording_id)
        raw.setdefault("session_id", None)
        raw.setdefault("conversation_id", None)
        raw.setdefault("agent_id", None)
        raw.setdefault("device_id", None)
        raw.setdefault("provider_id", None)
        raw.setdefault("language", "pt-BR")
        raw.setdefault("model", None)
        raw.setdefault("audio_ref", None)
        raw.setdefault("audio_format", None)
        raw.setdefault("duration_ms", None)
        raw.setdefault("transcript", None)
        raw.setdefault("status", "recorded")
        raw.setdefault("created_at", _now())
        raw.setdefault("updated_at", raw["created_at"])
        raw.setdefault("completed_at", None)
        raw.setdefault("chunks", 0)
        raw.setdefault("sequence", 0)
        raw.setdefault("total_bytes", 0)
        raw.setdefault("checksum", None)
        raw.setdefault("transcript_id", None)
        raw.setdefault("analysis_id", None)
        raw.setdefault("error", None)
        raw.setdefault("revision", 1)
        raw.setdefault("idempotency_keys", [])
        raw.setdefault("metadata", {})
        return VoiceRecording(**raw)

    def _write_audio_blob(
        self, recording_id: str, audio_base64: str, audio_format: str | None
    ) -> str:
        try:
            if "," in audio_base64 and audio_base64.strip().startswith("data:"):
                audio_base64 = audio_base64.split(",", 1)[1]
            audio_bytes = base64.b64decode(audio_base64, validate=True)
        except (ValueError, BinasciiError) as exc:
            raise ValidationError("Invalid audio payload.") from exc
        audio_path = self._recording_audio_path(recording_id, audio_format)
        audio_path.write_bytes(audio_bytes)
        return f"voice/recordings/{audio_path.name}"

    def _recording_chunks_root(self, recording_id: str) -> Path:
        root = self._recordings_root() / f"{recording_id}.chunks"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _transcripts_root(self) -> Path:
        root = self.data_dir.resolve("voice/transcripts")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _analyses_root(self) -> Path:
        root = self.data_dir.resolve("voice/analyses")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _syntheses_root(self) -> Path:
        root = self.data_dir.resolve("voice/syntheses")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _turns_root(self) -> Path:
        root = self.data_dir.resolve("voice/turns")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _get_device(self, device_id: str) -> AudioDevice:
        for device in self.list_devices():
            if device.device_id == device_id:
                return device
        raise NotFound(f"Voice device not found: {device_id}")

    def _resolve_provider_summary(self, provider_id: str | None) -> VoiceProviderSummary:
        providers = self.list_providers()
        if not providers:
            raise ValidationError("No speech providers configured.")
        if provider_id:
            for provider in providers:
                if provider.provider_id == provider_id or provider.adapter_id == provider_id:
                    return provider
            raise NotFound(f"Voice provider not found: {provider_id}")
        for provider in providers:
            if provider.adapter_type == "stt":
                return provider
        return providers[0]

    def _read_voice_pack_manifest(self, manifest_path: Path) -> VoicePackManifest:
        raw = load_structured_file(manifest_path)
        pack_id = str(raw.get("pack_id") or manifest_path.parent.name).strip()
        display_name = str(raw.get("display_name") or pack_id).strip()
        version = str(raw.get("version") or "").strip()
        provider = str(raw.get("provider") or "").strip()
        engine = str(raw.get("engine") or "").strip()
        entries: list[VoicePackEntry] = []
        for item in raw.get("voices", []):
            if not isinstance(item, dict):
                continue
            entry = self._voice_pack_entry_from_raw(manifest_path.parent, provider, engine, item)
            entries.append(entry)
        usable_count = sum(1 for entry in entries if entry.usable)
        expected_count = int(raw.get("expected_voice_count") or len(entries))
        status = "ready" if expected_count == len(entries) and usable_count == expected_count else "incomplete"
        reason = None
        if status != "ready":
            reason = f"usable_voices={usable_count}; expected_voices={expected_count}"
        return VoicePackManifest(
            pack_id=pack_id,
            display_name=display_name,
            version=version,
            provider=provider,
            engine=engine,
            voices=entries,
            status=status,
            reason=reason,
            metadata={
                **raw.get("metadata", {}),
                "manifest_reference": self._data_reference(manifest_path),
                "expected_voice_count": expected_count,
                "usable_voice_count": usable_count,
            },
        )

    def _voice_pack_roots(self) -> tuple[Path, ...]:
        return (
            self.data_dir.resolve("voice/voice-packs"),
            packaged_resources_root() / "voice" / "voice-packs",
        )

    def _voice_pack_entry_from_raw(
        self,
        pack_root: Path,
        provider: str,
        engine: str,
        raw: dict[str, Any],
    ) -> VoicePackEntry:
        voice_id = str(raw.get("voice_id") or "").strip()
        asset_reference = str(raw.get("asset_reference") or "").strip()
        asset_path = self._resolve_voice_asset_reference(asset_reference, pack_root)
        checksum = str(raw.get("checksum") or "").strip().lower()
        status = "missing"
        reason: str | None = "voice_asset_missing"
        usable = False
        if asset_reference and asset_path.is_file():
            observed = hashlib.sha256(asset_path.read_bytes()).hexdigest()
            if checksum and observed != checksum:
                status = "corrupt"
                reason = "voice_asset_checksum_mismatch"
            elif not checksum:
                status = "corrupt"
                reason = "voice_asset_checksum_missing"
            else:
                status = "ready"
                reason = None
                usable = True
        metadata = dict(raw.get("metadata", {}))
        metadata["asset_size_bytes"] = asset_path.stat().st_size if asset_path.is_file() else 0
        return VoicePackEntry(
            voice_id=voice_id,
            display_name=str(raw.get("display_name") or voice_id).strip(),
            language=str(raw.get("language") or "").strip(),
            locale=str(raw.get("locale") or "").strip(),
            voice_profile=dict(raw.get("voice_profile", {})),
            provider=str(raw.get("provider") or provider).strip(),
            engine=str(raw.get("engine") or engine).strip(),
            asset_reference=asset_reference,
            version=str(raw.get("version") or "").strip(),
            checksum=checksum,
            license=str(raw.get("license") or "").strip(),
            provenance=str(raw.get("provenance") or "").strip(),
            usable=usable,
            status=status,
            reason=reason,
            metadata=metadata,
        )

    def _resolve_voice_asset_reference(self, reference: str, pack_root: Path) -> Path:
        if not reference:
            return pack_root / ""
        if reference == "voice/models/kokoro/voices-v1.0.bin":
            settings = load_structured_file(self.data_dir.resolve("voice/kokoro-runtime.json"))
            root = settings.get("root")
            if isinstance(root, str) and root:
                return Path(root).resolve() / "models/kokoro/voices-v1.0.bin"
        packaged = resolve_package_resource_reference(reference, "voice")
        if packaged is not None:
            return packaged
        path = Path(reference).expanduser()
        if path.is_absolute():
            return path
        data_candidate = self.data_dir.resolve(reference)
        if data_candidate.exists():
            return data_candidate
        candidate = (pack_root / path).resolve()
        try:
            candidate.relative_to(pack_root.resolve())
            return candidate
        except ValueError:
            return self.data_dir.resolve(reference)

    def _data_reference(self, path: Path) -> str:
        try:
            return package_resource_reference("voice", path)
        except ValidationError:
            pass
        try:
            relative = path.relative_to(self.data_dir.root)
        except ValueError:
            return "external://voice-pack"
        return relative.as_posix()

    def _normalize_voice_settings(self, raw: dict[str, Any]) -> dict[str, Any]:
        original_version = int(raw.get("schema_version", 1))
        stt_provider_id = self._normalize_stt_provider_id(
            raw.get("stt_provider_id"),
            raw.get("provider_id"),
        )
        raw["stt_provider_id"] = stt_provider_id
        raw["provider_id"] = stt_provider_id
        raw.setdefault("stt_model", raw.get("model", "tiny"))
        if original_version < 3 and raw["stt_model"] == "auto":
            raw["stt_model"] = "base"
            raw["model"] = "base"
        raw.setdefault("stt_device", "cpu")
        raw.setdefault("stt_compute_type", "int8")
        raw.setdefault("input_device_id", raw.get("device_id"))
        raw.setdefault("output_device_id", None)
        raw.setdefault("voice_analysis_provider_id", "local_acoustic_analysis")
        raw.setdefault("vad_provider_id", None)
        raw.setdefault("vad_enabled", True)
        raw.setdefault("silence_threshold", 0.001)
        raw.setdefault("min_speech_duration_ms", 250)
        raw.setdefault("min_silence_duration_ms", 500)
        raw.setdefault("max_utterance_duration_ms", 120_000)
        raw.setdefault("recording_retention", "metadata")
        raw.setdefault("store_raw_audio", False)
        raw.setdefault("delete_after_transcription", True)
        raw.setdefault("retention_days", 30)
        raw.setdefault("keep_transcripts", True)
        raw.setdefault("keep_analysis", True)
        raw.setdefault("keep_synthesis_audio", False)
        raw.setdefault("temp_file_max_age_hours", 24)
        raw.setdefault("failed_recording_retention_days", 7)
        raw.setdefault("conversation_mode_defaults", {})
        if not raw.get("tts_provider_id"):
            raw["tts_provider_id"] = "piper"
        raw.setdefault("tts_model", None)
        raw.setdefault("default_tts_voice", raw.pop("tts_voice_id", None))
        raw.setdefault("preferred_voice_gender", "female")
        raw.setdefault("provider_configuration_references", {})
        raw.setdefault("policy_version", "voice-configuration-v1")
        raw["schema_version"] = 3
        if original_version < 3:
            raw["metadata"] = {
                **raw.get("metadata", {}),
                "settings_migration": {
                    "from_version": original_version,
                    "to_version": 3,
                    "legacy_provider_id": raw.get("provider_id"),
                },
            }
        return raw

    def _append_snapshot(
        self, stream_id: str, entity: str, payload: dict[str, Any], *, legacy: bool = False
    ) -> None:
        replay = self.journal.replay(stream_id)
        if replay.records and replay.records[-1].payload == payload:
            return
        revision = len(replay.records) + 1
        status = str(payload.get("status") or payload.get("state") or "observed")
        fact_type = f"{entity}.{status}"
        if payload.get("metadata", {}).get("restart_observed"):
            fact_type = "session.reconciliation_required"
        if legacy:
            fact_type = f"{entity}.legacy_imported"
        fingerprint_seed = hashlib.sha256(
            f"{stream_id}:{revision}:{fact_type}:{canonical_json(payload)}".encode("utf-8")
        ).hexdigest()
        lineage = (replay.records[-1].fingerprint,) if replay.records else ()
        self.journal.append(
            VoiceRecordDraft(
                stream_id=stream_id,
                fact_type=fact_type,
                revision=revision,
                payload=payload,
                idempotency_key=fingerprint_seed,
                lineage=lineage,
                retention={"raw_audio_embedded": False},
            ),
            expected_revision=revision - 1,
        )

    def _import_legacy_persistence_if_needed(self) -> None:
        mappings = (
            ("session", self._sessions_root(), "session_id"),
            ("utterance", self._utterances_root(), "utterance_id"),
            ("recording", self._recordings_root(), "recording_id"),
            ("synthesis", self._syntheses_root(), "synthesis_id"),
        )
        for entity, root, identity_field in mappings:
            if self.journal.stream_ids(f"{entity}:"):
                continue
            for path in sorted(root.glob("*.yaml")):
                raw = load_structured_file(path)
                if not raw:
                    continue
                raw.setdefault(identity_field, path.stem)
                if entity == "session":
                    raw.pop("embodiment_id", None)
                    raw.pop("avatar_session_id", None)
                    raw.pop("animation_state", None)
                self._append_snapshot(f"{entity}:{path.stem}", entity, raw, legacy=True)

    def _normalize_stt_provider_id(
        self, candidate: str | None, legacy_provider_id: str | None
    ) -> str | None:
        value = (candidate or legacy_provider_id or "").strip()
        if not value:
            return "faster_whisper"
        if value == "piper":
            return "faster_whisper"
        return value

    def _get_stt_provider_id(self) -> str | None:
        settings = self.get_settings()
        return settings.stt_provider_id or settings.provider_id or "faster_whisper"

    def _resolve_configured_provider(
        self,
        *,
        capability: str,
        adapter_type: str,
        configured_provider_id: str | None,
    ) -> VoiceProviderSelection:
        selection = VoiceProviderSelection(
            capability=capability,
            configured_provider_id=configured_provider_id,
            state="unavailable",
            metadata={"reason": "speech_adapter_runtime_unavailable"},
        )
        if self.speech_adapters is not None and configured_provider_id:
            manifest = next(
                (
                    item
                    for item in self.speech_adapters.list_adapters()
                    if item.adapter_type == adapter_type
                    and configured_provider_id in {item.adapter_id, item.provider_id}
                ),
                None,
            )
            if manifest is not None:
                health = self.speech_adapters.adapter_health(manifest.adapter_id)
                state = {
                    "available": "supported",
                    "degraded": "degraded",
                    "unconfigured": "configured",
                }.get(health.status, "unavailable")
                selection = VoiceProviderSelection(
                    capability=capability,
                    configured_provider_id=configured_provider_id,
                    state=state,
                    adapter_id=manifest.adapter_id,
                    provider_id=manifest.provider_id,
                    health=asdict(health),
                    metadata={
                        "mock": bool(manifest.metadata.get("mock", False)),
                        "selection": "exact_configured_provider",
                    },
                )
            else:
                selection = replace(
                    selection,
                    metadata={"reason": "configured_provider_not_registered"},
                )
        if selection.state not in VOICE_PROVIDER_SELECTION_STATES:
            raise ValidationError("Invalid voice provider selection state.")
        self.events.emit("voice.provider.resolved", "voice", asdict(selection))
        return selection

    def _sessions_root(self):
        root = self.data_dir.resolve("voice/sessions")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _utterances_root(self):
        root = self.data_dir.resolve("voice/utterances")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _session_path(self, session_id: str):
        return self._sessions_root() / f"{session_id}.yaml"

    def _utterance_path(self, utterance_id: str):
        return self._utterances_root() / f"{utterance_id}.yaml"


def _is_likely_repeated_transcription_echo(text: str) -> bool:
    words = re.sub(r"[^\w\s]", " ", text.lower(), flags=re.UNICODE).split()
    if len(words) < 16:
        return False
    trigrams: dict[str, int] = {}
    for index in range(0, len(words) - 2):
        key = " ".join(words[index : index + 3])
        trigrams[key] = trigrams.get(key, 0) + 1
    repeated_que_ratio = sum(1 for word in words if word in {"que", "é", "e"}) / len(words)
    return (max(trigrams.values()) if trigrams else 0) >= 4 or repeated_que_ratio > 0.72


def _now() -> str:
    return datetime.now(UTC).isoformat()
