from dataclasses import replace

from tests.test_coding_sessions_intents import _intent
from tests.test_coding_sessions_leases import _contract, _issue
from tests.test_repository_runtime_snapshots import identities, profile

from synapse.coding_sessions import (
    CodingSessionArtifactReference,
    CodingSessionBindingScope,
    CodingSessionCheckoutReference,
    CodingSessionIntentCategory,
    CodingSessionLeaseAction,
    CodingSessionLeaseCapability,
    CodingSessionLeaseInterval,
    CodingSessionLeaseMode,
    CodingSessionLifecycleState,
    CodingSessionPlatformContextReference,
    CodingSessionReceiptCompleteness,
    CodingSessionReceiptOutcome,
    CodingSessionRepositoryReference,
    CodingSessionStateProjection,
    CodingSessionTerminalOutcome,
    CodingSessionWorktreeReference,
)
from synapse.coding_sessions_integrations import (
    CodingSessionRepositoryApplicationPayload,
    CodingSessionRepositoryBinding,
    CodingSessionRepositoryCompatibilityAdapter,
    CodingSessionRepositoryCompatibilityDiagnosticCode,
    CodingSessionRepositoryCompatibilityStatus,
    CodingSessionRepositoryObservationPayload,
)
from synapse.repository_runtime import (
    RepositoryCheckoutIdentity,
    RepositoryFingerprint,
    RepositoryIdentity,
    RepositoryMutationApplicationRequest,
    RepositoryObservationRequest,
    RepositoryWorktreeIdentity,
)

NOW = 15


def _facts(*, write: bool = True):
    repository_id, checkout_id, worktree_id = identities()
    exact = CodingSessionRepositoryBinding(
        repository_id, checkout_id, worktree_id, profile()
    )
    contract = _contract(write=write)
    binding = replace(
        contract.binding,
        scope=CodingSessionBindingScope.WORKTREE,
        repository=CodingSessionRepositoryReference.create(
            "repository-runtime", "v1", repository_id.value
        ),
        checkout=CodingSessionCheckoutReference.create(
            "repository-runtime", "v1", checkout_id.value
        ),
        worktree=CodingSessionWorktreeReference.create(
            "repository-runtime", "v1", worktree_id.value
        ),
        platform_context=CodingSessionPlatformContextReference.create(
            "repository-runtime", "v1", exact.fingerprint.value
        ),
    )
    contract = replace(contract, binding=binding)
    lease = _issue(
        contract,
        capability=(
            CodingSessionLeaseCapability.WRITE
            if write
            else CodingSessionLeaseCapability.READ
        ),
        mode=(CodingSessionLeaseMode.EXCLUSIVE if write else CodingSessionLeaseMode.SHARED),
    )
    lifecycle = CodingSessionStateProjection(
        contract.session_identity, lifecycle=CodingSessionLifecycleState.ACTIVE
    )
    return contract, lease, lifecycle, exact


def _fingerprint(key: str) -> RepositoryFingerprint:
    return RepositoryFingerprint.from_content(key)


def test_exact_projection_preserves_binding_lease_and_source_of_truth() -> None:
    contract, lease, lifecycle, binding = _facts()

    result = CodingSessionRepositoryCompatibilityAdapter().project(
        contract, lifecycle, lease, binding, observation_time=NOW
    )

    assert result.status is CodingSessionRepositoryCompatibilityStatus.EXACT
    assert result.contract is not None and result.lease is not None
    assert result.contract.identity.value == contract.session_identity.value
    assert result.lease.lease_reference == lease.lease_identity.value
    assert result.lease.binding.repository_id == binding.repository_id
    assert not hasattr(result.lease, "authorization")
    assert lease.action is CodingSessionLeaseAction.ISSUE


def test_binding_mismatch_and_scope_escalation_fail_closed() -> None:
    contract, lease, lifecycle, binding = _facts()
    other_repository = RepositoryIdentity.from_stable_key("repository-other")
    other_checkout = RepositoryCheckoutIdentity.derive(other_repository, "checkout-other")
    other_worktree = RepositoryWorktreeIdentity.derive(other_checkout, "worktree-other")
    mismatch = replace(
        binding,
        repository_id=other_repository,
        checkout_id=other_checkout,
        worktree_id=other_worktree,
    )
    adapter = CodingSessionRepositoryCompatibilityAdapter()

    binding_result = adapter.project(
        contract, lifecycle, lease, mismatch, observation_time=NOW
    )
    narrowed_lease = replace(
        lease, scope=replace(lease.scope, level=CodingSessionBindingScope.REPOSITORY)
    )
    scope_result = adapter.project(
        contract, lifecycle, narrowed_lease, binding, observation_time=NOW
    )

    assert binding_result.status is CodingSessionRepositoryCompatibilityStatus.REJECTED
    assert scope_result.status is CodingSessionRepositoryCompatibilityStatus.REJECTED
    assert CodingSessionRepositoryCompatibilityDiagnosticCode.BINDING_MISMATCH in {
        item.code for item in binding_result.diagnostics
    }
    assert CodingSessionRepositoryCompatibilityDiagnosticCode.SCOPE_ESCALATION in {
        item.code for item in scope_result.diagnostics
    }


