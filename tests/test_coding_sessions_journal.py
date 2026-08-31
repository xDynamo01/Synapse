from __future__ import annotations

from dataclasses import replace

from synapse.coding_sessions import (
    CodingSessionArtifactReference,
    CodingSessionCheckpointAssessment,
    CodingSessionCheckpointComponent,
    CodingSessionCheckpointDiagnosticCode,
    CodingSessionCheckpointDurabilityState,
    CodingSessionCheckpointIdentity,
    CodingSessionCheckpointManifest,
    CodingSessionCheckpointPolicy,
    CodingSessionCheckpointRequest,
    CodingSessionCorrelationReference,
    CodingSessionFingerprint,
    CodingSessionIdentity,
    CodingSessionJournalAppendRequest,
    CodingSessionJournalAssessment,
    CodingSessionJournalEntry,
    CodingSessionJournalEntryCategory,
    CodingSessionJournalStream,
    CodingSessionRuntimeConclusion,
)


def _session(key: str = "session:one") -> CodingSessionIdentity:
    return CodingSessionIdentity.from_stable_key(key)


def _entry(
    revision: int,
    *,
    parent: CodingSessionFingerprint | None = None,
    session: CodingSessionIdentity | None = None,
    category: CodingSessionJournalEntryCategory = CodingSessionJournalEntryCategory.LIFECYCLE,
    semantic_identity: str | None = None,
    occurrence: tuple[tuple[str, str], ...] = (),
    semantic_reference=None,
) -> CodingSessionJournalEntry:
    fingerprint = (
        semantic_reference.fingerprint
        if semantic_reference is not None and semantic_reference.fingerprint is not None
        else CodingSessionFingerprint.from_content((category, semantic_identity or revision))
    )
    return CodingSessionJournalEntry.create(
        session_identity=session or _session(),
        category=category,
        semantic_identity=semantic_identity or f"fact:{revision}",
        semantic_fingerprint=fingerprint,
        semantic_reference=semantic_reference,
        correlation=CodingSessionCorrelationReference("correlation:one"),
        causal_revision=revision,
        parent=parent,
        occurrence_metadata=occurrence,
    )


def _stream() -> CodingSessionJournalAssessment:
    first = _entry(1)
    second = _entry(2, parent=first.fingerprint)
    return CodingSessionJournalAssessment.assess_stream(_session(), (second, first))


def _checkpoint_request(
    journal: CodingSessionJournalAssessment,
    *,
    stale: frozenset[CodingSessionCheckpointComponent] = frozenset(),
    occurrence: tuple[tuple[str, str], ...] = (),
) -> CodingSessionCheckpointRequest:
    manifest = CodingSessionCheckpointManifest(
        session_identity=_session(),
        journal_fingerprint=journal.stream.fingerprint,
        through_revision=2,
        contract_fingerprint=CodingSessionFingerprint.from_content("contract"),
        lifecycle_fingerprint=CodingSessionFingerprint.from_content("lifecycle"),
    )
    return CodingSessionCheckpointRequest(
        checkpoint_identity=CodingSessionCheckpointIdentity.from_stable_key(
            "checkpoint:one"
        ),
        session_identity=_session(),
        manifest=manifest,
        required_from_revision=1,
        stale_components=stale,
        occurrence_metadata=occurrence,
    )


def _policy() -> CodingSessionCheckpointPolicy:
    return CodingSessionCheckpointPolicy(
        frozenset(
            {
                CodingSessionCheckpointComponent.CONTRACT,
                CodingSessionCheckpointComponent.LIFECYCLE,
            }
        )
    )


def _codes(
    assessment: CodingSessionJournalAssessment | CodingSessionCheckpointAssessment,
) -> set[CodingSessionCheckpointDiagnosticCode]:
    return {item.code for item in assessment.diagnostics}


