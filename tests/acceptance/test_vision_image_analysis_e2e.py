from acceptance.perception_support import ControlledVision, png_bytes, runtime_fixture


def test_explicit_image_flows_from_capture_to_perception() -> None:
    directory, _, runtime = runtime_fixture()
    try:
        runtime.vision.vision_provider = ControlledVision()
        image = runtime.vision.store_image(png_bytes(), "image/png", owner="acceptance")
        result = runtime.vision.analyze_image(image, correlation_id="image-e2e", delete_raw_after=True)
        observations = runtime.perception.list_observations(correlation_id="image-e2e")
        assert result.provider == "controlled_acceptance_vision"
        assert observations[0].type == "vision.document_visible"
        assert observations[0].confidence == 0.82
        assert not runtime.capture.resolve_path(image).exists()
    finally:
        directory.cleanup()
