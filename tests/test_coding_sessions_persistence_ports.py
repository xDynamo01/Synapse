from dataclasses import replace

from synapse.coding_sessions import (
    CODING_SESSION_RECORD_VERSION,
    CodingSessionCausalRangeReadRequest,
    CodingSessionCheckpointIdentity,
    CodingSessionCheckpointPersistenceEvidence,
    CodingSessionCheckpointPersistenceState,
    CodingSessionExactRecordReadRequest,
    CodingSessionExactRecordReadResult,
    CodingSessionFingerprint,
    CodingSessionIdentity,
    CodingSessionPersistenceFailureCode,
    CodingSessionPersistenceRecordIdentity,
    CodingSessionPersistenceStream,
    CodingSessionRecordAppendAssessment,
    CodingSessionRecordAppendRequest,
    CodingSessionRecordAppendStatus,
    CodingSessionRecordCompatibilityPolicy,
    CodingSessionRecordEnvelope,
    CodingSessionReplayRequest,
    CodingSessionReplayResult,
    CodingSessionRestartReplayInput,
    CodingSessionRetentionMetadata,
    CodingSessionStreamCompleteness,
    CodingSessionStreamCompletenessAssessment,
)


def _fingerprint(key: str) -> CodingSessionFingerprint:
    return CodingSessionFingerprint.from_content(key)


def _session() -> CodingSessionIdentity:
    return CodingSessionIdentity.from_stable_key("persistence-session")


def _record(
    revision: int,
    *,
    stream: CodingSessionPersistenceStream = CodingSessionPersistenceStream.LIFECYCLE_COORDINATION,
    category: str = "lifecycle-suspended",
    payload: str | None = None,
    parent: CodingSessionRecordEnvelope | None = None,
    identity_key: str | None = None,
    idempotency_key: str | None = None,
    occurrence: str = "100",
) -> CodingSessionRecordEnvelope:
    parent_fingerprint = parent.record_fingerprint if parent else None
    return CodingSessionRecordEnvelope(
        record_identity=CodingSessionPersistenceRecordIdentity.from_stable_key(
            identity_key or f"record-{stream.value}-{revision}"
        ),
        session_identity=_session(),
        stream=stream,
        category=category,
        semantic_artifact_identity=f"artifact-{stream.value}-{revision}",
        canonical_payload=payload or f"payload-{revision}",
        canonical_payload_fingerprint=_fingerprint(payload or f"payload-{revision}"),
        causal_revision=revision,
        parent_record_fingerprint=parent_fingerprint,
        lineage=((parent_fingerprint,) if parent_fingerprint else ()),
        idempotency_key=_fingerprint(idempotency_key or f"idempotency-{revision}"),
        occurrence_metadata=(("observed-at", occurrence),),
        retention_metadata=CodingSessionRetentionMetadata("retention-v1", "factual"),
    )


def _append(
    existing: tuple[CodingSessionRecordEnvelope, ...],
    record: CodingSessionRecordEnvelope,
) -> CodingSessionRecordAppendAssessment:
    parent = existing[-1].record_fingerprint if existing else None
    return CodingSessionRecordAppendAssessment.assess(
        existing,
        CodingSessionRecordAppendRequest(record, len(existing) + 1, parent),
    )


def test_append_is_immutable_and_append_only() -> None:
    first = _record(1)
    second = _record(2, parent=first)

    result = _append((first,), second)

    assert result.status is CodingSessionRecordAppendStatus.APPENDED
    assert result.records == (first, second)
    assert result.records[0].record_fingerprint == first.record_fingerprint


def test_same_idempotency_and_semantic_artifact_is_idempotent() -> None:
    first = _record(1, idempotency_key="same-key", occurrence="100")
    repeated = replace(first, occurrence_metadata=(("observed-at", "200"),))

    result = _append((first,), repeated)

    assert result.status is CodingSessionRecordAppendStatus.IDEMPOTENT
    assert result.records == (first,)
    assert result.record == first


def test_idempotency_collision_and_divergent_identity_fail_closed() -> None:
    first = _record(1, idempotency_key="same-key", identity_key="same-identity")
    divergent = _record(
        2,
        parent=first,
        payload="different",
        idempotency_key="same-key",
        identity_key="same-identity",
    )

    result = _append((first,), divergent)

    assert result.status is CodingSessionRecordAppendStatus.REJECTED
    assert {
        CodingSessionPersistenceFailureCode.DIVERGENT_DUPLICATE_IDENTITY,
        CodingSessionPersistenceFailureCode.IDEMPOTENCY_COLLISION,
    } <= {item.code for item in result.failures}
    assert result.records == (first,)


def test_revision_conflict_and_lineage_gap_are_not_repaired() -> None:
    first = _record(1)
    gap = _record(3)
    request = CodingSessionRecordAppendRequest(gap, 3, None)

    result = CodingSessionRecordAppendAssessment.assess((first,), request)

    assert result.status is CodingSessionRecordAppendStatus.REJECTED
    assert {
        CodingSessionPersistenceFailureCode.CAUSAL_REVISION_CONFLICT,
        CodingSessionPersistenceFailureCode.LINEAGE_GAP,
    } <= {item.code for item in result.failures}
    assert result.records == (first,)


def test_exact_read_requires_identity_and_fingerprint() -> None:
    record = _record(1)
    exact = CodingSessionExactRecordReadRequest(
        _session(),
        record.stream,
        record.record_identity,
        record.record_fingerprint,
    )
    wrong = replace(exact, expected_record_fingerprint=_fingerprint("wrong"))

    assert CodingSessionExactRecordReadResult.assess((record,), exact).record == record
    mismatch = CodingSessionExactRecordReadResult.assess((record,), wrong)
    assert mismatch.record is None
    assert mismatch.failures[0].code is CodingSessionPersistenceFailureCode.CORRUPTED_FINGERPRINT


