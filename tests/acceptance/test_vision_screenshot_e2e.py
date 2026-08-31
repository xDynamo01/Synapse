from acceptance.perception_support import ControlledScreen, ControlledVision, runtime_fixture


def test_authorized_screenshot_is_short_lived_and_structured() -> None:
    directory, _, runtime = runtime_fixture()
    try:
        runtime.capture.provider = ControlledScreen()
        runtime.vision.vision_provider = ControlledVision()
        image = runtime.vision.capture_screenshot(owner="acceptance", source_id="1", policy_context={"application": "editor"})
        result = runtime.vision.analyze_image(image, correlation_id="screen-e2e")
        assert result.observations[0]["type"] == "screen.error_visible"
        assert not runtime.capture.resolve_path(image).exists()
        assert runtime.perception.list_observations(correlation_id="screen-e2e")[0].metadata["modality"] == "screen"
    finally:
        directory.cleanup()
