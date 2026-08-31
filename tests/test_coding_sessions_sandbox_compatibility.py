from dataclasses import replace

from tests.test_coding_sessions_intents import _contract, _intent

from synapse.coding_sessions import (
    CodingSessionArtifactReference,
    CodingSessionFingerprint,
    CodingSessionIntentCategory,
    CodingSessionLifecycleState,
    CodingSessionRequestedCapability,
    CodingSessionStateProjection,
    CodingSessionTargetAuthority,
)
from synapse.coding_sessions_integrations import (
    CodingSessionExecutionBindingProjectionState,
    CodingSessionSandboxCompatibilityAdapter,
    CodingSessionSandboxContext,
    CodingSessionSandboxDiagnosticCode,
    CodingSessionSandboxReceipt,
    CodingSessionSandboxReceiptState,
)
from synapse.sandbox import (
    OpaqueReference,
    SandboxAdmissionRequest,
    SandboxArtifactFingerprint,
    SandboxAttemptId,
    SandboxIsolationProfileId,
    SandboxPlanFingerprint,
    SandboxPlanId,
    SandboxPolicyVersion,
    SandboxWorkloadId,
)


def _context(state: CodingSessionLifecycleState = CodingSessionLifecycleState.ACTIVE):
    contract = _contract(capability=CodingSessionRequestedCapability.SANDBOX_EXECUTION)
    intent = _intent(
        contract,
        category=CodingSessionIntentCategory.SANDBOX_EXECUTION_REQUEST,
        authority=CodingSessionTargetAuthority.SANDBOX,
        capability=CodingSessionRequestedCapability.SANDBOX_EXECUTION,
        write=False,
    )
    artifact_fingerprint = CodingSessionFingerprint.from_content("material")
    artifact = CodingSessionArtifactReference.create(
        "artifact-authority", "v1", "material:one", artifact_fingerprint
    )
    return CodingSessionSandboxContext(
        contract,
        CodingSessionStateProjection(contract.session_identity, lifecycle=state),
        intent,
        SandboxWorkloadId("workload:one"),
        SandboxPlanId("plan:one"),
        SandboxPlanFingerprint.from_content("plan"),
        SandboxAttemptId("attempt:one"),
        SandboxArtifactFingerprint.from_content("attempt"),
        ("process",),
        (artifact,),
        (),
        None,
        "policy:sandbox",
        "v1",
    )


def _receipt(context, **changes):
    binding = context.contract.binding
    base = CodingSessionSandboxReceipt(
        producer="sandbox",
        producer_version="v1",
        receipt_identity="receipt:one",
        receipt_fingerprint=CodingSessionFingerprint.from_content("receipt"),
        session_identity=context.contract.session_identity.value,
        intent_identity=context.intent.intent_identity.value,
        actor=context.contract.actor.value,
        purpose=context.contract.purpose.purpose.value,
        correlation=context.contract.correlation.value,
        plan_id=context.plan_id,
        plan_fingerprint=context.plan_fingerprint,
        attempt_id=context.attempt_id,
        attempt_fingerprint=context.attempt_fingerprint,
        requested_capabilities=context.requested_capabilities,
        repository_binding=(
            binding.repository.identity if binding.repository else None,
            binding.checkout.identity if binding.checkout else None,
            binding.worktree.identity if binding.worktree else None,
        ),
        authorization_fingerprints=(),
        external_reference_fingerprints=tuple(
            item.fingerprint for item in context.artifact_references if item.fingerprint
        ),
        state=CodingSessionSandboxReceiptState.RUNNING,
        execution_verified=False,
        verification_evidence_identity=None,
        verification_evidence_fingerprint=None,
        termination_observed=False,
        termination_proof_identity=None,
        termination_proof_fingerprint=None,
        cleanup_complete=True,
        exit_code=None,
        stale=False,
        causal_revision=1,
        parent_receipt_identity=None,
    )
    return replace(base, **changes)


def test_admission_request_is_public_and_does_not_admit_locally() -> None:
    context = _context()
    result = CodingSessionSandboxCompatibilityAdapter.admission_request(
        context,
        isolation_profile_id=SandboxIsolationProfileId("profile:one"),
        isolation_policy_version=SandboxPolicyVersion("v1"),
        execution_profile=OpaqueReference("execution:profile"),
    )

    assert isinstance(result.request, SandboxAdmissionRequest)
    assert not result.admission_decided
    assert not result.driver_selected
    assert not result.process_started


def test_execution_request_contains_no_driver_command_or_local_effect() -> None:
    result = CodingSessionSandboxCompatibilityAdapter.execution_request(_context())

    assert result.request is not None
    assert result.request.reference.isolation_driver is None
    assert result.request.reference.process_command is None
    assert not result.request.admission_granted_locally
    assert not result.request.process_started_locally
    assert not result.process_started
    assert not result.process_terminated
    assert not result.capability_grant_changed


def test_running_admission_denial_and_unavailable_never_change_session_lifecycle() -> None:
    context = _context(CodingSessionLifecycleState.PREPARED)
    states = (
        CodingSessionSandboxReceiptState.ADMITTED,
        CodingSessionSandboxReceiptState.RUNNING,
        CodingSessionSandboxReceiptState.DENIED,
        CodingSessionSandboxReceiptState.UNAVAILABLE,
    )
    projections = tuple(
        CodingSessionSandboxCompatibilityAdapter.project_receipt(
            context, _receipt(context, state=state)
        )
        for state in states
    )

    assert all(not item.session_lifecycle_changed for item in projections)
    assert all(not item.session_completed for item in projections)
    assert all(not item.session_failed for item in projections)
    assert all(not item.admission_as_authorization for item in projections)


