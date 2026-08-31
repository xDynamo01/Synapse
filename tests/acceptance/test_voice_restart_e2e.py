import pytest

from acceptance.voice_support import runtime_fixture, valid_wav
from synapse.core.app import create_runtime


@pytest.mark.parametrize("interrupted_state", ["recording", "processing", "thinking", "speaking"])
def test_voice_restart_preserves_history_without_opening_device(interrupted_state: str) -> None:
    directory, settings, runtime = runtime_fixture()
    try:
        session = runtime.voice.create_session("artemis")
        runtime.voice.transition_session(session.session_id, "listening")
        runtime.voice.transition_session(session.session_id, "recording")
        partial_recording = None
        if interrupted_state == "recording":
            partial_recording = runtime.voice.start_recording(
                session_id=session.session_id,
                agent_id="artemis",
                audio_format="audio/wav",
            )
            runtime.voice.append_recording_chunk(
                partial_recording.recording_id,
                valid_wav(),
                sequence=0,
                idempotency_key="partial-before-restart",
            )
        if interrupted_state in {"processing", "thinking", "speaking"}:
            runtime.voice.transition_session(session.session_id, "processing")
        if interrupted_state in {"thinking", "speaking"}:
            runtime.voice.transition_session(session.session_id, "thinking")
        if interrupted_state == "speaking":
            runtime.voice.transition_session(session.session_id, "speaking")

        reopened = create_runtime(settings)
        persisted = reopened.voice.get_session(session.session_id)

        assert persisted.status == "reconciliation_required"
        assert persisted.previous_state == interrupted_state
        assert persisted.metadata["external_state"] == "unknown"
        if partial_recording is not None:
            recovered = reopened.voice.get_recording(partial_recording.recording_id)
            assert recovered.status == "recording"
            assert recovered.error is None
        assert reopened.audio.devices.last_error is None
    finally:
        directory.cleanup()
