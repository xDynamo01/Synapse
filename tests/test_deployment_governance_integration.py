from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from synapse.approvals import ApprovalRequest
from synapse.decisions.models import DecisionResult
from synapse.deployment import (
    ArtifactFingerprintReference,
    ArtifactMediaClass,
    ArtifactReference,
    CausationReference,
    CorrelationReference,
    CustodyReference,
    DeploymentArtifactRefV1,
    DeploymentAttemptId,
    DeploymentAuthorizationOutcome,
    DeploymentEventId,
    DeploymentFingerprint,
    DeploymentIntentId,
    DeploymentLifecycleState,
    DeploymentOperation,
    DeploymentReleaseV1,
    DeploymentTargetId,
    DesiredRevisionV1,
    EnvironmentId,
    OccurrenceReference,
    PolicyReference,
    PromotionId,
    PromotionLifecycleState,
    ProvenanceReference,
    ReleaseId,
    RequesterReference,
    RevisionId,
    RollbackAttemptId,
    RollbackLifecycleState,
    RolloutId,
    RolloutLifecycleState,
)
from synapse.deployment_integrations import (
    AuthorizationIntent,
    AuthorizationProjectionRegistry,
    DeploymentGovernanceAdapter,
    DeploymentOperationIntentV1,
    PromotionAuthorizationIntentV1,
    RollbackAuthorizationIntentV1,
    RolloutAuthorizationIntentV1,
    bind_authorization_event,
    project_authority_decision,
)
from synapse.deployment_integrations.governance import (
    AuthorizationBindingError,
    AuthorizationContradiction,
    to_decision_request,
)


def _facts() -> tuple[DeploymentReleaseV1, DeploymentArtifactRefV1]:
    artifact = DeploymentArtifactRefV1(
        ArtifactReference("artifact:release-006"),
        ArtifactFingerprintReference("fingerprint:release-006"),
        ProvenanceReference("provenance:build-006"),
        ArtifactMediaClass.APPLICATION_BUNDLE,
        CustodyReference("custody:approved"),
        "application/zip",
    )
    revision = DesiredRevisionV1(RevisionId("deployment-revision:006"), artifact.fingerprint)
    release = DeploymentReleaseV1(
        ReleaseId("deployment-release:006"),
        DeploymentIntentId("deployment-intent:006"),
        DeploymentFingerprint("sha256:" + "6" * 64),
        artifact,
        DeploymentTargetId("deployment-target:api"),
        revision,
        PolicyReference("policy:deployment-v1"),
    )
    return release, artifact


def _deployment_intent() -> DeploymentOperationIntentV1:
    release, artifact = _facts()
    return DeploymentOperationIntentV1(
        RequesterReference("subject:operator"), release,
        DeploymentAttemptId("deployment-attempt:006"),
        EnvironmentId("deployment-environment:staging"), release.target_id, artifact,
        release.desired_revision.revision_id, DeploymentOperation.APPLY,
        release.policy_reference, CorrelationReference("correlation:006"),
        CausationReference("causation:006"),
        DeploymentFingerprint("sha256:" + "a" * 64),
    )


def _decision(*, allowed: bool = False, blocked: bool = False, approval: bool = False) -> DecisionResult:
    return DecisionResult(allowed, blocked, approval, "high")


def _approval(intent: DeploymentOperationIntentV1, status: str = "approved") -> ApprovalRequest:
    request = to_decision_request(intent)
    return ApprovalRequest(
        agent_id=intent.requester.value,
        tool_name=request.action,
        tool_args=dict(request.metadata) | {},
        risk_level="high",
        reason="deployment authorization",
        tool_call_id="deployment-call-006",
        status=status,
        correlation_id=intent.correlation.value,
        causation_id=intent.causation.value if intent.causation else None,
        id="approval-006",
    )


def _bound_approval(intent: DeploymentOperationIntentV1, status: str = "approved") -> ApprovalRequest:
    approval = _approval(intent, status)
    return replace(approval, tool_args={key: value for key, value in approval.tool_args.items() if key != "tool_definition"})


@pytest.mark.parametrize(
    ("decision", "status", "expected"),
    [
        (_decision(allowed=True), None, DeploymentAuthorizationOutcome.ALLOWED),
        (_decision(blocked=True), None, DeploymentAuthorizationOutcome.DENIED),
        (_decision(approval=True), None, DeploymentAuthorizationOutcome.APPROVAL_REQUIRED),
        (_decision(), None, DeploymentAuthorizationOutcome.UNAVAILABLE),
        (_decision(approval=True), "approved", DeploymentAuthorizationOutcome.ALLOWED),
        (_decision(approval=True), "rejected", DeploymentAuthorizationOutcome.DENIED),
        (_decision(approval=True), "pending", DeploymentAuthorizationOutcome.APPROVAL_REQUIRED),
        (_decision(approval=True), "expired", DeploymentAuthorizationOutcome.EXPIRED),
        (_decision(approval=True), "resumed", DeploymentAuthorizationOutcome.STALE),
    ],
)
def test_authority_outcomes_remain_factual(decision: DecisionResult, status: str | None, expected: DeploymentAuthorizationOutcome) -> None:
    intent = _deployment_intent()
    approval = _bound_approval(intent, status) if status else None
    projected = project_authority_decision(intent, decision, approval)
    assert projected.outcome is expected
    assert projected.consumable is (expected is DeploymentAuthorizationOutcome.ALLOWED)


