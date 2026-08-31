from acceptance.voice_support import runtime_fixture


class InterruptionSink:
    def __init__(self) -> None:
        self.signals = []

    def emit(self, signal) -> None:
        self.signals.append(signal)


def test_voice_barge_in_cancels_synthesis_and_records() -> None:
    sink = InterruptionSink()
    directory, _, runtime = runtime_fixture(perception_sink=sink)
    try:
        session = runtime.voice.create_session("artemis")
        utterance = runtime.voice.queue_utterance(session.session_id, "response")
        synthesis = runtime.voice.synthesize_utterance(
            session.session_id, utterance.utterance_id, utterance.text
        )
        runtime.voice.transition_session(session.session_id, "speaking")
        recording = runtime.voice.interrupt_session(session.session_id)

        assert recording is not None
        assert runtime.voice.get_synthesis(synthesis.synthesis_id).status == "cancelled"
        assert runtime.voice.get_session(session.session_id).status == "recording"
        assert not [item for item in runtime.voice.list_syntheses() if item.status == "running"]
        assert any(item.type == "voice.interruption" for item in sink.signals)
    finally:
        directory.cleanup()