def test_journal_records_fingerprints_without_executing_or_transferring_authority() -> None:
    artifact_fingerprint = CodingSessionFingerprint.from_content("external-artifact")
    artifact = CodingSessionArtifactReference.create(
        "external-authority", "v1", "artifact:one", artifact_fingerprint
    )
    entry = _entry(
        1,
        category=CodingSessionJournalEntryCategory.EXTERNAL_RECEIPT,
        semantic_reference=artifact,
    )
    assert entry.semantic_reference == artifact
    assert entry.semantic_fingerprint == artifact_fingerprint
    assert not hasattr(entry, "payload")
    assert not hasattr(entry, "execute")
    assert not hasattr(entry, "authority")


def test_append_is_explicit_and_append_only() -> None:
    initial = CodingSessionJournalStream(_session())
    first = _entry(1)
    assessment = CodingSessionJournalAssessment.assess_append(
        initial,
        CodingSessionJournalAppendRequest(_session(), first, 0, None),
    )
    assert assessment.accepted
    assert initial.entries == ()
    assert assessment.stream.entries == (first,)
    second = _entry(2, parent=first.fingerprint)
    appended = CodingSessionJournalAssessment.assess_append(
        assessment.stream,
        CodingSessionJournalAppendRequest(_session(), second, 1, first.fingerprint),
    )
    assert appended.accepted
    assert appended.stream.entries == (first, second)


def test_stream_detects_duplicate_revision_gap_parent_and_session_mismatch() -> None:
    first = _entry(1)
    duplicate = _entry(1, semantic_identity="fact:duplicate")
    duplicated = CodingSessionJournalAssessment.assess_stream(
        _session(), (first, duplicate)
    )
    gap_entry = _entry(
        3, parent=CodingSessionFingerprint.from_content("wrong-parent")
    )
    gap = CodingSessionJournalAssessment.assess_stream(_session(), (first, gap_entry))
    foreign = _entry(1, session=_session("session:other"))
    mismatch = CodingSessionJournalAssessment.assess_stream(_session(), (foreign,))
    assert CodingSessionCheckpointDiagnosticCode.DUPLICATE_CAUSAL_REVISION in _codes(
        duplicated
    )
    assert CodingSessionCheckpointDiagnosticCode.REVISION_GAP in _codes(gap)
    assert CodingSessionCheckpointDiagnosticCode.PARENT_MISMATCH in _codes(gap)
    assert CodingSessionCheckpointDiagnosticCode.SESSION_MISMATCH in _codes(mismatch)


def test_duplicate_semantic_entry_and_corruption_fail_closed() -> None:
    first = _entry(1, semantic_identity="same")
    second = _entry(2, parent=first.fingerprint, semantic_identity="same")
    duplicate = CodingSessionJournalAssessment.assess_stream(
        _session(), (first, second)
    )
    corrupted = replace(
        first,
        semantic_fingerprint=CodingSessionFingerprint.from_content("tampered"),
    )
    corruption = CodingSessionJournalAssessment.assess_stream(
        _session(), (corrupted,)
    )
    assert CodingSessionCheckpointDiagnosticCode.DUPLICATE_SEMANTIC_ENTRY in _codes(
        duplicate
    )
    assert (
        CodingSessionCheckpointDiagnosticCode.CORRUPTED_SEMANTIC_FINGERPRINT
        in _codes(corruption)
    )


def test_projection_requires_explicit_session_and_revision_interval() -> None:
    journal = _stream()
    projection = journal.stream.project_interval(
        session_identity=_session(), from_revision=1, through_revision=1
    )
    invalid_session = journal.stream.project_interval(
        session_identity=_session("session:other"),
        from_revision=1,
        through_revision=2,
    )
    assert len(projection.entries) == 1
    assert projection.entries[0].causal_metadata.revision.value == 1
    assert invalid_session.entries == ()
    assert not hasattr(journal.stream, "latest")
    assert not hasattr(journal.stream, "current")


