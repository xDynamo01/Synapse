from __future__ import annotations

import os
from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Any

from synapse.audio.models import AudioInputRequest, AudioOutputRequest
from synapse.audio.runtime import AudioRuntime
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound, ValidationError
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.multimodal.runtime import MultimodalCommunicationRuntime
from synapse.observability.correlation import current_correlation_fields
from synapse.perception.runtime import PerceptionRuntime
from synapse.speech_pipeline.models import (
    SPEECH_PIPELINE_STATUSES,
    SpeechInputTurn,
    SpeechOutputTurn,
    SpeechPipelineSession,
    SpeechPipelineSummary,
)
from synapse.voice.runtime import VoiceRuntime

DEFAULT_POLICY: dict[str, Any] = {
    "enabled": True,
    "complete_mock_utterance_immediately": True,
    "emit_perception_signals": True,
    "emit_multimodal_events": True,
}


class SpeechPipelineRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        events: EventBus,
        audio: AudioRuntime,
        voice: VoiceRuntime,
        perception: PerceptionRuntime,
        multimodal: MultimodalCommunicationRuntime,
    ) -> None:
        self.data_dir = data_dir
        self.events = events
        self.audio = audio
        self.voice = voice
        self.perception = perception
        self.multimodal = multimodal
        self.dev_mode = os.getenv("SYNAPSE_DEV_MODE", "").lower() in {"1", "true", "yes"}

    def create_session(
        self,
        audio_session_id: str,
        voice_session_id: str | None = None,
        multimodal_session_id: str | None = None,
        agent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        pipeline_session_id: str | None = None,
    ) -> SpeechPipelineSession:
        audio_session = self.audio.get_session(audio_session_id)
        if voice_session_id:
            self.voice.get_session(voice_session_id)
        if multimodal_session_id:
            self.multimodal.get_session(multimodal_session_id)
        session = SpeechPipelineSession(
            audio_session_id=audio_session_id,
            voice_session_id=voice_session_id,
            multimodal_session_id=multimodal_session_id,
            agent_id=agent_id or audio_session.agent_id,
            pipeline_session_id=(
                pipeline_session_id
                or SpeechPipelineSession(audio_session_id=audio_session_id).pipeline_session_id
            ),
            metadata=metadata or {},
        )
        self._write_session(session)
        self.events.emit("speech_pipeline.session.created", "speech_pipeline", asdict(session))
        return session

    def get_session(self, session_id: str) -> SpeechPipelineSession:
        return self._read_session(session_id)

    def list_sessions(self, status: str | None = None) -> list[SpeechPipelineSession]:
        if status and status not in SPEECH_PIPELINE_STATUSES:
            raise ValidationError(f"Invalid speech pipeline status: {status}")
        sessions = [
            self._read_session(path.stem) for path in sorted(self._sessions_root().glob("*.yaml"))
        ]
        if status:
            sessions = [session for session in sessions if session.status == status]
        return sorted(sessions, key=lambda item: (item.updated_at, item.pipeline_session_id))

    def pause_session(self, session_id: str) -> SpeechPipelineSession:
        session = self._set_status(session_id, "paused")
        self.events.emit("speech_pipeline.session.paused", "speech_pipeline", asdict(session))
        return session

    def resume_session(self, session_id: str) -> SpeechPipelineSession:
        session = self._set_status(session_id, "idle")
        self.events.emit("speech_pipeline.session.resumed", "speech_pipeline", asdict(session))
        return session

    def close_session(self, session_id: str) -> SpeechPipelineSession:
        session = self._set_status(session_id, "closed")
        self.events.emit("speech_pipeline.session.closed", "speech_pipeline", asdict(session))
        return session

    def process_mock_input(self, session_id: str, text: str) -> SpeechInputTurn:
        _require_dev_mode(self.dev_mode)
        policy = self.load_policy()
        self._ensure_enabled(policy)
        session = self._set_status(session_id, "listening")
        try:
            result = self.audio.transcribe_mock(
                AudioInputRequest(session_id=session.audio_session_id),
                text,
            )
            signal_id = None
            if policy.get("emit_perception_signals", True):
                signal = self.perception.signal_from_speech_to_text(
                    result,
                    session_id=session.audio_session_id,
                    multimodal_session_id=session.multimodal_session_id,
                )
                signal_id = signal.signal_id
                if policy.get("emit_multimodal_events", True):
                    self.perception.emit_signal(signal)
            if policy.get("emit_multimodal_events", True) and session.multimodal_session_id:
                self.multimodal.emit_event(
                    session_id=session.multimodal_session_id,
                    channel="voice",
                    event_type="speech_pipeline.input.processed",
                    source=session.agent_id or "speech_pipeline",
                    payload=asdict(result),
                    metadata={"pipeline_session_id": session.pipeline_session_id},
                )
            fields = current_correlation_fields()
            turn = SpeechInputTurn(
                pipeline_session_id=session.pipeline_session_id,
                audio_session_id=session.audio_session_id,
                transcript=result.text,
                confidence=result.confidence,
                perception_signal_id=signal_id,
                correlation_id=fields.get("correlation_id"),
                causation_id=fields.get("causation_id"),
                metadata={"provider_id": result.provider_id},
            )
            self._write_input_turn(turn)
            self._set_status(session_id, "idle")
            self.events.emit("speech_pipeline.input.processed", "speech_pipeline", asdict(turn))
            return turn
        except Exception as exc:
            self._fail_session(session_id, exc)
            raise

    def process_mock_output(self, session_id: str, text: str) -> SpeechOutputTurn:
        _require_dev_mode(self.dev_mode)
        policy = self.load_policy()
        self._ensure_enabled(policy)
        session = self._set_status(session_id, "processing")
        if not session.voice_session_id:
            raise ValidationError(f"Speech pipeline has no voice session: {session_id}")
        try:
            utterance = self.voice.queue_utterance(session.voice_session_id, text)
            result = self.audio.synthesize_mock(
                AudioOutputRequest(session_id=session.audio_session_id, text=text)
            )
            ready = self.voice.mark_ready(utterance.utterance_id)
            if policy.get("complete_mock_utterance_immediately", True):
                utterance = self.voice.mark_completed(ready.utterance_id)
                status = "idle"
            else:
                utterance = ready
                status = "speaking"
            if policy.get("emit_perception_signals", True):
                signal = self.perception.signal_from_text_to_speech(
                    result,
                    session_id=session.audio_session_id,
                    multimodal_session_id=session.multimodal_session_id,
                )
                if policy.get("emit_multimodal_events", True):
                    self.perception.emit_signal(signal)
            if policy.get("emit_multimodal_events", True) and session.multimodal_session_id:
                self.multimodal.emit_event(
                    session_id=session.multimodal_session_id,
                    channel="audio",
                    event_type="speech_pipeline.output.processed",
                    source=session.agent_id or "speech_pipeline",
                    payload=asdict(result),
                    metadata={
                        "pipeline_session_id": session.pipeline_session_id,
                        "utterance_id": utterance.utterance_id,
                    },
                )
            fields = current_correlation_fields()
            turn = SpeechOutputTurn(
                pipeline_session_id=session.pipeline_session_id,
                voice_session_id=session.voice_session_id,
                utterance_id=utterance.utterance_id,
                text=text,
                output_ref=result.output_ref,
                correlation_id=fields.get("correlation_id"),
                causation_id=fields.get("causation_id"),
                metadata={"provider_id": result.provider_id, "utterance_state": utterance.state},
            )
            self._write_output_turn(turn)
            self._set_status(session_id, status)
            self.events.emit("speech_pipeline.output.processed", "speech_pipeline", asdict(turn))
            return turn
        except Exception as exc:
            self._fail_session(session_id, exc)
            raise

    def list_input_turns(self, session_id: str) -> list[SpeechInputTurn]:
        self.get_session(session_id)
        turns = [
            self._read_input_turn(path.stem)
            for path in sorted(self._input_turns_root().glob("*.yaml"))
        ]
        return sorted(
            [turn for turn in turns if turn.pipeline_session_id == session_id],
            key=lambda item: (item.created_at, item.turn_id),
        )

    def list_output_turns(self, session_id: str) -> list[SpeechOutputTurn]:
        self.get_session(session_id)
        turns = [
            self._read_output_turn(path.stem)
            for path in sorted(self._output_turns_root().glob("*.yaml"))
        ]
        return sorted(
            [turn for turn in turns if turn.pipeline_session_id == session_id],
            key=lambda item: (item.created_at, item.turn_id),
        )

    def summarize_session(self, session_id: str) -> SpeechPipelineSummary:
        session = self.get_session(session_id)
        inputs = self.list_input_turns(session_id)
        outputs = self.list_output_turns(session_id)
        return SpeechPipelineSummary(
            session=session,
            input_turn_count=len(inputs),
            output_turn_count=len(outputs),
            latest_input=inputs[-1] if inputs else None,
            latest_output=outputs[-1] if outputs else None,
            metadata={"policy": self.load_policy()},
        )

    def session_count(self) -> int:
        return len(self.list_sessions())

    def load_policy(self) -> dict[str, Any]:
        raw = load_structured_file(self.data_dir.resolve("config/speech_pipeline_policy.yaml"))
        policy_raw = raw.get("speech_pipeline", raw)
        policy = dict(DEFAULT_POLICY)
        policy.update(policy_raw)
        return policy

    def _ensure_enabled(self, policy: dict[str, Any]) -> None:
        if not policy.get("enabled", True):
            raise ValidationError("Speech pipeline is disabled by policy.")

    def _set_status(self, session_id: str, status: str) -> SpeechPipelineSession:
        if status not in SPEECH_PIPELINE_STATUSES:
            raise ValidationError(f"Invalid speech pipeline status: {status}")
        session = self.get_session(session_id)
        if session.status == "closed" and status != "closed":
            raise ValidationError(f"Speech pipeline session is closed: {session_id}")
        updated = replace(session, status=status, updated_at=_now())
        self._write_session(updated)
        return updated

    def _fail_session(self, session_id: str, exc: Exception) -> None:
        try:
            session = self._set_status(session_id, "failed")
            self.events.emit(
                "speech_pipeline.failed",
                "speech_pipeline",
                {**asdict(session), "error": str(exc)},
            )
        except Exception:
            self.events.emit(
                "speech_pipeline.failed",
                "speech_pipeline",
                {"pipeline_session_id": session_id, "error": str(exc)},
            )

    def _read_session(self, session_id: str) -> SpeechPipelineSession:
        path = self._session_path(session_id)
        if not path.exists():
            raise NotFound(f"Speech pipeline session not found: {session_id}")
        raw = load_structured_file(path)
        raw.setdefault("pipeline_session_id", session_id)
        raw.setdefault("voice_session_id", None)
        raw.setdefault("multimodal_session_id", None)
        raw.setdefault("agent_id", None)
        raw.setdefault("status", "idle")
        raw.setdefault("created_at", _now())
        raw.setdefault("updated_at", raw["created_at"])
        raw.setdefault("metadata", {})
        return SpeechPipelineSession(**raw)

    def _write_session(self, session: SpeechPipelineSession) -> None:
        if session.status not in SPEECH_PIPELINE_STATUSES:
            raise ValidationError(f"Invalid speech pipeline status: {session.status}")
        dump_structured_file(self._session_path(session.pipeline_session_id), asdict(session))

    def _read_input_turn(self, turn_id: str) -> SpeechInputTurn:
        raw = load_structured_file(self._input_turn_path(turn_id))
        raw.setdefault("turn_id", turn_id)
        raw.setdefault("confidence", None)
        raw.setdefault("perception_signal_id", None)
        raw.setdefault("correlation_id", None)
        raw.setdefault("causation_id", None)
        raw.setdefault("created_at", _now())
        raw.setdefault("metadata", {})
        return SpeechInputTurn(**raw)

    def _write_input_turn(self, turn: SpeechInputTurn) -> None:
        dump_structured_file(self._input_turn_path(turn.turn_id), asdict(turn))

    def _read_output_turn(self, turn_id: str) -> SpeechOutputTurn:
        raw = load_structured_file(self._output_turn_path(turn_id))
        raw.setdefault("turn_id", turn_id)
        raw.setdefault("output_ref", None)
        raw.setdefault("correlation_id", None)
        raw.setdefault("causation_id", None)
        raw.setdefault("created_at", _now())
        raw.setdefault("metadata", {})
        return SpeechOutputTurn(**raw)

    def _write_output_turn(self, turn: SpeechOutputTurn) -> None:
        dump_structured_file(self._output_turn_path(turn.turn_id), asdict(turn))

    def _sessions_root(self):
        root = self.data_dir.resolve("speech_pipeline/sessions")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _input_turns_root(self):
        root = self.data_dir.resolve("speech_pipeline/input_turns")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _output_turns_root(self):
        root = self.data_dir.resolve("speech_pipeline/output_turns")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _session_path(self, session_id: str):
        return self._sessions_root() / f"{session_id}.yaml"

    def _input_turn_path(self, turn_id: str):
        return self._input_turns_root() / f"{turn_id}.yaml"

    def _output_turn_path(self, turn_id: str):
        return self._output_turns_root() / f"{turn_id}.yaml"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _require_dev_mode(enabled: bool) -> None:
    if not enabled:
        raise ValidationError("Development speech-pipeline doubles are disabled.")
