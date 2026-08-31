"""Pure lease authority, conflict assessment, and ownership projection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .causal import CodingSessionCausalMetadata, CodingSessionCausalRevision, CodingSessionLineage
from .contracts import (
    CodingSessionBinding,
    CodingSessionBindingScope,
    CodingSessionContract,
    CodingSessionContractAssessment,
    CodingSessionPurpose,
    CodingSessionRequestedCapability,
)
from .identities import (
    CodingSessionFingerprint,
    CodingSessionIdentity,
    CodingSessionLeaseFactIdentity,
)
from .lifecycle import CodingSessionCoordinationState
from .references import CodingSessionActorReference

CODING_SESSION_LEASE_POLICY_VERSION = "coding-session-lease-policy-v1"


class CodingSessionLeaseCapability(str, Enum):
    READ = "read"
    WRITE = "write"


class CodingSessionLeaseMode(str, Enum):
    SHARED = "shared"
    EXCLUSIVE = "exclusive"


class CodingSessionLeaseAction(str, Enum):
    ISSUE = "issue"
    RENEW = "renew"
    REVOKE = "revoke"
    MARK_STALE = "mark-stale"


class CodingSessionLeaseValidity(str, Enum):
    ACTIVE = "active"
    NOT_YET_VALID = "not-yet-valid"
    EXPIRED = "expired"
    REVOKED = "revoked"
    STALE = "stale"
    INVALID = "invalid"
    UNKNOWN = "unknown"


class CodingSessionLeaseDiagnosticCode(str, Enum):
    CONTRACT_INVALID = "contract-invalid"
    CONTRACT_CAPABILITY_MISSING = "contract-capability-missing"
    SESSION_MISMATCH = "session-mismatch"
    ACTOR_MISMATCH = "actor-mismatch"
    PURPOSE_MISMATCH = "purpose-mismatch"
    BINDING_MISMATCH = "binding-mismatch"
    SCOPE_ESCALATION = "scope-escalation"
    INVALID_SCOPE = "invalid-scope"
    SHARED_WRITE_NOT_ALLOWED = "shared-write-not-allowed"
    INVALID_INTERVAL = "invalid-interval"
    INVALID_RENEWAL = "invalid-renewal"
    UNKNOWN_REVOCATION = "unknown-revocation"
    DUPLICATE_CAUSAL_REVISION = "duplicate-causal-revision"
    LINEAGE_GAP = "lineage-gap"
    CONFLICTING_WRITE_LEASE = "conflicting-write-lease"
    LEASE_EXPIRED = "lease-expired"
    LEASE_STALE = "lease-stale"
    UNSUPPORTED_POLICY_VERSION = "unsupported-policy-version"


@dataclass(frozen=True, slots=True, order=True)
class CodingSessionLeaseDiagnostic:
    code: CodingSessionLeaseDiagnosticCode
    subject: str = "lease"


@dataclass(frozen=True, slots=True)
class CodingSessionLeasePolicy:
    allow_shared_write: bool = False
    version: str = CODING_SESSION_LEASE_POLICY_VERSION


@dataclass(frozen=True, slots=True)
class CodingSessionLeaseScope:
    level: CodingSessionBindingScope


@dataclass(frozen=True, slots=True)
class CodingSessionLeaseInterval:
    issued_at: int
    valid_from: int
    expires_at: int

    @property
    def valid(self) -> bool:
        return (
            not isinstance(self.issued_at, bool)
            and not isinstance(self.valid_from, bool)
            and not isinstance(self.expires_at, bool)
            and self.issued_at >= 0
            and self.issued_at <= self.valid_from < self.expires_at
        )


@dataclass(frozen=True, slots=True)
class CodingSessionLeaseRequest:
    action: CodingSessionLeaseAction
    session_identity: CodingSessionIdentity
    actor: CodingSessionActorReference
    purpose: CodingSessionPurpose
    binding: CodingSessionBinding
    scope: CodingSessionLeaseScope
    capability: CodingSessionLeaseCapability
    mode: CodingSessionLeaseMode
    interval: CodingSessionLeaseInterval
    expected_causal_revision: int
    previous_fact_identity: CodingSessionLeaseFactIdentity | None = None
    evidence: tuple[CodingSessionFingerprint, ...] = ()
    occurrence_metadata: tuple[tuple[str, str], ...] = ()
    policy_version: str = CODING_SESSION_LEASE_POLICY_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evidence",
            tuple(sorted(set(self.evidence), key=lambda item: item.value)),
        )
        object.__setattr__(
            self, "occurrence_metadata", tuple(sorted(set(self.occurrence_metadata)))
        )

    def semantic_content(self) -> object:
        return (
            self.action,
            self.session_identity,
            self.actor,
            self.purpose,
            self.binding,
            self.scope,
            self.capability,
            self.mode,
            self.interval,
            self.expected_causal_revision,
            self.previous_fact_identity,
            self.evidence,
            self.policy_version,
        )

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self.semantic_content())


@dataclass(frozen=True, slots=True)
class CodingSessionLeaseFact:
    fact_identity: CodingSessionLeaseFactIdentity
    lease_identity: CodingSessionLeaseFactIdentity
    action: CodingSessionLeaseAction
    session_identity: CodingSessionIdentity
    actor: CodingSessionActorReference
    purpose: CodingSessionPurpose
    binding: CodingSessionBinding
    scope: CodingSessionLeaseScope
    capability: CodingSessionLeaseCapability
    mode: CodingSessionLeaseMode
    interval: CodingSessionLeaseInterval
    policy_version: str
    causal_metadata: CodingSessionCausalMetadata

    def semantic_content(self) -> object:
        return (
            self.fact_identity,
            self.lease_identity,
            self.action,
            self.session_identity,
            self.actor,
            self.purpose,
            self.binding,
            self.scope,
            self.capability,
            self.mode,
            self.interval,
            self.policy_version,
            self.causal_metadata,
        )

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self.semantic_content())


@dataclass(frozen=True, slots=True)
class CodingSessionLeaseAssessment:
    accepted: bool
    request_fingerprint: CodingSessionFingerprint
    diagnostics: tuple[CodingSessionLeaseDiagnostic, ...]
    fact: CodingSessionLeaseFact | None = None

    @classmethod
    def assess(
        cls,
        request: CodingSessionLeaseRequest,
        contract: CodingSessionContract,
        history: tuple[CodingSessionLeaseFact, ...],
        policy: CodingSessionLeasePolicy,
    ) -> CodingSessionLeaseAssessment:
        prior = next(
            (
                fact
                for fact in history
                if fact.fact_identity == request.previous_fact_identity
            ),
            None,
        )
        diagnostics = _request_diagnostics(request, contract, history, prior, policy)
        if diagnostics:
            return cls(False, request.fingerprint, diagnostics)
        fact_identity = CodingSessionLeaseFactIdentity.from_stable_key(
            request.fingerprint.value
        )
        lease_identity = fact_identity if prior is None else prior.lease_identity
        parents = () if prior is None else (prior.fingerprint,)
        fact = CodingSessionLeaseFact(
            fact_identity=fact_identity,
            lease_identity=lease_identity,
            action=request.action,
            session_identity=request.session_identity,
            actor=request.actor,
            purpose=request.purpose,
            binding=request.binding,
            scope=request.scope,
            capability=request.capability,
            mode=request.mode,
            interval=request.interval,
            policy_version=request.policy_version,
            causal_metadata=CodingSessionCausalMetadata(
                semantic_identity=fact_identity,
                revision=CodingSessionCausalRevision(
                    request.expected_causal_revision + 1
                ),
                lineage=CodingSessionLineage(
                    parents=parents,
                    references=request.evidence,
                ),
                occurrence_metadata=request.occurrence_metadata,
            ),
        )
        return cls(True, request.fingerprint, (), fact)


@dataclass(frozen=True, slots=True, order=True)
class CodingSessionLeaseConflict:
    first_lease: CodingSessionLeaseFactIdentity
    second_lease: CodingSessionLeaseFactIdentity
    diagnostic: CodingSessionLeaseDiagnosticCode = (
        CodingSessionLeaseDiagnosticCode.CONFLICTING_WRITE_LEASE
    )

    def __post_init__(self) -> None:
        if self.second_lease.value < self.first_lease.value:
            first = self.first_lease
            object.__setattr__(self, "first_lease", self.second_lease)
            object.__setattr__(self, "second_lease", first)


@dataclass(frozen=True, slots=True)
class CodingSessionOwnershipProjection:
    observation_time: int
    state: CodingSessionCoordinationState
    validities: tuple[tuple[CodingSessionLeaseFactIdentity, CodingSessionLeaseValidity], ...]
    active_leases: tuple[CodingSessionLeaseFactIdentity, ...]
    conflicts: tuple[CodingSessionLeaseConflict, ...]
    diagnostics: tuple[CodingSessionLeaseDiagnostic, ...]
    valid: bool

    @classmethod
    def project(
        cls,
        facts: tuple[CodingSessionLeaseFact, ...],
        *,
        observation_time: int,
        policy: CodingSessionLeasePolicy,
    ) -> CodingSessionOwnershipProjection:
        diagnostics: set[CodingSessionLeaseDiagnostic] = set()
        terminal: list[CodingSessionLeaseFact] = []
        for lease_identity in sorted(
            {fact.lease_identity for fact in facts}, key=lambda item: item.value
        ):
            chain = sorted(
                (fact for fact in facts if fact.lease_identity == lease_identity),
                key=lambda item: item.causal_metadata.revision.value,
            )
            chain_diagnostics = _chain_diagnostics(chain)
            diagnostics.update(chain_diagnostics)
            if not chain_diagnostics:
                terminal.append(chain[-1])
        validities = tuple(
            sorted(
                (
                    (fact.lease_identity, _validity_at(fact, observation_time))
                    for fact in terminal
                ),
                key=lambda item: item[0].value,
            )
        )
        for _, validity in validities:
            if validity is CodingSessionLeaseValidity.EXPIRED:
                diagnostics.add(
                    CodingSessionLeaseDiagnostic(CodingSessionLeaseDiagnosticCode.LEASE_EXPIRED)
                )
            elif validity is CodingSessionLeaseValidity.STALE:
                diagnostics.add(
                    CodingSessionLeaseDiagnostic(CodingSessionLeaseDiagnosticCode.LEASE_STALE)
                )
        active = tuple(
            fact
            for fact in terminal
            if _validity_at(fact, observation_time) is CodingSessionLeaseValidity.ACTIVE
        )
        conflicts = _conflicts(active, policy)
        if conflicts:
            diagnostics.add(
                CodingSessionLeaseDiagnostic(
                    CodingSessionLeaseDiagnosticCode.CONFLICTING_WRITE_LEASE
                )
            )
        state = _ownership_state(active, conflicts, validities)
        return cls(
            observation_time=observation_time,
            state=state,
            validities=validities,
            active_leases=tuple(sorted((fact.lease_identity for fact in active), key=lambda x: x.value)),
            conflicts=conflicts,
            diagnostics=tuple(sorted(diagnostics)),
            valid=not any(
                item.code
                in {
                    CodingSessionLeaseDiagnosticCode.DUPLICATE_CAUSAL_REVISION,
                    CodingSessionLeaseDiagnosticCode.LINEAGE_GAP,
                }
                for item in diagnostics
            ),
        )

    @property
    def evidence_fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(
            (
                self.observation_time,
                self.state,
                self.validities,
                self.active_leases,
                self.conflicts,
                self.diagnostics,
                self.valid,
            )
        )


def _request_diagnostics(
    request: CodingSessionLeaseRequest,
    contract: CodingSessionContract,
    history: tuple[CodingSessionLeaseFact, ...],
    prior: CodingSessionLeaseFact | None,
    policy: CodingSessionLeasePolicy,
) -> tuple[CodingSessionLeaseDiagnostic, ...]:
    findings: set[CodingSessionLeaseDiagnostic] = set()
    add = findings.add
    contract_assessment = CodingSessionContractAssessment.assess(contract)
    if not contract_assessment.complete or not contract_assessment.valid:
        add(CodingSessionLeaseDiagnostic(CodingSessionLeaseDiagnosticCode.CONTRACT_INVALID))
    if request.policy_version != policy.version or policy.version != CODING_SESSION_LEASE_POLICY_VERSION:
        add(CodingSessionLeaseDiagnostic(CodingSessionLeaseDiagnosticCode.UNSUPPORTED_POLICY_VERSION))
    if request.session_identity != contract.session_identity or request.binding.session_identity != request.session_identity:
        add(CodingSessionLeaseDiagnostic(CodingSessionLeaseDiagnosticCode.SESSION_MISMATCH))
    if request.actor != contract.actor:
        add(CodingSessionLeaseDiagnostic(CodingSessionLeaseDiagnosticCode.ACTOR_MISMATCH))
    if request.purpose != contract.purpose:
        add(CodingSessionLeaseDiagnostic(CodingSessionLeaseDiagnosticCode.PURPOSE_MISMATCH))
    if request.binding != contract.binding:
        add(CodingSessionLeaseDiagnostic(CodingSessionLeaseDiagnosticCode.BINDING_MISMATCH))
    if _scope_rank(request.scope.level) > _scope_rank(contract.binding.scope):
        add(CodingSessionLeaseDiagnostic(CodingSessionLeaseDiagnosticCode.SCOPE_ESCALATION))
    if request.scope.level is CodingSessionBindingScope.NONE:
        add(CodingSessionLeaseDiagnostic(CodingSessionLeaseDiagnosticCode.INVALID_SCOPE))
    required_capability = (
        CodingSessionRequestedCapability.REPOSITORY_MUTATION
        if request.capability is CodingSessionLeaseCapability.WRITE
        else CodingSessionRequestedCapability.REPOSITORY_ACCESS
    )
    declared = {item.code for item in contract.requested_capabilities}
    if required_capability not in declared:
        add(CodingSessionLeaseDiagnostic(CodingSessionLeaseDiagnosticCode.CONTRACT_CAPABILITY_MISSING))
    if request.capability is CodingSessionLeaseCapability.WRITE and request.mode is CodingSessionLeaseMode.SHARED and not policy.allow_shared_write:
        add(CodingSessionLeaseDiagnostic(CodingSessionLeaseDiagnosticCode.SHARED_WRITE_NOT_ALLOWED))
    if not request.interval.valid:
        add(CodingSessionLeaseDiagnostic(CodingSessionLeaseDiagnosticCode.INVALID_INTERVAL))
    if request.action is CodingSessionLeaseAction.ISSUE:
        if request.previous_fact_identity is not None or request.expected_causal_revision != 0:
            add(CodingSessionLeaseDiagnostic(CodingSessionLeaseDiagnosticCode.INVALID_RENEWAL))
    elif prior is None:
        code = (
            CodingSessionLeaseDiagnosticCode.UNKNOWN_REVOCATION
            if request.action is CodingSessionLeaseAction.REVOKE
            else CodingSessionLeaseDiagnosticCode.INVALID_RENEWAL
        )
        add(CodingSessionLeaseDiagnostic(code))
    elif any(
        fact.lease_identity == prior.lease_identity
        and fact.causal_metadata.revision.value > prior.causal_metadata.revision.value
        for fact in history
    ):
        add(CodingSessionLeaseDiagnostic(CodingSessionLeaseDiagnosticCode.INVALID_RENEWAL))
    elif (
        request.expected_causal_revision != prior.causal_metadata.revision.value
        or request.session_identity != prior.session_identity
        or request.actor != prior.actor
        or request.purpose != prior.purpose
        or request.binding != prior.binding
        or request.scope != prior.scope
        or request.capability != prior.capability
        or request.mode != prior.mode
    ):
        add(CodingSessionLeaseDiagnostic(CodingSessionLeaseDiagnosticCode.INVALID_RENEWAL))
    elif request.action is CodingSessionLeaseAction.RENEW and (
        request.interval.issued_at != prior.interval.issued_at
        or request.interval.valid_from < prior.interval.valid_from
        or request.interval.expires_at <= prior.interval.expires_at
    ):
        add(CodingSessionLeaseDiagnostic(CodingSessionLeaseDiagnosticCode.INVALID_RENEWAL))
    elif request.action in {CodingSessionLeaseAction.REVOKE, CodingSessionLeaseAction.MARK_STALE} and request.interval != prior.interval:
        add(CodingSessionLeaseDiagnostic(CodingSessionLeaseDiagnosticCode.INVALID_RENEWAL))
    return tuple(sorted(findings))


def _chain_diagnostics(
    chain: list[CodingSessionLeaseFact],
) -> tuple[CodingSessionLeaseDiagnostic, ...]:
    findings: set[CodingSessionLeaseDiagnostic] = set()
    revisions = [fact.causal_metadata.revision.value for fact in chain]
    if len(revisions) != len(set(revisions)):
        findings.add(
            CodingSessionLeaseDiagnostic(
                CodingSessionLeaseDiagnosticCode.DUPLICATE_CAUSAL_REVISION
            )
        )
    previous: CodingSessionLeaseFact | None = None
    for expected_revision, fact in enumerate(chain, start=1):
        expected_parents = () if previous is None else (previous.fingerprint,)
        if (
            fact.causal_metadata.revision.value != expected_revision
            or fact.causal_metadata.semantic_identity != fact.fact_identity
            or fact.causal_metadata.lineage.parents != expected_parents
            or (previous is None and fact.action is not CodingSessionLeaseAction.ISSUE)
            or (previous is not None and fact.action is CodingSessionLeaseAction.ISSUE)
        ):
            findings.add(
                CodingSessionLeaseDiagnostic(CodingSessionLeaseDiagnosticCode.LINEAGE_GAP)
            )
        if previous is not None and (
            fact.session_identity != previous.session_identity
            or fact.actor != previous.actor
            or fact.purpose != previous.purpose
            or fact.binding != previous.binding
            or fact.scope != previous.scope
            or fact.capability != previous.capability
            or fact.mode != previous.mode
        ):
            findings.add(
                CodingSessionLeaseDiagnostic(CodingSessionLeaseDiagnosticCode.INVALID_RENEWAL)
            )
        previous = fact
    return tuple(sorted(findings))


def _validity_at(
    fact: CodingSessionLeaseFact, observation_time: int
) -> CodingSessionLeaseValidity:
    if fact.action is CodingSessionLeaseAction.REVOKE:
        return CodingSessionLeaseValidity.REVOKED
    if fact.action is CodingSessionLeaseAction.MARK_STALE:
        return CodingSessionLeaseValidity.STALE
    if not fact.interval.valid or observation_time < 0:
        return CodingSessionLeaseValidity.INVALID
    if observation_time < fact.interval.valid_from:
        return CodingSessionLeaseValidity.NOT_YET_VALID
    if observation_time >= fact.interval.expires_at:
        return CodingSessionLeaseValidity.EXPIRED
    return CodingSessionLeaseValidity.ACTIVE


def _conflicts(
    active: tuple[CodingSessionLeaseFact, ...], policy: CodingSessionLeasePolicy
) -> tuple[CodingSessionLeaseConflict, ...]:
    conflicts: set[CodingSessionLeaseConflict] = set()
    for index, first in enumerate(active):
        for second in active[index + 1 :]:
            if not _scopes_overlap(first, second):
                continue
            has_write = CodingSessionLeaseCapability.WRITE in {
                first.capability,
                second.capability,
            }
            exclusive = CodingSessionLeaseMode.EXCLUSIVE in {first.mode, second.mode}
            shared_write_denied = (
                has_write
                and not policy.allow_shared_write
                and CodingSessionLeaseMode.SHARED in {first.mode, second.mode}
            )
            if has_write and (exclusive or shared_write_denied):
                conflicts.add(
                    CodingSessionLeaseConflict(first.lease_identity, second.lease_identity)
                )
    return tuple(sorted(conflicts))


def _scopes_overlap(first: CodingSessionLeaseFact, second: CodingSessionLeaseFact) -> bool:
    first_binding = first.binding
    second_binding = second.binding
    if first_binding.repository != second_binding.repository:
        return False
    lower = min(_scope_rank(first.scope.level), _scope_rank(second.scope.level))
    if lower == _scope_rank(CodingSessionBindingScope.REPOSITORY):
        return True
    if first_binding.checkout != second_binding.checkout:
        return False
    if lower == _scope_rank(CodingSessionBindingScope.CHECKOUT):
        return True
    return first_binding.worktree == second_binding.worktree


def _ownership_state(
    active: tuple[CodingSessionLeaseFact, ...],
    conflicts: tuple[CodingSessionLeaseConflict, ...],
    validities: tuple[tuple[CodingSessionLeaseFactIdentity, CodingSessionLeaseValidity], ...],
) -> CodingSessionCoordinationState:
    if conflicts:
        return CodingSessionCoordinationState.CONFLICTED
    if active:
        if any(fact.capability is CodingSessionLeaseCapability.WRITE for fact in active):
            return CodingSessionCoordinationState.WRITE_OWNED
        return CodingSessionCoordinationState.READ_OWNED
    statuses = {validity for _, validity in validities}
    if CodingSessionLeaseValidity.STALE in statuses:
        return CodingSessionCoordinationState.STALE
    if CodingSessionLeaseValidity.REVOKED in statuses:
        return CodingSessionCoordinationState.REVOKED
    if statuses <= {
        CodingSessionLeaseValidity.EXPIRED,
        CodingSessionLeaseValidity.NOT_YET_VALID,
    }:
        return CodingSessionCoordinationState.UNOWNED
    return CodingSessionCoordinationState.UNKNOWN


def _scope_rank(scope: CodingSessionBindingScope) -> int:
    return {
        CodingSessionBindingScope.NONE: 0,
        CodingSessionBindingScope.REPOSITORY: 1,
        CodingSessionBindingScope.CHECKOUT: 2,
        CodingSessionBindingScope.WORKTREE: 3,
    }[scope]
