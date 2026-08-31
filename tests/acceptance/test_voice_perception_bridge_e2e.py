from acceptance.voice_support import completed_recording, runtime_fixture


class CollectingSink:
    def __init__(self) -> None:
        self.signals = []

    def emit(self, signal) -> None:
        self.signals.append(signal)


class FailingSink:
    def emit(self, signal) -> None:
        raise RuntimeError("sink unavailable")


def test_voice_perception_signals_are_redacted_and_optional() -> None:
    sink = CollectingSink()
    directory, _, runtime = runtime_fixture(perception_sink=sink)
    try:
        session = runtime.voice.create_session("artemis", conversation_id="voice-conversation")
        runtime.voice.transition_session(session.session_id, "listening")
        runtime.voice.transition_session(session.session_id, "recording")
        recording = completed_recording(runtime, session.session_id)
        runtime.voice.transition_session(session.session_id, "processing")
        result = runtime.voice.complete_voice_message(recording.recording_id)

        assert result.status == "success"
        assert {item.type for item in sink.signals} >= {
            "speech.transcribed",
            "voice.volume",
            "voice.peak",
            "voice.analysis_completed",
            "speech.started",
            "speech.ended",
        }
        assert all(item.provenance for item in sink.signals)
        assert all(item.correlation_id for item in sink.signals)
        assert all(item.session_id == session.session_id for item in sink.signals)
        assert all(item.conversation_id == "voice-conversation" for item in sink.signals)
        assert all("audio" not in item.values for item in sink.signals)
        runtime.voice.perception_sink = FailingSink()
        second = completed_recording(runtime, key="second")
        assert runtime.voice.complete_voice_message(second.recording_id).status == "success"
    finally:
        directory.cleanup()
