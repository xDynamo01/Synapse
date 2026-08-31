from types import SimpleNamespace
from unittest.mock import Mock

from acceptance.voice_support import completed_recording, runtime_fixture


def test_voice_conversation_runs_two_turns() -> None:
    directory, _, runtime = runtime_fixture()
    try:
        runtime.chat.submit_turn = Mock(
            side_effect=[
                SimpleNamespace(response="one", conversation_id="voice-conversation", message=None),
                SimpleNamespace(response="two", conversation_id="voice-conversation", message=None),
            ]
        )
        session = runtime.voice.create_session("artemis", conversation_id="voice-conversation")
        runtime.voice.transition_session(session.session_id, "listening")
        results = []
        for index in range(2):
            runtime.voice.transition_session(session.session_id, "recording")
            recording = completed_recording(runtime, session.session_id, f"audio-{index}")
            results.append(
                runtime.voice.run_conversation_turn(
                    session.session_id,
                    recording.recording_id,
                    idempotency_key=f"turn-{index}",
                )
            )
        assert runtime.chat.submit_turn.call_count == 2
        assert results[0].recording_id != results[1].recording_id
        assert results[0].utterance_id != results[1].utterance_id
        assert results[0].synthesis_id != results[1].synthesis_id
        assert {item.conversation_id for item in results} == {"voice-conversation"}
        assert runtime.voice.get_session(session.session_id).status == "listening"
    finally:
        directory.cleanup()
