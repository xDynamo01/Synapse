"""Pure append-only journal and structural checkpoint semantics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .causal import CodingSessionCausalMetadata, CodingSessionCausalRevision, CodingSessionLineage
from .contracts import CodingSessionRuntimeConclusion
from .identities import (
    CodingSessionCheckpointIdentity,
    CodingSessionFactIdentity,
    CodingSessionFingerprint,
    CodingSessionIdentity,
)
from .intents import CodingSessionProducerReference
from .references import CodingSessionCorrelationReference

CODING_SESSION_JOURNAL_VERSION = "coding-session-journal-v1"
CODING_SESSION_CHECKPOINT_POLICY_VERSION = "coding-session-checkpoint-policy-v1"


class CodingSessionJournalEntryCategory(str, Enum):
    CONTRACT_BINDING = "contract-binding"
    LIFECYCLE = "lifecycle"
    LEASE_COORDINATION = "lease-coordination"
    INTENT = "intent"
    EXTERNAL_RECEIPT = "external-receipt"
    CHECKPOINT = "checkpoint"
    CANCELLATION = "cancellation"
    RECOVERY = "recovery"


class CodingSessionCheckpointDurabilityState(str, Enum):
    PENDING = "pending"
    DURABLE_READY = "durable-ready"
    INCOMPLETE = "incomplete"
    STALE = "stale"
    LINEAGE_GAP = "lineage-gap"


class CodingSessionCheckpointComponent(str, Enum):
    CONTRACT = "contract"
    LIFECYCLE = "lifecycle"
    OWNERSHIP = "ownership"
    INTENT_RECEIPT = "intent-receipt"
    REPOSITORY = "repository"
    WORKER_EXECUTION = "worker-execution"
    EVALUATION = "evaluation"
    ARTIFACT = "artifact"
    CANCELLATION_RECOVERY = "cancellation-recovery"


class CodingSessionCheckpointDiagnosticCode(str, Enum):
    DUPLICATE_CAUSAL_REVISION = "duplicate-causal-revision"
    REVISION_GAP = "revision-gap"
    LINEAGE_GAP = "lineage-gap"
    PARENT_MISMATCH = "parent-mismatch"
    SESSION_MISMATCH = "session-mismatch"
    DUPLICATE_SEMANTIC_ENTRY = "duplicate-semantic-entry"
    UNSUPPORTED_VERSION = "unsupported-version"
    CORRUPTED_SEMANTIC_FINGERPRINT = "corrupted-semantic-fingerprint"
    INVALID_REVISION_INTERVAL = "invalid-revision-interval"
    MISSING_REQUIRED_COMPONENT = "missing-required-component"
    STALE_COMPONENT = "stale-component"
    MISMATCHED_COMPONENT = "mismatched-component"
    LINEAGE_INCOMPLETE_COMPONENT = "lineage-incomplete-component"
    JOURNAL_FINGERPRINT_MISMATCH = "journal-fingerprint-mismatch"


@dataclass(frozen=True, slots=True, order=True)
class CodingSessionCheckpointDiagnostic:
    code: CodingSessionCheckpointDiagnosticCode
    subject: str = "journal-checkpoint"


@dataclass(frozen=True, slots=True)
class CodingSessionJournalEntry:
    entry_identity: CodingSessionFactIdentity
    session_identity: CodingSessionIdentity
    category: CodingSessionJournalEntryCategory
    semantic_identity: str
    semantic_fingerprint: CodingSessionFingerprint
    semantic_reference: CodingSessionProducerReference | None
    correlation: CodingSessionCorrelationReference | None
    journal_version: str
    causal_metadata: CodingSessionCausalMetadata
    integrity_fingerprint: CodingSessionFingerprint

    @classmethod
    def create(
        cls,
        *,
        session_identity: CodingSessionIdentity,
        category: CodingSessionJournalEntryCategory,
        semantic_identity: str,
        semantic_fingerprint: CodingSessionFingerprint,
        causal_revision: int,
        parent: CodingSessionFingerprint | None = None,
        semantic_reference: CodingSessionProducerReference | None = None,
        correlation: CodingSessionCorrelationReference | None = None,
        occurrence_metadata: tuple[tuple[str, str], ...] = (),
        journal_version: str = CODING_SESSION_JOURNAL_VERSION,
    ) -> CodingSessionJournalEntry:
        entry_key = CodingSessionFingerprint.from_content(
            (session_identity, category, semantic_identity, causal_revision)
        )
        entry_identity = CodingSessionFactIdentity.from_stable_key(entry_key.value)
        causal_metadata = CodingSessionCausalMetadata(
            semantic_identity=entry_identity,
            revision=CodingSessionCausalRevision(causal_revision),
            lineage=CodingSessionLineage(parents=((parent,) if parent else ())),
            occurrence_metadata=occurrence_metadata,
        )
        integrity = CodingSessionFingerprint.from_content(
            _entry_integrity_content(
                entry_identity,
                session_identity,
                category,
                semantic_identity,
                semantic_fingerprint,
                semantic_reference,
                correlation,
                journal_version,
                causal_metadata,
            )
        )
        return cls(
            entry_identity,
            session_identity,
            category,
            semantic_identity,
            semantic_fingerprint,
            semantic_reference,
            correlation,
            journal_version,
            causal_metadata,
            integrity,
        )

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return self.integrity_fingerprint

    @property
    def calculated_integrity_fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(
            _entry_integrity_content(
                self.entry_identity,
                self.session_identity,
                self.category,
                self.semantic_identity,
                self.semantic_fingerprint,
                self.semantic_reference,
                self.correlation,
                self.journal_version,
                self.causal_metadata,
            )
        )


@dataclass(frozen=True, slots=True)
class CodingSessionJournalAppendRequest:
    session_identity: CodingSessionIdentity
    entry: CodingSessionJournalEntry
    expected_previous_revision: int
    expected_parent: CodingSessionFingerprint | None


@dataclass(frozen=True, slots=True)
class CodingSessionJournalStream:
    session_identity: CodingSessionIdentity
    entries: tuple[CodingSessionJournalEntry, ...] = ()

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(
            (self.session_identity, self.entries)
        )

    def project_interval(
        self,
        *,
        session_identity: CodingSessionIdentity,
        from_revision: int,
        through_revision: int,
    ) -> CodingSessionJournalStream:
        if session_identity != self.session_identity or from_revision < 1 or through_revision < from_revision:
            return CodingSessionJournalStream(session_identity)
        return CodingSessionJournalStream(
            session_identity,
            tuple(
                entry
                for entry in self.entries
                if from_revision <= entry.causal_metadata.revision.value <= through_revision
            ),
        )


@dataclass(frozen=True, slots=True)
class CodingSessionJournalAssessment:
    accepted: bool
    stream: CodingSessionJournalStream
    diagnostics: tuple[CodingSessionCheckpointDiagnostic, ...]

    @classmethod
    def assess_stream(
        cls,
        session_identity: CodingSessionIdentity,
        entries: tuple[CodingSessionJournalEntry, ...],
    ) -> CodingSessionJournalAssessment:
        diagnostics = _stream_diagnostics(session_identity, entries)
        ordered = tuple(
            sorted(entries, key=lambda item: item.causal_metadata.revision.value)
        )
        return cls(not diagnostics, CodingSessionJournalStream(session_identity, ordered), diagnostics)

    @classmethod
    def assess_append(
        cls,
        stream: CodingSessionJournalStream,
        request: CodingSessionJournalAppendRequest,
    ) -> CodingSessionJournalAssessment:
        expected_revision = len(stream.entries)
        expected_parent = stream.entries[-1].fingerprint if stream.entries else None
        preliminary: set[CodingSessionCheckpointDiagnostic] = set()
        if request.session_identity != stream.session_identity:
            preliminary.add(_diagnostic(CodingSessionCheckpointDiagnosticCode.SESSION_MISMATCH))
        if request.expected_previous_revision != expected_revision:
            preliminary.add(_diagnostic(CodingSessionCheckpointDiagnosticCode.REVISION_GAP))
        if request.expected_parent != expected_parent:
            preliminary.add(_diagnostic(CodingSessionCheckpointDiagnosticCode.PARENT_MISMATCH))
        if preliminary:
            return cls(False, stream, tuple(sorted(preliminary)))
        return cls.assess_stream(
            stream.session_identity,
            (*stream.entries, request.entry),
        )


@dataclass(frozen=True, slots=True)
class CodingSessionCheckpointManifest:
    session_identity: CodingSessionIdentity
    journal_fingerprint: CodingSessionFingerprint
    through_revision: int
    contract_fingerprint: CodingSessionFingerprint | None = None
    lifecycle_fingerprint: CodingSessionFingerprint | None = None
    ownership_fingerprint: CodingSessionFingerprint | None = None
    intent_receipt_fingerprint: CodingSessionFingerprint | None = None
    repository_references: tuple[CodingSessionProducerReference, ...] = ()
    worker_execution_references: tuple[CodingSessionProducerReference, ...] = ()
    evaluation_references: tuple[CodingSessionProducerReference, ...] = ()
    artifact_references: tuple[CodingSessionProducerReference, ...] = ()
    cancellation_recovery_references: tuple[CodingSessionFingerprint, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "repository_references",
            "worker_execution_references",
            "evaluation_references",
            "artifact_references",
        ):
            values = getattr(self, name)
            object.__setattr__(
                self,
                name,
                tuple(
                    sorted(
                        set(values),
                        key=lambda item: (item.producer, item.artifact_type, item.identity),
                    )
                ),
            )
        object.__setattr__(
            self,
            "cancellation_recovery_references",
            tuple(
                sorted(
                    set(self.cancellation_recovery_references),
                    key=lambda item: item.value,
                )
            ),
        )

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class CodingSessionCheckpointPolicy:
    required_components: frozenset[CodingSessionCheckpointComponent]
    version: str = CODING_SESSION_CHECKPOINT_POLICY_VERSION


@dataclass(frozen=True, slots=True)
class CodingSessionCheckpointRequest:
    checkpoint_identity: CodingSessionCheckpointIdentity
    session_identity: CodingSessionIdentity
    manifest: CodingSessionCheckpointManifest
    required_from_revision: int
    stale_components: frozenset[CodingSessionCheckpointComponent] = frozenset()
    mismatched_components: frozenset[CodingSessionCheckpointComponent] = frozenset()
    lineage_incomplete_components: frozenset[CodingSessionCheckpointComponent] = frozenset()
    occurrence_metadata: tuple[tuple[str, str], ...] = ()
    policy_version: str = CODING_SESSION_CHECKPOINT_POLICY_VERSION

    def semantic_content(self) -> object:
        return (
            self.checkpoint_identity,
            self.session_identity,
            self.manifest,
            self.required_from_revision,
            self.stale_components,
            self.mismatched_components,
            self.lineage_incomplete_components,
            self.policy_version,
        )

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self.semantic_content())


@dataclass(frozen=True, slots=True)
class CodingSessionCheckpointFact:
    checkpoint_identity: CodingSessionCheckpointIdentity
    session_identity: CodingSessionIdentity
    state: CodingSessionCheckpointDurabilityState
    manifest: CodingSessionCheckpointManifest
    policy_version: str
    causal_metadata: CodingSessionCausalMetadata

    def semantic_content(self) -> object:
        return (
            self.checkpoint_identity,
            self.session_identity,
            self.state,
            self.manifest,
            self.policy_version,
            self.causal_metadata,
        )

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self.semantic_content())


@dataclass(frozen=True, slots=True)
class CodingSessionCheckpointAssessment:
    structurally_complete: bool
    persisted: CodingSessionRuntimeConclusion
    resumable: CodingSessionRuntimeConclusion
    state: CodingSessionCheckpointDurabilityState
    diagnostics: tuple[CodingSessionCheckpointDiagnostic, ...]
    fact: CodingSessionCheckpointFact

    @classmethod
    def assess(
        cls,
        request: CodingSessionCheckpointRequest,
        journal: CodingSessionJournalAssessment,
        policy: CodingSessionCheckpointPolicy,
    ) -> CodingSessionCheckpointAssessment:
        diagnostics: set[CodingSessionCheckpointDiagnostic] = set(journal.diagnostics)
        if (
            request.policy_version != policy.version
            or policy.version != CODING_SESSION_CHECKPOINT_POLICY_VERSION
        ):
            diagnostics.add(_diagnostic(CodingSessionCheckpointDiagnosticCode.UNSUPPORTED_VERSION))
        if (
            request.session_identity != request.manifest.session_identity
            or request.session_identity != journal.stream.session_identity
        ):
            diagnostics.add(_diagnostic(CodingSessionCheckpointDiagnosticCode.SESSION_MISMATCH))
        if request.manifest.journal_fingerprint != journal.stream.fingerprint:
            diagnostics.add(
                _diagnostic(CodingSessionCheckpointDiagnosticCode.JOURNAL_FINGERPRINT_MISMATCH)
            )
        if (
            request.required_from_revision < 1
            or request.manifest.through_revision < request.required_from_revision
            or request.manifest.through_revision != len(journal.stream.entries)
        ):
            diagnostics.add(
                _diagnostic(CodingSessionCheckpointDiagnosticCode.INVALID_REVISION_INTERVAL)
            )
        present = _present_components(request.manifest)
        if not policy.required_components <= present:
            diagnostics.add(
                _diagnostic(CodingSessionCheckpointDiagnosticCode.MISSING_REQUIRED_COMPONENT)
            )
        if request.stale_components:
            diagnostics.add(_diagnostic(CodingSessionCheckpointDiagnosticCode.STALE_COMPONENT))
        if request.mismatched_components:
            diagnostics.add(_diagnostic(CodingSessionCheckpointDiagnosticCode.MISMATCHED_COMPONENT))
        if request.lineage_incomplete_components:
            diagnostics.add(
                _diagnostic(
                    CodingSessionCheckpointDiagnosticCode.LINEAGE_INCOMPLETE_COMPONENT
                )
            )
        codes = {item.code for item in diagnostics}
        if codes & {
            CodingSessionCheckpointDiagnosticCode.LINEAGE_GAP,
            CodingSessionCheckpointDiagnosticCode.REVISION_GAP,
            CodingSessionCheckpointDiagnosticCode.PARENT_MISMATCH,
            CodingSessionCheckpointDiagnosticCode.LINEAGE_INCOMPLETE_COMPONENT,
        }:
            state = CodingSessionCheckpointDurabilityState.LINEAGE_GAP
        elif CodingSessionCheckpointDiagnosticCode.STALE_COMPONENT in codes:
            state = CodingSessionCheckpointDurabilityState.STALE
        elif diagnostics:
            state = CodingSessionCheckpointDurabilityState.INCOMPLETE
        else:
            state = CodingSessionCheckpointDurabilityState.DURABLE_READY
        fact = CodingSessionCheckpointFact(
            checkpoint_identity=request.checkpoint_identity,
            session_identity=request.session_identity,
            state=state,
            manifest=request.manifest,
            policy_version=request.policy_version,
            causal_metadata=CodingSessionCausalMetadata(
                semantic_identity=request.checkpoint_identity,
                revision=CodingSessionCausalRevision(
                    request.manifest.through_revision + 1
                ),
                lineage=CodingSessionLineage(
                    parents=((journal.stream.fingerprint,) if journal.stream.entries else ())
                ),
                occurrence_metadata=request.occurrence_metadata,
            ),
        )
        return cls(
            structurally_complete=not diagnostics,
            persisted=CodingSessionRuntimeConclusion.NOT_EVALUATED,
            resumable=CodingSessionRuntimeConclusion.NOT_EVALUATED,
            state=state,
            diagnostics=tuple(sorted(diagnostics)),
            fact=fact,
        )


def _stream_diagnostics(
    session_identity: CodingSessionIdentity,
    entries: tuple[CodingSessionJournalEntry, ...],
) -> tuple[CodingSessionCheckpointDiagnostic, ...]:
    findings: set[CodingSessionCheckpointDiagnostic] = set()
    revisions = [entry.causal_metadata.revision.value for entry in entries]
    if len(revisions) != len(set(revisions)):
        findings.add(_diagnostic(CodingSessionCheckpointDiagnosticCode.DUPLICATE_CAUSAL_REVISION))
    semantic_keys = [
        (entry.category, entry.semantic_identity, entry.semantic_fingerprint) for entry in entries
    ]
    if len(semantic_keys) != len(set(semantic_keys)):
        findings.add(_diagnostic(CodingSessionCheckpointDiagnosticCode.DUPLICATE_SEMANTIC_ENTRY))
    previous: CodingSessionJournalEntry | None = None
    for expected_revision, entry in enumerate(
        sorted(entries, key=lambda item: item.causal_metadata.revision.value), start=1
    ):
        if entry.session_identity != session_identity:
            findings.add(_diagnostic(CodingSessionCheckpointDiagnosticCode.SESSION_MISMATCH))
        if entry.journal_version != CODING_SESSION_JOURNAL_VERSION:
            findings.add(_diagnostic(CodingSessionCheckpointDiagnosticCode.UNSUPPORTED_VERSION))
        if entry.causal_metadata.revision.value != expected_revision:
            findings.add(_diagnostic(CodingSessionCheckpointDiagnosticCode.REVISION_GAP))
        expected_parent = () if previous is None else (previous.fingerprint,)
        if entry.causal_metadata.lineage.parents != expected_parent:
            findings.add(_diagnostic(CodingSessionCheckpointDiagnosticCode.PARENT_MISMATCH))
        if entry.causal_metadata.semantic_identity != entry.entry_identity:
            findings.add(_diagnostic(CodingSessionCheckpointDiagnosticCode.LINEAGE_GAP))
        if entry.integrity_fingerprint != entry.calculated_integrity_fingerprint or (
            entry.semantic_reference is not None
            and entry.semantic_reference.fingerprint is not None
            and entry.semantic_reference.fingerprint != entry.semantic_fingerprint
        ):
            findings.add(
                _diagnostic(CodingSessionCheckpointDiagnosticCode.CORRUPTED_SEMANTIC_FINGERPRINT)
            )
        previous = entry
    return tuple(sorted(findings))


def _present_components(
    manifest: CodingSessionCheckpointManifest,
) -> frozenset[CodingSessionCheckpointComponent]:
    components: set[CodingSessionCheckpointComponent] = set()
    for component, present in (
        (CodingSessionCheckpointComponent.CONTRACT, manifest.contract_fingerprint is not None),
        (CodingSessionCheckpointComponent.LIFECYCLE, manifest.lifecycle_fingerprint is not None),
        (CodingSessionCheckpointComponent.OWNERSHIP, manifest.ownership_fingerprint is not None),
        (
            CodingSessionCheckpointComponent.INTENT_RECEIPT,
            manifest.intent_receipt_fingerprint is not None,
        ),
        (CodingSessionCheckpointComponent.REPOSITORY, bool(manifest.repository_references)),
        (
            CodingSessionCheckpointComponent.WORKER_EXECUTION,
            bool(manifest.worker_execution_references),
        ),
        (CodingSessionCheckpointComponent.EVALUATION, bool(manifest.evaluation_references)),
        (CodingSessionCheckpointComponent.ARTIFACT, bool(manifest.artifact_references)),
        (
            CodingSessionCheckpointComponent.CANCELLATION_RECOVERY,
            bool(manifest.cancellation_recovery_references),
        ),
    ):
        if present:
            components.add(component)
    return frozenset(components)


def _entry_integrity_content(
    entry_identity: CodingSessionFactIdentity,
    session_identity: CodingSessionIdentity,
    category: CodingSessionJournalEntryCategory,
    semantic_identity: str,
    semantic_fingerprint: CodingSessionFingerprint,
    semantic_reference: CodingSessionProducerReference | None,
    correlation: CodingSessionCorrelationReference | None,
    journal_version: str,
    causal_metadata: CodingSessionCausalMetadata,
) -> object:
    return (
        entry_identity,
        session_identity,
        category,
        semantic_identity,
        semantic_fingerprint,
        semantic_reference,
        correlation,
        journal_version,
        causal_metadata,
    )


def _diagnostic(
    code: CodingSessionCheckpointDiagnosticCode,
) -> CodingSessionCheckpointDiagnostic:
    return CodingSessionCheckpointDiagnostic(code=code)
