from datetime import UTC, datetime, timedelta

from acceptance.perception_support import png_bytes, runtime_fixture
from synapse.core.app import create_runtime
from synapse.perception.models import PerceptionSignal


def test_restart_preserves_metadata_and_cleanup_is_idempotent() -> None:
    directory, settings, runtime = runtime_fixture()
    try:
        expired = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        signal = runtime.perception.ingest_signal(PerceptionSignal(
            type="system.expired", modality="system", source="system", values={"state": "old"}, expires_at=expired,
        ))
        restarted = create_runtime(settings)
        assert restarted.perception.get_signal(signal.id).id == signal.id
        image = restarted.vision.store_image(png_bytes(), "image/png", owner="retention-test")
        raw_path = restarted.capture.resolve_path(image)
        active_marker = type(raw_path)(f"{raw_path}.active")
        active_marker.touch()
        protected = restarted.perception.cleanup(
            dry_run=True, now=datetime.now(UTC) + timedelta(minutes=20)
        )
        assert protected.raw_assets == 0
        active_marker.unlink()
        preview = restarted.perception.cleanup(dry_run=True)
        assert preview.expired_signals == 1
        applied = restarted.perception.cleanup(dry_run=False)
        assert applied.expired_signals == 1
        assert restarted.perception.cleanup(dry_run=False).expired_signals == 0
    finally:
        directory.cleanup()
