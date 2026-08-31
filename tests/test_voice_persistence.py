from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from synapse.core.app import create_runtime
from synapse.core.exceptions import NotFound, ValidationError
from synapse.voice.persistence_models import VoiceRecordDraft, canonical_json
from synapse.voice.sqlite_persistence import _MIGRATION_CHECKSUM, SQLiteVoiceJournal
from test_voice_runtime import runtime_in_tempdir


@pytest.fixture
def runtime_factory():
    directories = []

    def factory():
        directory, settings, runtime = runtime_in_tempdir()
        directories.append(directory)
        return runtime, settings

    yield factory
    for directory in directories:
        directory.cleanup()


def draft(
    stream: str = "session:opaque-session",
    revision: int = 1,
    *,
    key: str = "key-1",
    lineage: tuple[str, ...] = (),
) -> VoiceRecordDraft:
    return VoiceRecordDraft(
        stream_id=stream,
        fact_type="session.created",
        revision=revision,
        payload={"status": "idle", "session_id": "opaque-session"},
        idempotency_key=key,
        lineage=lineage,
        retention={"raw_audio_embedded": False},
    )


def test_canonical_determinism_and_occurrence_metadata_exclusion() -> None:
    assert canonical_json({"b": 2, "a": 1}) == canonical_json({"a": 1, "b": 2})
    first = draft()
    second = replace(first, record_id="different", occurred_at="2030-01-01T00:00:00+00:00")
    assert first.fingerprint == second.fingerprint


def test_append_exact_read_idempotency_replay_and_conflicts(tmp_path: Path) -> None:
    store = SQLiteVoiceJournal(tmp_path / "voice.sqlite3")
    first = store.append(draft(), expected_revision=0)
    duplicate = store.append(replace(draft(), record_id="other"), expected_revision=0)
    assert duplicate.record_id == first.record_id
    assert store.read_exact(first.record_id, first.fingerprint) == first
    with pytest.raises(NotFound):
        store.read_exact(first.record_id, "0" * 64)
    second = store.append(
        draft(revision=2, key="key-2", lineage=(first.fingerprint,)), expected_revision=1
    )
    replay = store.replay(first.stream_id)
    assert replay.records == (first, second)
    assert replay.complete
    assert store.read_causal_range(first.stream_id, 2, 2) == (second,)
    with pytest.raises(ValidationError, match="optimistic revision conflict"):
        store.append(draft(revision=3, key="key-3"), expected_revision=0)
    with pytest.raises(ValidationError, match="lineage gap"):
        store.append(draft(revision=4, key="key-4"), expected_revision=2)
    with pytest.raises(ValidationError, match="idempotency conflict"):
        store.append(replace(draft(key="key-1"), payload={"status": "other"}))


def test_append_only_schema_migration_health_and_corruption(tmp_path: Path) -> None:
    path = tmp_path / "voice.sqlite3"
    store = SQLiteVoiceJournal(path)
    record = store.append(draft())
    assert store.health().state.value == "available"
    connection = sqlite3.connect(path)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute("UPDATE voice_records SET fact_type='changed'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute("DELETE FROM voice_records")
    connection.execute("DROP TRIGGER voice_records_no_update")
    connection.execute(
        "UPDATE voice_records SET payload=? WHERE record_id=?", ("{}", record.record_id)
    )
    connection.commit()
    connection.close()
    with pytest.raises(ValidationError, match="corrupt"):
        store.replay(record.stream_id)

    mismatch = tmp_path / "mismatch.sqlite3"
    mismatch_store = SQLiteVoiceJournal(mismatch)
    connection = sqlite3.connect(mismatch)
    connection.execute("DROP TRIGGER voice_migrations_no_update")
    connection.execute("UPDATE voice_migrations SET checksum='wrong'")
    connection.commit()
    connection.close()
    assert mismatch_store.health().state.value == "migration_mismatch"
    assert _MIGRATION_CHECKSUM


@pytest.mark.parametrize(
    "state",
    ["listening", "recording", "processing", "speaking", "cancelling"],
)
def test_real_runtime_restart_requires_reconciliation(runtime_factory, state: str) -> None:
    runtime, settings = runtime_factory()
    session = runtime.voice.create_session("artemis")
    runtime.voice._write_session(replace(session, status=state, revision=2))

    restarted = create_runtime(settings)
    recovered = restarted.voice.get_session(session.session_id)

    assert recovered.status == "reconciliation_required"
    assert recovered.previous_state == state
    assert recovered.metadata["external_state"] == "unknown"
    facts = restarted.voice.journal.replay(f"session:{session.session_id}").records
    assert facts[-1].fact_type == "session.reconciliation_required"
    assert all(item.payload.get("status") not in {"paused", "cancelled", "closed"} for item in facts)


def test_reconciliation_and_late_results_are_new_facts(runtime_factory) -> None:
    runtime, settings = runtime_factory()
    session = runtime.voice.create_session("artemis")
    recording = runtime.voice.start_recording(session_id=session.session_id)
    runtime.voice._write_session(
        replace(runtime.voice.get_session(session.session_id), status="processing")
    )
    restarted = create_runtime(settings)
    before = restarted.voice.journal.replay(f"recording:{recording.recording_id}").records
    provider_id = next(
        item.provider_id for item in restarted.voice.list_providers() if item.adapter_type == "stt"
    )
    restarted.voice.transcribe_recording(
        recording.recording_id, transcript="late", provider_id=provider_id
    )
    after = restarted.voice.journal.replay(f"recording:{recording.recording_id}").records
    assert len(after) == len(before) + 1
    assert before[0] == after[0]
    reconciled = restarted.voice.reconcile_session(
        session.session_id, target_state="idle", evidence={"pending_transcription": "observed"}
    )
    assert reconciled.status == "idle"
    assert restarted.voice.get_settings().store_raw_audio is False
