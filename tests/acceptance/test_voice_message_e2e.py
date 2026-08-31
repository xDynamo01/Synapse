from unittest.mock import Mock

from acceptance.voice_support import completed_recording, runtime_fixture
from synapse.core.app import create_runtime


def test_voice_message_persists_across_restart_without_chat() -> None:
    directory, settings, runtime = runtime_fixture()
    try:
        runtime.chat.submit_turn = Mock()
        recording = completed_recording(runtime)
        result = runtime.voice.complete_voice_message(recording.recording_id)
        reopened = create_runtime(settings)

        assert reopened.voice.get_recording(recording.recording_id).transcript == result.text
        assert reopened.voice._read_voice_message_result(result.transcript_id).text == result.text
        runtime.chat.submit_turn.assert_not_called()
        assert all(not item.metadata.get("mock") for item in reopened.speech_adapters.list_adapters())
        diagnostics = reopened.health.summary().voice_diagnostics
        assert diagnostics["decoder"]["status"] == "ready"
        assert diagnostics["storage"]["status"] == "ready"
        assert diagnostics["retention"]["status"] == "configured"
        assert diagnostics["vad"]["status"] == "ready"
    finally:
        directory.cleanup()
