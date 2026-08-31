from acceptance.perception_support import ControlledScreen, ControlledVision, runtime_fixture
from synapse.perception.models import PerceptionSignal


def test_voice_and_screen_observations_are_temporally_fused_without_concatenation() -> None:
    directory, _, runtime = runtime_fixture()
    try:
        runtime.capture.provider = ControlledScreen()
        runtime.vision.vision_provider = ControlledVision()
        correlation_id = "voice-screen-e2e"
        voice = runtime.perception.ingest_signal(PerceptionSignal(
            type="speech.transcribed", modality="speech", source="voice",
            values={"text": "what does this error mean?"}, confidence=0.91,
            correlation_id=correlation_id, sensitivity="sensitive",
        ))
        image = runtime.vision.capture_screenshot(owner="acceptance", source_id="1")
        runtime.vision.analyze_image(image, correlation_id=correlation_id)
        source_ids = [item.id for item in runtime.perception.list_observations(correlation_id=correlation_id)]
        fusion = runtime.multimodal.fuse(source_ids, correlation_id=correlation_id)
        assert fusion.metadata["modalities"] == ["screen", "speech"]
        assert fusion.confidence == 0.82
        assert voice.values["text"] == "[REDACTED]"
        assert "text" not in fusion.interpretation
        assert len(fusion.source_observation_ids) == 2
    finally:
        directory.cleanup()
