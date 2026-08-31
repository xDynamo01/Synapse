from acceptance.voice_support import completed_recording, runtime_fixture


def test_default_voice_sink_ingests_redacted_canonical_signals() -> None:
    directory, _, runtime = runtime_fixture()
    try:
        session = runtime.voice.create_session("artemis", conversation_id="voice-perception-e2e")
        runtime.voice.transition_session(session.session_id, "listening")
        runtime.voice.transition_session(session.session_id, "recording")
        recording = completed_recording(runtime, session.session_id)
        runtime.voice.transition_session(session.session_id, "processing")
        assert runtime.voice.complete_voice_message(recording.recording_id).status == "success"
        signals = runtime.perception.list_signals(session_id=session.session_id)
        assert {item.type for item in signals} >= {"speech.transcribed", "speech.started", "speech.ended"}
        transcript = next(item for item in signals if item.type == "speech.transcribed")
        assert "text" not in transcript.values
        assert transcript.metadata.get("text_redacted") is True
        assert all("audio" not in item.values for item in signals)
        assert len(runtime.perception.list_observations(session_id=session.session_id)) == len(signals)
    finally:
        directory.cleanup()