def test_same_causal_journal_is_deterministic_but_changed_causality_changes_it() -> None:
    first = _entry(1, semantic_identity="first")
    second = _entry(2, parent=first.fingerprint, semantic_identity="second")
    left = CodingSessionJournalAssessment.assess_stream(_session(), (first, second))
    right = CodingSessionJournalAssessment.assess_stream(_session(), (second, first))
    alternate_first = _entry(1, semantic_identity="second")
    alternate_second = _entry(
        2, parent=alternate_first.fingerprint, semantic_identity="first"
    )
    changed = CodingSessionJournalAssessment.assess_stream(
        _session(), (alternate_first, alternate_second)
    )
    assert left.stream.fingerprint == right.stream.fingerprint
    assert left.stream.fingerprint != changed.stream.fingerprint


def test_checkpoint_durable_ready_is_not_persisted_resumable_or_completion() -> None:
    journal = _stream()
    assessment = CodingSessionCheckpointAssessment.assess(
        _checkpoint_request(journal), journal, _policy()
    )
    assert assessment.structurally_complete
    assert assessment.state is CodingSessionCheckpointDurabilityState.DURABLE_READY
    assert assessment.persisted is CodingSessionRuntimeConclusion.NOT_EVALUATED
    assert assessment.resumable is CodingSessionRuntimeConclusion.NOT_EVALUATED
    assert not hasattr(assessment, "session_completed")
    assert not hasattr(assessment, "lifecycle_transition")


def test_checkpoint_missing_stale_mismatched_or_lineage_incomplete_is_not_complete() -> None:
    journal = _stream()
    missing_manifest = replace(
        _checkpoint_request(journal).manifest,
        lifecycle_fingerprint=None,
    )
    requests = (
        replace(_checkpoint_request(journal), manifest=missing_manifest),
        _checkpoint_request(
            journal, stale=frozenset({CodingSessionCheckpointComponent.LIFECYCLE})
        ),
        replace(
            _checkpoint_request(journal),
            mismatched_components=frozenset(
                {CodingSessionCheckpointComponent.CONTRACT}
            ),
        ),
        replace(
            _checkpoint_request(journal),
            lineage_incomplete_components=frozenset(
                {CodingSessionCheckpointComponent.LIFECYCLE}
            ),
        ),
    )
    assessments = tuple(
        CodingSessionCheckpointAssessment.assess(request, journal, _policy())
        for request in requests
    )
    assert all(not item.structurally_complete for item in assessments)
    assert assessments[1].state is CodingSessionCheckpointDurabilityState.STALE
    assert assessments[3].state is CodingSessionCheckpointDurabilityState.LINEAGE_GAP


def test_checkpoint_requires_exact_journal_fingerprint_and_interval() -> None:
    journal = _stream()
    request = _checkpoint_request(journal)
    wrong = replace(
        request,
        manifest=replace(
            request.manifest,
            journal_fingerprint=CodingSessionFingerprint.from_content("wrong"),
            through_revision=3,
        ),
    )
    assessment = CodingSessionCheckpointAssessment.assess(wrong, journal, _policy())
    assert CodingSessionCheckpointDiagnosticCode.JOURNAL_FINGERPRINT_MISMATCH in _codes(
        assessment
    )
    assert CodingSessionCheckpointDiagnosticCode.INVALID_REVISION_INTERVAL in _codes(
        assessment
    )


def test_occurrence_metadata_changes_neither_entry_nor_checkpoint_semantics() -> None:
    first = _entry(1, occurrence=(("observed-at", "100"),))
    second = _entry(1, occurrence=(("observed-at", "200"),))
    assert first.entry_identity == second.entry_identity
    assert first.fingerprint == second.fingerprint

    journal = _stream()
    first_request = _checkpoint_request(
        journal, occurrence=(("observed-at", "100"),)
    )
    second_request = replace(
        first_request, occurrence_metadata=(("observed-at", "200"),)
    )
    first_checkpoint = CodingSessionCheckpointAssessment.assess(
        first_request, journal, _policy()
    ).fact
    second_checkpoint = CodingSessionCheckpointAssessment.assess(
        second_request, journal, _policy()
    ).fact
    assert first_request.fingerprint == second_request.fingerprint
    assert first_checkpoint.fingerprint == second_checkpoint.fingerprint