def test_exit_even_zero_is_unverified_and_not_session_success() -> None:
    context = _context()
    projection = CodingSessionSandboxCompatibilityAdapter.project_receipt(
        context,
        _receipt(context, state=CodingSessionSandboxReceiptState.EXITED, exit_code=0),
    )

    assert projection.state is CodingSessionExecutionBindingProjectionState.EXITED_UNVERIFIED
    assert not projection.session_completed
    assert not projection.session_failed


def test_verified_requires_specific_evidence_not_boolean_or_exit_code() -> None:
    context = _context()
    missing = CodingSessionSandboxCompatibilityAdapter.project_receipt(
        context, _receipt(context, execution_verified=True, exit_code=0)
    )
    factual = CodingSessionSandboxCompatibilityAdapter.project_receipt(
        context,
        _receipt(
            context,
            execution_verified=True,
            verification_evidence_identity="evidence:one",
            verification_evidence_fingerprint=CodingSessionFingerprint.from_content("evidence"),
        ),
    )

    assert missing.state is not CodingSessionExecutionBindingProjectionState.VERIFIED
    assert CodingSessionSandboxDiagnosticCode.VERIFICATION_EVIDENCE_INCOMPATIBLE in {
        item.code for item in missing.diagnostics
    }
    assert factual.state is CodingSessionExecutionBindingProjectionState.VERIFIED
    assert not factual.session_completed


def test_cancellation_and_termination_dimensions_remain_independent() -> None:
    context = _context()
    request = CodingSessionSandboxCompatibilityAdapter.cancellation_request(context)
    observed = CodingSessionSandboxCompatibilityAdapter.project_receipt(
        context,
        _receipt(
            context,
            state=CodingSessionSandboxReceiptState.TERMINATION_OBSERVED,
            termination_observed=True,
        ),
    )
    proved = CodingSessionSandboxCompatibilityAdapter.project_receipt(
        context,
        _receipt(
            context,
            state=CodingSessionSandboxReceiptState.TERMINATION_PROVED,
            termination_observed=True,
            termination_proof_identity="proof:one",
            termination_proof_fingerprint=CodingSessionFingerprint.from_content("proof"),
        ),
    )

    assert request.request is not None
    assert not request.request.termination_inferred
    assert not request.request.termination_proof_inferred
    assert observed.state is CodingSessionExecutionBindingProjectionState.EXITED_UNVERIFIED
    assert not observed.session_cancelled
    assert not proved.session_cancelled


def test_cleanup_incomplete_and_incompatible_proof_remain_explicit() -> None:
    context = _context()
    projection = CodingSessionSandboxCompatibilityAdapter.project_receipt(
        context,
        _receipt(
            context,
            state=CodingSessionSandboxReceiptState.CLEANUP_INCOMPLETE,
            cleanup_complete=False,
            termination_proof_identity="proof:one",
        ),
    )

    codes = {item.code for item in projection.diagnostics}
    assert CodingSessionSandboxDiagnosticCode.CLEANUP_INCOMPLETE in codes
    assert CodingSessionSandboxDiagnosticCode.TERMINATION_EVIDENCE_INCOMPATIBLE in codes
    assert not projection.recovery_completed


def test_plan_attempt_capability_and_binding_mismatch_fail_closed() -> None:
    context = _context()
    projection = CodingSessionSandboxCompatibilityAdapter.project_receipt(
        context,
        _receipt(
            context,
            attempt_id=SandboxAttemptId("attempt:other"),
            requested_capabilities=("network",),
            repository_binding=("repository:other", None, None),
        ),
    )

    codes = {item.code for item in projection.diagnostics}
    assert projection.attempt_reference is None
    assert codes >= {
        CodingSessionSandboxDiagnosticCode.PLAN_ATTEMPT_MISMATCH,
        CodingSessionSandboxDiagnosticCode.CAPABILITY_MISMATCH,
        CodingSessionSandboxDiagnosticCode.BINDING_MISMATCH,
    }


def test_contradiction_lineage_and_late_result_are_explicit() -> None:
    context = _context(CodingSessionLifecycleState.TERMINAL)
    exited = _receipt(context, state=CodingSessionSandboxReceiptState.EXITED)
    failed = _receipt(
        context,
        receipt_identity="receipt:two",
        state=CodingSessionSandboxReceiptState.FAILED,
        causal_revision=2,
        parent_receipt_identity=None,
    )
    result = CodingSessionSandboxCompatibilityAdapter.project_receipt(
        context, failed, known_receipts=(exited,)
    )

    codes = {item.code for item in result.diagnostics}
    assert codes >= {
        CodingSessionSandboxDiagnosticCode.CONTRADICTORY_OUTCOME,
        CodingSessionSandboxDiagnosticCode.LINEAGE_GAP,
        CodingSessionSandboxDiagnosticCode.LATE_RESULT,
    }
    assert not result.reopens_terminal_session


def test_same_canonical_input_is_deterministic() -> None:
    context = _context()
    first = CodingSessionSandboxCompatibilityAdapter.execution_request(context)
    second = CodingSessionSandboxCompatibilityAdapter.execution_request(context)

    assert first == second
