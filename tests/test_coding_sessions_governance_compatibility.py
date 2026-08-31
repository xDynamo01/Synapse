from dataclasses import replace

from tests.test_coding_sessions_intents import _contract, _intent

from synapse.approvals import ApprovalRequest
from synapse.coding_sessions import (
    CodingSessionFingerprint,
    CodingSessionIntentCategory,
    CodingSessionLifecycleState,
    CodingSessionRequestedCapability,
    CodingSessionStateProjection,
    CodingSessionTargetAuthority,
)
from synapse.coding_sessions_integrations import (
    CodingSessionAuthorizationStatus,
    CodingSessionGovernanceCompatibilityAdapter,
    CodingSessionGovernanceDiagnosticCode,
    CodingSessionGovernanceReceipt,
    CodingSessionGovernanceRequestContext,
)
from synapse.decisions.models import DecisionRequest
from synapse.project_governance.models import RFCGateRequest


def _context(state: CodingSessionLifecycleState = CodingSessionLifecycleState.ACTIVE):
    contract = _contract(capability=CodingSessionRequestedCapability.APPROVAL)
    intent = _intent(
        contract,
        category=CodingSessionIntentCategory.AUTHORIZATION_REQUEST,
        authority=CodingSessionTargetAuthority.GOVERNANCE_APPROVALS,
        capability=CodingSessionRequestedCapability.APPROVAL,
        write=False,
    )
    lifecycle = CodingSessionStateProjection(contract.session_identity, lifecycle=state)
    return CodingSessionGovernanceRequestContext(
        contract,
        lifecycle,
        intent,
        "repository-mutation",
        "worktree:one",
        ("path:src",),
        "governance-policy",
        "v1",
        (CodingSessionFingerprint.from_content("plan"),),
    )


def _receipt(context, **changes):
    base = CodingSessionGovernanceReceipt(
        producer="approvals",
        producer_version="v1",
        identity="approval:one",
        producer_fingerprint=CodingSessionFingerprint.from_content("approval"),
        session_identity=context.contract.session_identity.value,
        actor=context.contract.actor.value,
        project=context.contract.project.value,
        purpose=context.contract.purpose.purpose.value,
        capability=context.capability,
        resource=context.resource,
        scope=context.scope,
        status=CodingSessionAuthorizationStatus.GRANTED,
        decision_type="approval",
        valid_from=10,
        valid_until=20,
        causal_revision=1,
        parent_identity=None,
        policy_id=context.policy_id,
        policy_version=context.policy_version,
    )
    return replace(base, **changes)


def test_translation_targets_public_contracts_without_granting_authority() -> None:
    context = _context()
    adapter = CodingSessionGovernanceCompatibilityAdapter()

    decision = adapter.decision_request(context)
    gate = adapter.project_gate_request(context)
    approval = adapter.approval_request(context, risk_level="high")

    assert isinstance(decision.request, DecisionRequest)
    assert isinstance(gate.request, RFCGateRequest)
    assert isinstance(approval.request, ApprovalRequest)
    assert decision.request.metadata["session_identity"] == context.contract.session_identity.value
    assert gate.request.project_id == context.contract.project.value
    assert approval.request.status == "pending"
    assert all(not item.authorization_created for item in (decision, gate, approval))
    assert all(not item.approval_granted for item in (decision, gate, approval))
    assert all(not item.operation_executed for item in (decision, gate, approval))


def test_correspondence_mismatch_fails_closed() -> None:
    context = _context()
    mismatched = replace(context.intent, actor=replace(context.contract.actor, value="actor:other"))

    result = CodingSessionGovernanceCompatibilityAdapter.decision_request(
        replace(context, intent=mismatched)
    )

    assert result.request is None
    assert CodingSessionGovernanceDiagnosticCode.ACTOR_MISMATCH in {
        item.code for item in result.diagnostics
    }


def test_denied_revoked_expired_and_stale_remain_distinct_and_non_authoritative() -> None:
    context = _context()
    adapter = CodingSessionGovernanceCompatibilityAdapter()
    variants = (
        _receipt(context, status=CodingSessionAuthorizationStatus.DENIED),
        _receipt(context, identity="approval:revoked", status=CodingSessionAuthorizationStatus.REVOKED),
        _receipt(context, identity="approval:expired", status=CodingSessionAuthorizationStatus.EXPIRED, valid_until=11),
        _receipt(context, identity="approval:stale", status=CodingSessionAuthorizationStatus.STALE),
    )

    results = tuple(adapter.project_receipt(context, item, observed_at=15) for item in variants)

    assert [item.status for item in results] == [item.status for item in variants]
    assert all(not item.grants_authority for item in results)
    assert CodingSessionGovernanceDiagnosticCode.REVOKED in {item.code for item in results[1].diagnostics}
    assert CodingSessionGovernanceDiagnosticCode.EXPIRED in {item.code for item in results[2].diagnostics}
    assert CodingSessionGovernanceDiagnosticCode.STALE in {item.code for item in results[3].diagnostics}


def test_conflict_and_lineage_gap_stay_explicit() -> None:
    context = _context()
    original = _receipt(context)
    conflicting = replace(
        original,
        status=CodingSessionAuthorizationStatus.DENIED,
        causal_revision=2,
        parent_identity=None,
    )

    result = CodingSessionGovernanceCompatibilityAdapter.project_receipt(
        context, conflicting, observed_at=15, known_receipts=(original,)
    )

    codes = {item.code for item in result.diagnostics}
    assert CodingSessionGovernanceDiagnosticCode.CONFLICTING in codes
    assert CodingSessionGovernanceDiagnosticCode.LINEAGE_GAP in codes
    assert result.producer_reference is None


def test_late_receipt_is_fact_only_and_never_reopens_terminal_session() -> None:
    context = _context(CodingSessionLifecycleState.TERMINAL)

    result = CodingSessionGovernanceCompatibilityAdapter.project_receipt(
        context, _receipt(context), observed_at=15
    )

    assert CodingSessionGovernanceDiagnosticCode.LATE in {item.code for item in result.diagnostics}
    assert not result.reopens_session
    assert not result.grants_authority


def test_same_canonical_input_is_deterministic_and_occurrence_is_not_added() -> None:
    context = _context()
    first = CodingSessionGovernanceCompatibilityAdapter.decision_request(context)
    second = CodingSessionGovernanceCompatibilityAdapter.decision_request(context)
    first_approval = CodingSessionGovernanceCompatibilityAdapter.approval_request(
        context, risk_level="high"
    )
    second_approval = CodingSessionGovernanceCompatibilityAdapter.approval_request(
        context, risk_level="high"
    )

    assert first == second
    assert first_approval == second_approval
    assert "occurrence" not in first.request.metadata