def test_safe_projection_contains_exact_scope_but_no_raw_governance_payload() -> None:
    intent = _deployment_intent()
    projected = project_authority_decision(intent, _decision(approval=True), _bound_approval(intent))
    evidence = projected.evidence
    assert evidence is not None
    assert evidence.target_id == intent.target_id
    assert evidence.environment_id == intent.environment_id
    assert evidence.semantic_fingerprint == intent.semantic_fingerprint
    assert evidence.authority_revision == "approvals-schema:1"
    assert not hasattr(evidence, "tool_args")
    assert not hasattr(evidence, "metadata")
    assert not hasattr(evidence, "fencing_generation")


@pytest.mark.parametrize(
    "change",
    [
        {"agent_id": "subject:other"},
        {"tool_name": "deployment.prepare"},
        {"risk_level": "medium"},
        {"correlation_id": "correlation:other"},
        {"causation_id": "causation:other"},
    ],
)
def test_approval_identity_and_context_mismatch_fail_closed(change: dict[str, str]) -> None:
    intent = _deployment_intent()
    with pytest.raises(AuthorizationBindingError):
        project_authority_decision(intent, _decision(approval=True), replace(_bound_approval(intent), **change))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("target_id", "deployment-target:other"),
        ("environment_id", "deployment-environment:other"),
        ("artifact_reference", "artifact:other"),
        ("revision_id", "deployment-revision:other"),
        ("attempt_reference", "deployment-attempt:other"),
        ("operation", "prepare"),
        ("requester", "subject:other"),
        ("policy_reference", "policy:other"),
    ],
)
def test_every_scope_mismatch_fails_closed(field: str, value: str) -> None:
    intent = _deployment_intent()
    approval = _bound_approval(intent)
    args = dict(approval.tool_args)
    args[field] = value
    with pytest.raises(AuthorizationBindingError):
        project_authority_decision(intent, _decision(approval=True), replace(approval, tool_args=args))


def test_expiry_is_checked_at_consumption_time() -> None:
    intent = _deployment_intent()
    expired = replace(_bound_approval(intent), expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat())
    assert project_authority_decision(intent, _decision(approval=True), expired).outcome is DeploymentAuthorizationOutcome.EXPIRED


def test_duplicate_decision_is_idempotent_and_contradiction_rejected() -> None:
    intent = _deployment_intent()
    registry = AuthorizationProjectionRegistry()
    fact = project_authority_decision(intent, _decision(approval=True), _bound_approval(intent))
    assert registry.accept(fact) == registry.accept(fact)
    contrary = project_authority_decision(intent, _decision(approval=True), replace(_bound_approval(intent), status="rejected"))
    with pytest.raises(AuthorizationContradiction):
        registry.accept(contrary)


def test_absent_or_failing_authority_is_unavailable_and_fail_closed() -> None:
    intent = _deployment_intent()
    assert DeploymentGovernanceAdapter(None).authorize(intent).outcome is DeploymentAuthorizationOutcome.UNAVAILABLE

    class Broken:
        def evaluate(self, request: object) -> DecisionResult:
            raise RuntimeError("authority unavailable")

    assert DeploymentGovernanceAdapter(Broken()).authorize(intent).outcome is DeploymentAuthorizationOutcome.UNAVAILABLE


def test_allowed_only_binds_events_and_never_executes_effects() -> None:
    intent = _deployment_intent()
    projection = project_authority_decision(intent, _decision(allowed=True))
    event = bind_authorization_event(intent, projection, DeploymentEventId("deployment-event:auth"), OccurrenceReference("occurrence:auth"))
    assert projection.evidence is not None
    assert event.resulting_state is DeploymentLifecycleState.AUTHORIZED
    assert event.authorization_reference == projection.evidence.authorization_reference
    assert not hasattr(event, "apply")
    assert not hasattr(projection, "apply_receipt_reference")


def test_rollout_promotion_and_rollback_receive_only_authorization_references() -> None:
    base = _deployment_intent()
    intents: tuple[AuthorizationIntent, ...] = (
        RolloutAuthorizationIntentV1(
            base.requester, base.release, RolloutId("deployment-rollout:006"),
            base.environment_id, base.target_id, base.artifact, base.desired_revision,
            base.policy_reference, base.correlation, base.causation, base.semantic_fingerprint,
        ),
        PromotionAuthorizationIntentV1(
            base.requester, base.release, PromotionId("deployment-promotion:006"),
            RolloutId("deployment-rollout:006"), base.environment_id, base.target_id,
            base.artifact, base.desired_revision, base.policy_reference, base.correlation,
            base.causation, base.semantic_fingerprint,
        ),
        RollbackAuthorizationIntentV1(
            base.requester, base.release,
            RollbackAttemptId("deployment-rollback-attempt:006"), base.environment_id,
            base.target_id, base.artifact, RevisionId("deployment-revision:007"),
            base.desired_revision, DeploymentOperation.ROLLBACK_APPLY,
            base.policy_reference, base.correlation, base.causation,
            base.semantic_fingerprint,
        ),
    )
    expected = (RolloutLifecycleState.AUTHORIZED, PromotionLifecycleState.AUTHORIZED, RollbackLifecycleState.AUTHORIZED)
    for index, (intent, state) in enumerate(zip(intents, expected, strict=True)):
        projection = project_authority_decision(intent, _decision(allowed=True))
        event = bind_authorization_event(intent, projection, DeploymentEventId(f"deployment-event:auth-{index}"), OccurrenceReference(f"occurrence:auth-{index}"))
        assert projection.evidence is not None
        assert event.resulting_state is state
        assert event.authorization_reference == projection.evidence.authorization_reference


def test_replay_contract_does_not_reauthorize() -> None:
    assert "authority" not in DeploymentLifecycleState.__members__
    assert not hasattr(DeploymentGovernanceAdapter, "replay")
