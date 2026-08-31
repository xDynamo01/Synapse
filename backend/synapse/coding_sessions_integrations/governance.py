"""Reference-only compatibility with Governance and Approvals authorities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from synapse.approvals import ApprovalRequest
from synapse.coding_sessions import (
    CODING_SESSION_INTENT_POLICY_VERSION,
    CodingSessionApprovalReference,
    CodingSessionAuthorizationReference,
    CodingSessionContract,
    CodingSessionFingerprint,
    CodingSessionIntent,
    CodingSessionIntentCategory,
    CodingSessionLifecycleState,
    CodingSessionProducerReference,
    CodingSessionRequestedCapability,
    CodingSessionStateProjection,
    CodingSessionTargetAuthority,
)
from synapse.decisions.models import DecisionRequest
from synapse.project_governance.models import RFCGateRequest

CODING_SESSION_GOVERNANCE_COMPATIBILITY_VERSION = (
    "coding-session-governance-compatibility-v1"
)


class CodingSessionAuthorizationStatus(str, Enum):
    NOT_REQUESTED = "not-requested"
    PENDING = "pending"
    GRANTED = "granted"
    DENIED = "denied"
    EXPIRED = "expired"
    REVOKED = "revoked"
    STALE = "stale"
    CONFLICTING = "conflicting"
    UNKNOWN = "unknown"


class CodingSessionGovernanceDiagnosticCode(str, Enum):
    SESSION_MISMATCH = "session-mismatch"
    ACTOR_MISMATCH = "actor-mismatch"
    PROJECT_MISMATCH = "project-mismatch"
    PURPOSE_MISMATCH = "purpose-mismatch"
    CAPABILITY_MISMATCH = "capability-mismatch"
    SCOPE_MISMATCH = "scope-mismatch"
    RESOURCE_MISMATCH = "resource-mismatch"
    PRODUCER_MISMATCH = "producer-mismatch"
    VERSION_MISMATCH = "version-mismatch"
    EXPIRED = "expired"
    REVOKED = "revoked"
    STALE = "stale"
    DUPLICATE = "duplicate"
    CONFLICTING = "conflicting"
    LATE = "late"
    LINEAGE_GAP = "lineage-gap"
    LIFECYCLE_INCOMPATIBLE = "lifecycle-incompatible"


@dataclass(frozen=True, slots=True, order=True)
class CodingSessionGovernanceDiagnostic:
    code: CodingSessionGovernanceDiagnosticCode
    subject: str = "governance-compatibility"


@dataclass(frozen=True, slots=True)
class CodingSessionGovernanceRequestContext:
    contract: CodingSessionContract
    lifecycle: CodingSessionStateProjection
    intent: CodingSessionIntent
    capability: str
    resource: str
    scope: tuple[str, ...]
    policy_id: str
    policy_version: str
    external_fingerprints: tuple[CodingSessionFingerprint, ...] = ()


@dataclass(frozen=True, slots=True)
class CodingSessionGovernanceTranslation:
    request: DecisionRequest | RFCGateRequest | ApprovalRequest | None
    intent_fingerprint: CodingSessionFingerprint
    authorization_created: bool
    approval_granted: bool
    operation_executed: bool
    diagnostics: tuple[CodingSessionGovernanceDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class CodingSessionGovernanceReceipt:
    producer: str
    producer_version: str
    identity: str
    producer_fingerprint: CodingSessionFingerprint
    session_identity: str
    actor: str
    project: str
    purpose: str
    capability: str
    resource: str
    scope: tuple[str, ...]
    status: CodingSessionAuthorizationStatus
    decision_type: str
    valid_from: int | None
    valid_until: int | None
    causal_revision: int
    parent_identity: str | None
    policy_id: str
    policy_version: str


@dataclass(frozen=True, slots=True)
class CodingSessionGovernanceProjection:
    status: CodingSessionAuthorizationStatus
    producer_reference: CodingSessionProducerReference | None
    reopens_session: bool
    grants_authority: bool
    diagnostics: tuple[CodingSessionGovernanceDiagnostic, ...]


class CodingSessionGovernanceCompatibilityAdapter:
    """Pure mapping that neither calls a producer nor changes session state."""

    @staticmethod
    def decision_request(
        context: CodingSessionGovernanceRequestContext,
    ) -> CodingSessionGovernanceTranslation:
        diagnostics = _request_diagnostics(context)
        request = None
        if not diagnostics:
            request = DecisionRequest(
                actor_type="coding-session-actor",
                actor_id=context.contract.actor.value,
                action=context.intent.target_type,
                category="capability",
                capability_id=context.capability,
                resource_scope={"resource": context.resource, "scope": context.scope},
                correlation_id=context.contract.correlation.value,
                metadata=_metadata(context),
            )
        return _translation(context, request, diagnostics)

    @staticmethod
    def project_gate_request(
        context: CodingSessionGovernanceRequestContext,
    ) -> CodingSessionGovernanceTranslation:
        diagnostics = _request_diagnostics(context)
        request = None
        if not diagnostics:
            request = RFCGateRequest(
                project_id=context.contract.project.value,
                requested_change=context.intent.target_type,
                domains=context.scope,
                contracts=(),
                requester=context.contract.actor.value,
                correlation_id=context.contract.correlation.value,
                impact=_metadata(context),
            )
        return _translation(context, request, diagnostics)

    @staticmethod
    def approval_request(
        context: CodingSessionGovernanceRequestContext,
        *,
        risk_level: str,
    ) -> CodingSessionGovernanceTranslation:
        diagnostics = _request_diagnostics(context)
        request = None
        if not diagnostics:
            request = ApprovalRequest(
                id=f"approval:{context.intent.intent_identity.value}",
                agent_id=context.contract.actor.value,
                tool_name=context.capability,
                tool_args={"resource": context.resource, "scope": context.scope},
                risk_level=risk_level,
                reason=context.contract.purpose.purpose.value,
                tool_call_id=context.intent.intent_identity.value,
                session_id=context.contract.session_identity.value,
                project_id=context.contract.project.value,
                correlation_id=context.contract.correlation.value,
                source=CODING_SESSION_GOVERNANCE_COMPATIBILITY_VERSION,
                created_at="not-observed",
                updated_at="not-observed",
            )
        return _translation(context, request, diagnostics)

    @staticmethod
    def project_receipt(
        context: CodingSessionGovernanceRequestContext,
        receipt: CodingSessionGovernanceReceipt,
        *,
        observed_at: int,
        known_receipts: tuple[CodingSessionGovernanceReceipt, ...] = (),
    ) -> CodingSessionGovernanceProjection:
        findings = set(_request_diagnostics(context))
        expected = context.contract
        if receipt.producer not in {"approvals", "decisions", "project-governance"}:
            findings.add(
                CodingSessionGovernanceDiagnostic(
                    CodingSessionGovernanceDiagnosticCode.PRODUCER_MISMATCH
                )
            )
        comparisons = (
            (receipt.session_identity, expected.session_identity.value, CodingSessionGovernanceDiagnosticCode.SESSION_MISMATCH),
            (receipt.actor, expected.actor.value, CodingSessionGovernanceDiagnosticCode.ACTOR_MISMATCH),
            (receipt.project, expected.project.value, CodingSessionGovernanceDiagnosticCode.PROJECT_MISMATCH),
            (receipt.purpose, expected.purpose.purpose.value, CodingSessionGovernanceDiagnosticCode.PURPOSE_MISMATCH),
            (receipt.capability, context.capability, CodingSessionGovernanceDiagnosticCode.CAPABILITY_MISMATCH),
            (receipt.resource, context.resource, CodingSessionGovernanceDiagnosticCode.RESOURCE_MISMATCH),
            (receipt.scope, context.scope, CodingSessionGovernanceDiagnosticCode.SCOPE_MISMATCH),
            (receipt.policy_version, context.policy_version, CodingSessionGovernanceDiagnosticCode.VERSION_MISMATCH),
        )
        for actual, wanted, code in comparisons:
            if actual != wanted:
                findings.add(CodingSessionGovernanceDiagnostic(code))
        if receipt.valid_until is not None and observed_at > receipt.valid_until:
            findings.add(CodingSessionGovernanceDiagnostic(CodingSessionGovernanceDiagnosticCode.EXPIRED))
        if receipt.status is CodingSessionAuthorizationStatus.REVOKED:
            findings.add(CodingSessionGovernanceDiagnostic(CodingSessionGovernanceDiagnosticCode.REVOKED))
        if receipt.status is CodingSessionAuthorizationStatus.STALE:
            findings.add(CodingSessionGovernanceDiagnostic(CodingSessionGovernanceDiagnosticCode.STALE))
        for known in known_receipts:
            if known.identity == receipt.identity:
                code = CodingSessionGovernanceDiagnosticCode.DUPLICATE if known == receipt else CodingSessionGovernanceDiagnosticCode.CONFLICTING
                findings.add(CodingSessionGovernanceDiagnostic(code))
            if known.causal_revision == receipt.causal_revision and known.identity != receipt.identity:
                findings.add(CodingSessionGovernanceDiagnostic(CodingSessionGovernanceDiagnosticCode.CONFLICTING))
        if receipt.causal_revision > 1 and receipt.parent_identity is None:
            findings.add(CodingSessionGovernanceDiagnostic(CodingSessionGovernanceDiagnosticCode.LINEAGE_GAP))
        terminal = context.lifecycle.lifecycle is CodingSessionLifecycleState.TERMINAL
        if terminal:
            findings.add(CodingSessionGovernanceDiagnostic(CodingSessionGovernanceDiagnosticCode.LATE))
        diagnostics = tuple(sorted(findings, key=lambda item: (item.code.value, item.subject)))
        reference = None
        if not any(item.code in _CORRESPONDENCE_FAILURES for item in diagnostics):
            reference_type = (
                CodingSessionApprovalReference
                if receipt.decision_type == "approval"
                else CodingSessionAuthorizationReference
            )
            reference = reference_type.create(
                receipt.producer, receipt.producer_version, receipt.identity,
                receipt.producer_fingerprint,
            )
        return CodingSessionGovernanceProjection(
            status=receipt.status,
            producer_reference=reference,
            reopens_session=False,
            grants_authority=False,
            diagnostics=diagnostics,
        )


def _request_diagnostics(
    context: CodingSessionGovernanceRequestContext,
) -> tuple[CodingSessionGovernanceDiagnostic, ...]:
    findings: set[CodingSessionGovernanceDiagnostic] = set()
    contract, intent = context.contract, context.intent
    checks = (
        (intent.session_identity != contract.session_identity, CodingSessionGovernanceDiagnosticCode.SESSION_MISMATCH),
        (intent.actor != contract.actor, CodingSessionGovernanceDiagnosticCode.ACTOR_MISMATCH),
        (intent.purpose != contract.purpose, CodingSessionGovernanceDiagnosticCode.PURPOSE_MISMATCH),
        (intent.binding.project != contract.project, CodingSessionGovernanceDiagnosticCode.PROJECT_MISMATCH),
        (intent.requirement.requested_capability is not CodingSessionRequestedCapability.APPROVAL, CodingSessionGovernanceDiagnosticCode.CAPABILITY_MISMATCH),
        (intent.category is not CodingSessionIntentCategory.AUTHORIZATION_REQUEST, CodingSessionGovernanceDiagnosticCode.CAPABILITY_MISMATCH),
        (intent.target_authority is not CodingSessionTargetAuthority.GOVERNANCE_APPROVALS, CodingSessionGovernanceDiagnosticCode.PRODUCER_MISMATCH),
        (intent.policy_version != CODING_SESSION_INTENT_POLICY_VERSION, CodingSessionGovernanceDiagnosticCode.VERSION_MISMATCH),
        (context.lifecycle.lifecycle not in {CodingSessionLifecycleState.PREPARED, CodingSessionLifecycleState.ACTIVE}, CodingSessionGovernanceDiagnosticCode.LIFECYCLE_INCOMPATIBLE),
    )
    for failed, code in checks:
        if failed:
            findings.add(CodingSessionGovernanceDiagnostic(code))
    return tuple(sorted(findings, key=lambda item: (item.code.value, item.subject)))


def _metadata(context: CodingSessionGovernanceRequestContext) -> dict[str, object]:
    binding = context.contract.binding
    return {
        "adapter_version": CODING_SESSION_GOVERNANCE_COMPATIBILITY_VERSION,
        "session_identity": context.contract.session_identity.value,
        "task": context.contract.purpose.task.value,
        "purpose": context.contract.purpose.purpose.value,
        "intent_identity": context.intent.intent_identity.value,
        "intent_fingerprint": context.intent.fingerprint.value,
        "resource": context.resource,
        "scope": context.scope,
        "repository": binding.repository.identity if binding.repository else None,
        "checkout": binding.checkout.identity if binding.checkout else None,
        "worktree": binding.worktree.identity if binding.worktree else None,
        "external_fingerprints": tuple(item.value for item in context.external_fingerprints),
        "causal_revision": context.intent.causal_metadata.revision.value,
        "policy_id": context.policy_id,
        "policy_version": context.policy_version,
    }


def _translation(context, request, diagnostics):
    return CodingSessionGovernanceTranslation(
        request=request,
        intent_fingerprint=context.intent.fingerprint,
        authorization_created=False,
        approval_granted=False,
        operation_executed=False,
        diagnostics=diagnostics,
    )


_CORRESPONDENCE_FAILURES = {
    CodingSessionGovernanceDiagnosticCode.SESSION_MISMATCH,
    CodingSessionGovernanceDiagnosticCode.ACTOR_MISMATCH,
    CodingSessionGovernanceDiagnosticCode.PROJECT_MISMATCH,
    CodingSessionGovernanceDiagnosticCode.PURPOSE_MISMATCH,
    CodingSessionGovernanceDiagnosticCode.CAPABILITY_MISMATCH,
    CodingSessionGovernanceDiagnosticCode.SCOPE_MISMATCH,
    CodingSessionGovernanceDiagnosticCode.RESOURCE_MISMATCH,
    CodingSessionGovernanceDiagnosticCode.PRODUCER_MISMATCH,
    CodingSessionGovernanceDiagnosticCode.VERSION_MISMATCH,
    CodingSessionGovernanceDiagnosticCode.CONFLICTING,
    CodingSessionGovernanceDiagnosticCode.LINEAGE_GAP,
}
