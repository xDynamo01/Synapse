import pytest

from acceptance.perception_support import ControlledScreen, runtime_fixture
from synapse.perception.models import PerceptionSignal


def test_transcript_redaction_and_sensitive_window_denial() -> None:
    directory, _, runtime = runtime_fixture()
    try:
        signal = runtime.perception.ingest_signal(PerceptionSignal(
            type="speech.transcribed", modality="speech", source="voice",
            values={"text": "private transcript", "duration_ms": 100}, sensitivity="restricted",
        ))
        assert signal.values["text"] == "[REDACTED]"
        runtime.capture.provider = ControlledScreen()
        with pytest.raises(Exception) as raised:
            runtime.vision.capture_screenshot(owner="acceptance", source_id="1", policy_context={"window_title": "Incognito Passwords"})
        assert getattr(raised.value, "code", None) == "screenshot_permission_denied"
        events = runtime.events.tail(500)
        assert "private transcript" not in str(events)
    finally:
        directory.cleanup()
