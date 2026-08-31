import base64

from acceptance.voice_support import runtime_fixture, valid_wav


def test_voice_retention_dry_run_cleanup_and_idempotency() -> None:
    directory, _, runtime = runtime_fixture()
    try:
        recording = runtime.voice.create_recording(
            audio_base64=base64.b64encode(valid_wav()).decode("ascii"),
            audio_format="wav",
            transcript="keep transcript",
        )
        active = runtime.voice.start_recording(audio_format="audio/wav")
        active = runtime.voice.append_recording_chunk(
            active.recording_id,
            valid_wav(),
            sequence=0,
            idempotency_key="active-audio",
        )
        dry_run = runtime.voice.cleanup_voice_storage(dry_run=True)
        cleanup = runtime.voice.cleanup_voice_storage()
        repeated = runtime.voice.cleanup_voice_storage()

        assert recording.audio_ref is None
        assert dry_run.recordings_deleted == 0
        assert cleanup.recordings_deleted == 0
        assert cleanup.reclaimed_bytes == 0
        assert repeated.recordings_deleted == 0
        assert runtime.voice.get_recording(recording.recording_id).transcript == "keep transcript"
        assert runtime.voice.get_recording(active.recording_id).status == "recording"
        assert active.chunks == 1
    finally:
        directory.cleanup()