def test_unknown_record_version_fails_explicitly() -> None:
    record = replace(_record(1), record_version="coding-session-record-v2")

    result = _append((), record)

    assert result.status is CodingSessionRecordAppendStatus.REJECTED
    assert result.failures[0].code is CodingSessionPersistenceFailureCode.UNSUPPORTED_RECORD_VERSION
    assert CODING_SESSION_RECORD_VERSION == "coding-session-record-v1"
    assert CodingSessionRecordCompatibilityPolicy().supports(CODING_SESSION_RECORD_VERSION)
    assert not CodingSessionRecordCompatibilityPolicy().supports("coding-session-record-v2")


def test_completeness_preserves_causal_gap() -> None:
    request = CodingSessionCausalRangeReadRequest(
        _session(), CodingSessionPersistenceStream.RECOVERY_OUTCOME, 1, 3
    )
    first = _record(1, stream=request.stream, category="recovery-reconciling")
    third = _record(3, stream=request.stream, category="recovery-manual-intervention")

    assessment = CodingSessionStreamCompletenessAssessment.assess(
        request, (first, third)
    )

    assert assessment.state is CodingSessionStreamCompleteness.INCOMPLETE
    assert assessment.missing_revisions == (2,)
    assert assessment.failures[0].code is CodingSessionPersistenceFailureCode.INCOMPLETE_REPLAY


def test_replay_preserves_intermediate_and_unknown_facts_without_inference() -> None:
    categories = (
        (CodingSessionPersistenceStream.LIFECYCLE_COORDINATION, "lifecycle-suspended"),
        (CodingSessionPersistenceStream.INTENTS_RECEIPTS, "intent-pending"),
        (CodingSessionPersistenceStream.INTENTS_RECEIPTS, "receipt-late"),
        (CodingSessionPersistenceStream.CONTROL_CANCELLATION, "cancellation-pending"),
        (CodingSessionPersistenceStream.RESTART_RECONCILIATION, "repository-unknown"),
        (CodingSessionPersistenceStream.RECOVERY_OUTCOME, "recovery-reconciling"),
        (CodingSessionPersistenceStream.RECOVERY_OUTCOME, "manual-intervention"),
    )
    built: list[CodingSessionRecordEnvelope] = []
    previous: dict[CodingSessionPersistenceStream, CodingSessionRecordEnvelope] = {}
    revisions: dict[CodingSessionPersistenceStream, int] = {}
    for index, (stream, category) in enumerate(categories):
        revision = revisions.get(stream, 0) + 1
        record = _record(
            revision,
            stream=stream,
            category=category,
            identity_key=f"record-{index}",
            parent=previous.get(stream),
        )
        built.append(record)
        previous[stream] = record
        revisions[stream] = revision
    records = tuple(built)
    streams = frozenset(stream for stream, _ in categories)
    ranges = tuple(
        CodingSessionCausalRangeReadRequest(_session(), stream, 1, revisions[stream])
        for stream in sorted(streams, key=lambda item: item.value)
    )
    replay = CodingSessionReplayResult.project(
        CodingSessionReplayRequest(_session(), ranges, streams), records
    )

    replayed_categories = {item.category for item in replay.records}
    assert {
        "lifecycle-suspended",
        "intent-pending",
        "receipt-late",
        "cancellation-pending",
        "repository-unknown",
        "recovery-reconciling",
        "manual-intervention",
    } <= replayed_categories
    assert "lifecycle-active" not in replayed_categories
    assert replay.completeness is CodingSessionStreamCompleteness.COMPLETE


def test_replay_gap_stays_incomplete_and_restart_requires_external_reconciliation() -> None:
    stream = CodingSessionPersistenceStream.RESTART_RECONCILIATION
    request = CodingSessionReplayRequest(
        _session(),
        (CodingSessionCausalRangeReadRequest(_session(), stream, 1, 2),),
        frozenset({stream}),
    )
    replay = CodingSessionReplayResult.project(
        request, (_record(1, stream=stream, category="worker-unknown"),)
    )
    restart = CodingSessionRestartReplayInput.from_replay(replay, None)

    assert replay.completeness is CodingSessionStreamCompleteness.INCOMPLETE
    assert restart.external_reconciliation_required
    assert restart.completeness is CodingSessionStreamCompleteness.INCOMPLETE


def test_checkpoint_persistence_is_distinct_from_structure_and_durable_ready() -> None:
    checkpoint = CodingSessionCheckpointIdentity.from_stable_key("checkpoint-one")
    not_persisted = CodingSessionCheckpointPersistenceEvidence(
        session_identity=_session(),
        checkpoint_identity=checkpoint,
        checkpoint_fingerprint=_fingerprint("checkpoint"),
        record_identity=None,
        record_fingerprint=None,
        structural_complete=True,
        durable_ready=True,
        persistence_state=CodingSessionCheckpointPersistenceState.NOT_PERSISTED,
    )
    persisted_incomplete = replace(
        not_persisted,
        record_identity=CodingSessionPersistenceRecordIdentity.from_stable_key(
            "checkpoint-record"
        ),
        record_fingerprint=_fingerprint("checkpoint-record"),
        structural_complete=False,
        persistence_state=CodingSessionCheckpointPersistenceState.PERSISTED,
    )

    assert not_persisted.durable_ready
    assert not_persisted.persistence_state is CodingSessionCheckpointPersistenceState.NOT_PERSISTED
    assert persisted_incomplete.persistence_state is CodingSessionCheckpointPersistenceState.PERSISTED
    assert not persisted_incomplete.structural_complete
