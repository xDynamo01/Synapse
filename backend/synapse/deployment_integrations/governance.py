"""Safe translation between Deployment and the existing Decisions/Approvals authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, TypeAlias

from synapse.approvals import ApprovalRequest
from synapse.decisions.models import DecisionRequest, DecisionResult
from synapse.deployment import (
    ArtifactReference,
    AuthorizationReference,
    CausationReference,
    CorrelationReference,
    DeploymentArtifactRefV1,
    DeploymentAttemptId,
    DeploymentAuthorizationOutcome,
    DeploymentEventId,
    DeploymentFingerprint,
    DeploymentLifecycleState,
    DeploymentOperation,
    DeploymentReleaseV1,
    DeploymentTargetId,
    DeploymentTransitionEventV1,
    EnvironmentId,
    EvidenceReference,
    OccurrenceReference,
    PolicyReference,
    PromotionId,
    PromotionLifecycleState,
    PromotionTransitionEventV1,
    ReleaseId,
    RequesterReference,
    RevisionId,
    RollbackAttemptId,
    RollbackLifecycleState,
    RollbackTransitionEventV1,
    RolloutId,
    RolloutLifecycleState,
    RolloutTransitionEventV1,
    TransitionFailureClass,
    canonical_json,
)

AUTHORITY_VERSION = "synapse-governance-approvals-v1"


class AuthorizationBindingError(ValueError):
    """Authorization evidence does not correspond to its intent."""


class AuthorizationContradiction(AuthorizationBindingError):
    """One authority identity was rebound to different factual content."""


@dataclass(frozen=True, slots=True)
class _Scope:
    requester: RequesterReference
    release_id: ReleaseId
    attempt_reference: str
    environment_id: EnvironmentId
    target_id: DeploymentTargetId
    artifact: DeploymentArtifactRefV1
    desired_revision: RevisionId
    operation: str
    policy_reference: PolicyReference
    correlation: CorrelationReference
    causation: CausationReference | None
    semantic_fingerprint: DeploymentFingerprint

    def payload(self) -> dict[str, str | None]:
        return {
            "requester": self.requester.value,
            "release_id": self.release_id.value,
            "attempt_reference": self.attempt_reference,
            "environment_id": self.environment_id.value,
            "target_id": self.target_id.value,
            "artifact_reference": self.artifact.artifact.value,
            "artifact_fingerprint": self.artifact.fingerprint.value,
            "revision_id": self.desired_revision.value,
            "operation": self.operation,
            "policy_reference": self.policy_reference.value,
            "correlation": self.correlation.value,
            "causation": self.causation.value if self.causation else None,
            "semantic_fingerprint": self.semantic_fingerprint.value,
        }


@dataclass(frozen=True, slots=True)
class DeploymentOperationIntentV1:
    requester: RequesterReference
    release: DeploymentReleaseV1
    attempt_id: DeploymentAttemptId
    environment_id: EnvironmentId
    target_id: DeploymentTargetId
    artifact: DeploymentArtifactRefV1
    desired_revision: RevisionId
    operation: DeploymentOperation
    policy_reference: PolicyReference
    correlation: CorrelationReference
    causation: CausationReference | None
    semantic_fingerprint: DeploymentFingerprint

    def __post_init__(self) -> None:
        if self.operation not in {DeploymentOperation.PREPARE, DeploymentOperation.APPLY}:
            raise AuthorizationBindingError("deployment intent operation is not mutable")
        _validate_release(self.release, self.target_id, self.artifact, self.desired_revision)


@dataclass(frozen=True, slots=True)
class RolloutAuthorizationIntentV1:
    requester: RequesterReference
    release: DeploymentReleaseV1
    rollout_id: RolloutId
    environment_id: EnvironmentId
    target_id: DeploymentTargetId
    artifact: DeploymentArtifactRefV1
    desired_revision: RevisionId
    policy_reference: PolicyReference
    correlation: CorrelationReference
    causation: CausationReference | None
    semantic_fingerprint: DeploymentFingerprint
    operation: str = "rollout-advance"

    def __post_init__(self) -> None:
        _validate_release(self.release, self.target_id, self.artifact, self.desired_revision)


@dataclass(frozen=True, slots=True)
class PromotionAuthorizationIntentV1:
    requester: RequesterReference
    release: DeploymentReleaseV1
    promotion_id: PromotionId
    rollout_id: RolloutId
    environment_id: EnvironmentId
    target_id: DeploymentTargetId
    artifact: DeploymentArtifactRefV1
    desired_revision: RevisionId
    policy_reference: PolicyReference
    correlation: CorrelationReference
    causation: CausationReference | None
    semantic_fingerprint: DeploymentFingerprint
    operation: str = "promotion"

    def __post_init__(self) -> None:
        _validate_release(self.release, self.target_id, self.artifact, self.desired_revision)


@dataclass(frozen=True, slots=True)
class RollbackAuthorizationIntentV1:
    requester: RequesterReference
    release: DeploymentReleaseV1
    rollback_attempt_id: RollbackAttemptId
    environment_id: EnvironmentId
    target_id: DeploymentTargetId
    artifact: DeploymentArtifactRefV1
    current_revision: RevisionId
    desired_revision: RevisionId
    operation: DeploymentOperation
    policy_reference: PolicyReference
    correlation: CorrelationReference
    causation: CausationReference | None
    semantic_fingerprint: DeploymentFingerprint

    def __post_init__(self) -> None:
        if (
            self.operation
            not in {
                DeploymentOperation.ROLLBACK_PREPARE,
                DeploymentOperation.ROLLBACK_APPLY,
            }
            or self.current_revision == self.desired_revision
        ):
            raise AuthorizationBindingError("rollback operation or revision binding is invalid")
        if self.release.target_id != self.target_id or self.release.artifact != self.artifact:
            raise AuthorizationBindingError("rollback release binding mismatch")


AuthorizationIntent: TypeAlias = (
    DeploymentOperationIntentV1
    | RolloutAuthorizationIntentV1
    | PromotionAuthorizationIntentV1
    | RollbackAuthorizationIntentV1
)


@dataclass(frozen=True, slots=True)
class AuthorizationEvidenceV1:
    decision_identity: str
    authorization_reference: AuthorizationReference | None
    evidence_reference: EvidenceReference
    operation: str
    requester: RequesterReference
    release_id: ReleaseId
    attempt_reference: str
    environment_id: EnvironmentId
    target_id: DeploymentTargetId
    artifact_reference: ArtifactReference
    artifact_fingerprint: str
    revision_id: RevisionId
    policy_reference: PolicyReference
    decision: DeploymentAuthorizationOutcome
    valid_until: str | None
    authority: str
    authority_revision: str
    semantic_fingerprint: DeploymentFingerprint
    decision_fingerprint: DeploymentFingerprint


@dataclass(frozen=True, slots=True)
class AuthorizationDecisionProjection:
    outcome: DeploymentAuthorizationOutcome
    evidence: AuthorizationEvidenceV1 | None

    @property
    def consumable(self) -> bool:
        return self.outcome is DeploymentAuthorizationOutcome.ALLOWED and self.evidence is not None


class DecisionAuthority(Protocol):
    def evaluate(self, request: DecisionRequest) -> DecisionResult: ...


class DeploymentGovernanceAdapter:
    def __init__(self, authority: DecisionAuthority | None) -> None:
        self._authority = authority

    def authorize(self, intent: AuthorizationIntent) -> AuthorizationDecisionProjection:
        if self._authority is None:
            return AuthorizationDecisionProjection(DeploymentAuthorizationOutcome.UNAVAILABLE, None)
        try:
            decision = self._authority.evaluate(to_decision_request(intent))
        except Exception:
            return AuthorizationDecisionProjection(DeploymentAuthorizationOutcome.UNAVAILABLE, None)
        return project_authority_decision(intent, decision)


class AuthorizationProjectionRegistry:
    def __init__(self) -> None:
        self._facts: dict[str, DeploymentFingerprint] = {}

    def accept(
        self, projection: AuthorizationDecisionProjection
    ) -> AuthorizationDecisionProjection:
        if projection.evidence is None:
            return projection
        identity = projection.evidence.decision_identity
        known = self._facts.get(identity)
        if known is not None and known != projection.evidence.decision_fingerprint:
            raise AuthorizationContradiction("authority decision identity is contradictory")
        self._facts[identity] = projection.evidence.decision_fingerprint
        return projection


def _validate_release(
    release: DeploymentReleaseV1,
    target_id: DeploymentTargetId,
    artifact: DeploymentArtifactRefV1,
    revision: RevisionId,
) -> None:
    if (
        release.target_id != target_id
        or release.artifact != artifact
        or release.desired_revision.revision_id != revision
    ):
        raise AuthorizationBindingError("release authorization binding mismatch")


def _scope(intent: AuthorizationIntent) -> _Scope:
    if isinstance(intent, DeploymentOperationIntentV1):
        attempt = intent.attempt_id.value
    elif isinstance(intent, RolloutAuthorizationIntentV1):
        attempt = intent.rollout_id.value
    elif isinstance(intent, PromotionAuthorizationIntentV1):
        attempt = intent.promotion_id.value
    else:
        attempt = intent.rollback_attempt_id.value
    operation = (
        intent.operation.value
        if isinstance(intent.operation, DeploymentOperation)
        else intent.operation
    )
    return _Scope(
        intent.requester,
        intent.release.release_id,
        attempt,
        intent.environment_id,
        intent.target_id,
        intent.artifact,
        intent.desired_revision,
        operation,
        intent.policy_reference,
        intent.correlation,
        intent.causation,
        intent.semantic_fingerprint,
    )


def to_decision_request(intent: AuthorizationIntent) -> DecisionRequest:
    scope = _scope(intent)
    return DecisionRequest(
        actor_type="deployment-requester",
        actor_id=scope.requester.value,
        action=f"deployment.{scope.operation}",
        category="tool_execution",
        resource_scope=scope.target_id.value,
        metadata={"tool_definition": {"risk_level": "high"}, **scope.payload()},
        correlation_id=scope.correlation.value,
    )


def project_authority_decision(
    intent: AuthorizationIntent,
    decision: DecisionResult,
    approval: ApprovalRequest | None = None,
    *,
    observed_at: datetime | None = None,
) -> AuthorizationDecisionProjection:
    scope = _scope(intent)
    if decision.allowed and (decision.blocked or decision.requires_approval):
        raise AuthorizationBindingError("authority returned contradictory decision flags")
    if approval is not None:
        _validate_approval(scope, approval)
        outcome = {
            "approved": DeploymentAuthorizationOutcome.ALLOWED,
            "rejected": DeploymentAuthorizationOutcome.DENIED,
            "pending": DeploymentAuthorizationOutcome.APPROVAL_REQUIRED,
            "expired": DeploymentAuthorizationOutcome.EXPIRED,
            "resumed": DeploymentAuthorizationOutcome.STALE,
        }.get(approval.status, DeploymentAuthorizationOutcome.STALE)
        identity = f"approval:{approval.id}"
        expiry = approval.expires_at
        authority_revision = f"approvals-schema:{approval.schema_version}"
    else:
        outcome = (
            DeploymentAuthorizationOutcome.ALLOWED
            if decision.allowed
            else DeploymentAuthorizationOutcome.APPROVAL_REQUIRED
            if decision.requires_approval
            else DeploymentAuthorizationOutcome.DENIED
            if decision.blocked
            else DeploymentAuthorizationOutcome.UNAVAILABLE
        )
        identity = f"decision:{_fingerprint((scope.payload(), decision.to_dict())).value[7:]}"
        expiry = None
        authority_revision = "decisions-v1"
    now = observed_at or datetime.now(UTC)
    if expiry is not None and datetime.fromisoformat(expiry) <= now:
        outcome = DeploymentAuthorizationOutcome.EXPIRED
    content = (
        identity,
        scope.payload(),
        outcome.value,
        expiry,
        AUTHORITY_VERSION,
        authority_revision,
    )
    decision_fingerprint = _fingerprint(content)
    authorization = (
        AuthorizationReference(identity)
        if outcome is DeploymentAuthorizationOutcome.ALLOWED
        else None
    )
    evidence = AuthorizationEvidenceV1(
        identity,
        authorization,
        EvidenceReference(f"evidence:{decision_fingerprint.value[7:]}"),
        scope.operation,
        scope.requester,
        scope.release_id,
        scope.attempt_reference,
        scope.environment_id,
        scope.target_id,
        scope.artifact.artifact,
        scope.artifact.fingerprint.value,
        scope.desired_revision,
        scope.policy_reference,
        outcome,
        expiry,
        AUTHORITY_VERSION,
        authority_revision,
        scope.semantic_fingerprint,
        decision_fingerprint,
    )
    return AuthorizationDecisionProjection(outcome, evidence)


def _validate_approval(scope: _Scope, approval: ApprovalRequest) -> None:
    if (
        approval.agent_id != scope.requester.value
        or approval.tool_name != f"deployment.{scope.operation}"
        or approval.tool_args != scope.payload()
        or approval.risk_level != "high"
        or approval.correlation_id != scope.correlation.value
        or approval.causation_id != (scope.causation.value if scope.causation else None)
    ):
        raise AuthorizationBindingError("approval evidence does not exactly correspond")


def _fingerprint(value: object) -> DeploymentFingerprint:
    import hashlib

    return DeploymentFingerprint(
        "sha256:" + hashlib.sha256(canonical_json(value).encode()).hexdigest()
    )


def bind_authorization_event(
    intent: AuthorizationIntent,
    projection: AuthorizationDecisionProjection,
    event_id: DeploymentEventId,
    occurrence: OccurrenceReference,
) -> (
    DeploymentTransitionEventV1
    | RolloutTransitionEventV1
    | PromotionTransitionEventV1
    | RollbackTransitionEventV1
):
    if (
        projection.outcome
        not in {
            DeploymentAuthorizationOutcome.ALLOWED,
            DeploymentAuthorizationOutcome.DENIED,
        }
        or projection.evidence is None
    ):
        raise AuthorizationBindingError("non-final authorization cannot create a lifecycle event")
    scope = _scope(intent)
    evidence = projection.evidence
    if (
        evidence.requester != scope.requester
        or evidence.target_id != scope.target_id
        or evidence.environment_id != scope.environment_id
        or evidence.artifact_reference != scope.artifact.artifact
        or evidence.revision_id != scope.desired_revision
        or evidence.attempt_reference != scope.attempt_reference
        or evidence.operation != scope.operation
        or evidence.policy_reference != scope.policy_reference
        or evidence.semantic_fingerprint != scope.semantic_fingerprint
    ):
        raise AuthorizationBindingError("authorization projection is stale or mismatched")
    allowed = projection.outcome is DeploymentAuthorizationOutcome.ALLOWED
    reference = evidence.authorization_reference if allowed else None
    failure = None if allowed else TransitionFailureClass.POLICY_DENIED
    common = (event_id, intent.correlation, intent.causation, occurrence)
    if isinstance(intent, DeploymentOperationIntentV1):
        return DeploymentTransitionEventV1(
            common[0],
            intent.release.release_id,
            intent.attempt_id,
            DeploymentLifecycleState.AUTHORIZATION_PENDING,
            DeploymentLifecycleState.AUTHORIZED if allowed else DeploymentLifecycleState.DENIED,
            common[1],
            common[2],
            common[3],
            reference,
            failure_class=failure,
        )
    if isinstance(intent, RolloutAuthorizationIntentV1):
        return RolloutTransitionEventV1(
            common[0],
            intent.rollout_id,
            intent.release.release_id,
            RolloutLifecycleState.PLANNED,
            RolloutLifecycleState.AUTHORIZED if allowed else RolloutLifecycleState.BLOCKED,
            common[1],
            common[2],
            common[3],
            reference,
            failure_class=failure,
        )
    if isinstance(intent, PromotionAuthorizationIntentV1):
        return PromotionTransitionEventV1(
            common[0],
            intent.promotion_id,
            intent.rollout_id,
            PromotionLifecycleState.PENDING,
            PromotionLifecycleState.AUTHORIZED if allowed else PromotionLifecycleState.DENIED,
            common[1],
            common[2],
            common[3],
            reference,
            failure_class=failure,
        )
    return RollbackTransitionEventV1(
        common[0],
        intent.rollback_attempt_id,
        intent.release.release_id,
        intent.target_id,
        intent.current_revision,
        intent.desired_revision,
        intent.artifact.artifact,
        RollbackLifecycleState.AUTHORIZATION_PENDING,
        RollbackLifecycleState.AUTHORIZED if allowed else RollbackLifecycleState.DENIED,
        common[1],
        common[2],
        common[3],
        reference,
        failure_class=failure,
    )