def test_stale_expired_and_revoked_lease_never_satisfy_projection() -> None:
    contract, lease, lifecycle, binding = _facts()
    adapter = CodingSessionRepositoryCompatibilityAdapter()
    variants = (
        replace(lease, action=CodingSessionLeaseAction.MARK_STALE),
        replace(lease, interval=CodingSessionLeaseInterval(1, 1, NOW)),
        replace(lease, action=CodingSessionLeaseAction.REVOKE),
    )

    results = tuple(
        adapter.project(contract, lifecycle, item, binding, observation_time=NOW)
        for item in variants
    )

    assert all(item.status is CodingSessionRepositoryCompatibilityStatus.REJECTED for item in results)
    codes = [{diagnostic.code for diagnostic in item.diagnostics} for item in results]
    assert CodingSessionRepositoryCompatibilityDiagnosticCode.LEASE_STALE in codes[0]
    assert CodingSessionRepositoryCompatibilityDiagnosticCode.LEASE_EXPIRED in codes[1]
    assert CodingSessionRepositoryCompatibilityDiagnosticCode.LEASE_REVOKED in codes[2]


def test_unrepresentable_lifecycle_has_no_silent_fallback() -> None:
    contract, lease, lifecycle, binding = _facts()
    lifecycle = replace(
        lifecycle,
        lifecycle=CodingSessionLifecycleState.TERMINAL,
        terminal_outcome=CodingSessionTerminalOutcome.FAILED,
    )

    result = CodingSessionRepositoryCompatibilityAdapter().project(
        contract, lifecycle, lease, binding, observation_time=NOW
    )

    assert result.lifecycle.status is CodingSessionRepositoryCompatibilityStatus.UNREPRESENTABLE
    assert result.lifecycle.lifecycle is None
    assert result.contract is None


def test_observation_translation_is_neutral_and_does_not_execute() -> None:
    contract, lease, lifecycle, binding = _facts(write=False)
    adapter = CodingSessionRepositoryCompatibilityAdapter()
    projection = adapter.project(contract, lifecycle, lease, binding, observation_time=NOW)
    intent = _intent(
        contract,
        category=CodingSessionIntentCategory.REPOSITORY_OBSERVATION,
        capability=contract.requested_capabilities[0].code,
        write=False,
    )

    result = adapter.translate(
        intent,
        projection,
        CodingSessionRepositoryObservationPayload(),
        observation_time=NOW,
    )

    assert result.status is CodingSessionRepositoryCompatibilityStatus.EXACT
    assert isinstance(result.translated_request, RepositoryObservationRequest)
    assert not result.authorization_granted
    assert not result.operation_executed


def test_application_requires_exact_lease_reference_and_never_authorizes() -> None:
    contract, lease, lifecycle, binding = _facts()
    adapter = CodingSessionRepositoryCompatibilityAdapter()
    projection = adapter.project(contract, lifecycle, lease, binding, observation_time=NOW)
    payload = CodingSessionRepositoryApplicationPayload(
        _fingerprint("base"),
        _fingerprint("plan"),
        _fingerprint("authorization"),
        _fingerprint("restore"),
        "attempt:compatibility",
    )
    missing_lease = _intent(contract, lease_reference=None)
    exact = _intent(contract, lease_reference=lease.lease_identity)

    rejected = adapter.translate(missing_lease, projection, payload, observation_time=NOW)
    accepted = adapter.translate(exact, projection, payload, observation_time=NOW)

    assert rejected.status is CodingSessionRepositoryCompatibilityStatus.REJECTED
    assert isinstance(accepted.translated_request, RepositoryMutationApplicationRequest)
    assert not accepted.authorization_granted
    assert not accepted.operation_executed


def test_repository_receipt_never_implies_session_state() -> None:
    contract, lease, lifecycle, binding = _facts()
    adapter = CodingSessionRepositoryCompatibilityAdapter()
    projection = adapter.project(contract, lifecycle, lease, binding, observation_time=NOW)
    assert projection.contract is not None
    intent = _intent(contract, lease_reference=lease.lease_identity)
    reference = CodingSessionArtifactReference.create(
        "repository-runtime", "v1", "application-result", None
    )

    receipt = adapter.project_receipt(
        intent,
        reference,
        outcome=CodingSessionReceiptOutcome.SUCCEEDED,
        completeness=CodingSessionReceiptCompleteness.COMPLETE,
    )

    assert receipt.status is CodingSessionRepositoryCompatibilityStatus.EXACT
    assert not receipt.session_completed
    assert not receipt.repository_correspondence_inferred
    assert not receipt.recovery_completed
    assert not receipt.lifecycle_transitioned
