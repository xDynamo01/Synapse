from __future__ import annotations

import json
from dataclasses import replace

from synapse.deployment import (
    AuthorizationReference,
    CapabilityReference,
    DeploymentFencingAuthority,
    DeploymentFencingTransitionRequestV1,
    DeploymentFingerprint,
    DeploymentIdempotencyKey,
    DeploymentIdempotencyRequestV1,
    DeploymentLifecycleState,
    DeploymentMachineKey,
    DeploymentMachineKind,
    DeploymentMutationClass,
    LocalApplyFailure,
    LocalApplyOutcome,
    LocalApplyRequestV1,
    LocalRevisionPreparationOutcome,
    OccurrenceReference,
    RequesterReference,
    SandboxLocalApplyCommandV1,
    SandboxLocalApplyOutcome,
    SandboxLocalApplyResultV1,
    local_apply_semantic_fingerprint,
)
from synapse.deployment_adapters import (
    DeploymentSQLiteConfig,
    LocalActiveStateAdapter,
    LocalActiveStateConfigV1,
    SQLiteDeploymentAuthorityStore,
    SQLiteDeploymentJournalStore,
)
from synapse.deployment_integrations import (
    DeploymentWindowsProcessApplyAdapter,
    DeploymentWindowsProcessBindingV1,
    LocalApplyOrchestrator,
)
from synapse.sandbox_drivers import WindowsProcessDriver
from test_deployment_local_service_adapter import _setup
from test_windows_process_driver import (
    Authorization as SandboxAuthorization,
)
from test_windows_process_driver import (
    FakeApi,
    _resolved,
)
from test_windows_process_driver import (
    Fencing as SandboxFencing,
)
from test_windows_process_driver import (
    _request as _process_request,
)


class _CurrentAuthorization:
    def __init__(self, values: tuple[bool, ...] = (True,)) -> None:
        self._values = values
        self.calls = 0

    def validate(self, request: LocalApplyRequestV1) -> bool:
        index = min(self.calls, len(self._values) - 1)
        self.calls += 1
        return self._values[index]


class _Sandbox:
    def __init__(
        self,
        outcome: SandboxLocalApplyOutcome = SandboxLocalApplyOutcome.STARTED,
        *,
        process_started: bool = True,
        diagnostic_codes: tuple[str, ...] = (),
    ) -> None:
        self.outcome = outcome
        self.process_started = process_started
        self.diagnostic_codes = diagnostic_codes
        self.calls = 0

    def start(self, command: SandboxLocalApplyCommandV1) -> SandboxLocalApplyResultV1:
        self.calls += 1
        assert command.sandbox_fencing_reference.value.startswith("sandbox-fencing:")
        assert command.deployment_fencing_reference.value.startswith("sha256:")
        assert command.sandbox_fencing_reference.value != command.deployment_fencing_reference.value
        return SandboxLocalApplyResultV1(
            self.outcome,
            CapabilityReference("sandbox-execution:local-service")
            if self.process_started
            else None,
            self.process_started,
            self.process_started,
            self.diagnostic_codes,
        )


def _apply_setup(tmp_path, *, authorization=None, sandbox=None):
    preparation_adapter, preparation_request, _, _ = _setup(tmp_path)
    preparation = preparation_adapter.prepare(preparation_request)
    sandbox_authority = CapabilityReference("sandbox-authority:local-service")
    sandbox_fencing = CapabilityReference("sandbox-fencing:generation-1")
    semantic = local_apply_semantic_fingerprint(
        preparation_request, preparation, sandbox_authority, sandbox_fencing
    )
    sqlite = DeploymentSQLiteConfig((tmp_path / "deployment.sqlite3").resolve())
    authority_store = SQLiteDeploymentAuthorityStore(sqlite)
    authority_store.initialize()
    fencing = DeploymentFencingAuthority(authority_store)
    previous = preparation_request.fencing_token
    assert previous is not None
    token = fencing.transition(
        DeploymentFencingTransitionRequestV1(
            preparation_request.idempotency.scope,
            preparation_request.authorization.requester,
            preparation_request.fencing_authority,
            previous.generation.value,
            OccurrenceReference("occurrence:apply-fencing"),
            semantic,
        )
    )
    idempotency = DeploymentIdempotencyRequestV1(
        DeploymentMutationClass.APPLY_REQUEST,
        preparation_request.idempotency.scope,
        DeploymentIdempotencyKey("deployment-idempotency:local-apply"),
        semantic,
        OccurrenceReference("occurrence:apply-idempotency"),
    )
    request = LocalApplyRequestV1(
        preparation_request,
        preparation,
        AuthorizationReference("authorization:local-apply"),
        semantic,
        token,
        idempotency,
        preparation_request.fencing_authority,
        sandbox_authority,
        sandbox_fencing,
        True,
        OccurrenceReference("occurrence:local-apply"),
    )
    current = authorization or _CurrentAuthorization()
    sandbox_port = sandbox or _Sandbox()
    active = LocalActiveStateAdapter(
        LocalActiveStateConfigV1((tmp_path / "deployment-root/active-state").resolve())
    )
    journal = SQLiteDeploymentJournalStore(sqlite)
    orchestrator = LocalApplyOrchestrator(fencing, current, sandbox_port, active, journal)
    return orchestrator, request, fencing, current, sandbox_port, active, journal


def test_nominal_apply_activates_revision_starts_sandbox_and_emits_unverified_receipt(
    tmp_path,
) -> None:
    orchestrator, request, _, _, sandbox, _, journal = _apply_setup(tmp_path)
    result = orchestrator.apply(request)
    assert result.outcome is LocalApplyOutcome.APPLIED
    assert result.receipt is not None
    assert not result.receipt.verified
    assert not result.verified
    assert sandbox.calls == 1
    active = json.loads(
        (tmp_path / "deployment-root/active-state/active.json").read_text(encoding="utf-8")
    )
    assert (
        active["desired_revision"]
        == request.preparation_request.correspondence.desired_revision.desired_revision.revision_id.value
    )
    assert journal.health().store_available
    machine = DeploymentMachineKey(
        DeploymentMachineKind.DEPLOYMENT,
        request.preparation_request.correspondence.attempt.attempt_id.value,
    )
    states = [record.event.resulting_state for record in journal.history(machine)]
    assert states[-2:] == [DeploymentLifecycleState.APPLYING, DeploymentLifecycleState.APPLIED]
    assert DeploymentLifecycleState.VERIFIED not in states


def test_apply_requires_current_prepared_revision_authorization_and_fencing(tmp_path) -> None:
    orchestrator, request, fencing, _, sandbox, _, _ = _apply_setup(tmp_path)
    missing = replace(
        request,
        preparation_result=replace(
            request.preparation_result,
            outcome=LocalRevisionPreparationOutcome.BLOCKED,
        ),
    )
    assert orchestrator.apply(missing).failure is LocalApplyFailure.PREPARED_REVISION_REQUIRED
    invalid_auth = replace(
        request, authorization_semantic_fingerprint=request.preparation_request.semantic_fingerprint
    )
    assert orchestrator.apply(invalid_auth).failure is LocalApplyFailure.AUTHORIZATION_INVALID
    token = request.deployment_fencing_token
    assert token is not None
    fencing.transition(
        DeploymentFencingTransitionRequestV1(
            request.idempotency.scope,
            RequesterReference("subject:transferred"),
            request.deployment_fencing_authority,
            token.generation.value,
            OccurrenceReference("occurrence:apply-transfer"),
            request.semantic_fingerprint,
        )
    )
    assert orchestrator.apply(request).failure is LocalApplyFailure.DEPLOYMENT_FENCING_INVALID
    assert sandbox.calls == 0
    assert not (tmp_path / "deployment-root/active-state").exists()


def test_target_readiness_and_stale_preparation_block_before_effect(tmp_path) -> None:
    orchestrator, request, _, _, sandbox, _, _ = _apply_setup(tmp_path)
    not_ready = replace(request, target_ready=False)
    assert orchestrator.apply(not_ready).failure is LocalApplyFailure.TARGET_NOT_READY
    stale = replace(
        request,
        preparation_result=replace(
            request.preparation_result,
            outcome=LocalRevisionPreparationOutcome.BLOCKED,
        ),
    )
    assert orchestrator.apply(stale).failure is LocalApplyFailure.PREPARED_REVISION_REQUIRED
    assert sandbox.calls == 0
    assert not (tmp_path / "deployment-root/active-state").exists()


def test_invalid_sandbox_authority_and_start_failure_do_not_activate(tmp_path) -> None:
    sandbox = _Sandbox(
        SandboxLocalApplyOutcome.FAILED,
        process_started=False,
        diagnostic_codes=("sandbox-authority-invalid",),
    )
    orchestrator, request, _, _, _, _, _ = _apply_setup(tmp_path, sandbox=sandbox)
    result = orchestrator.apply(request)
    assert result.failure is LocalApplyFailure.SANDBOX_AUTHORITY_INVALID
    assert not (tmp_path / "deployment-root/active-state/active.json").exists()


def test_generic_sandbox_start_failure_is_failed_not_verified(tmp_path) -> None:
    sandbox = _Sandbox(
        SandboxLocalApplyOutcome.FAILED,
        process_started=False,
        diagnostic_codes=("process-creation-failed",),
    )
    orchestrator, request, _, _, _, _, _ = _apply_setup(tmp_path, sandbox=sandbox)
    result = orchestrator.apply(request)
    assert result.outcome is LocalApplyOutcome.FAILED
    assert result.failure is LocalApplyFailure.SANDBOX_START_FAILED
    assert result.receipt is None and not result.verified


def test_repeated_apply_returns_durable_receipt_without_redeploy(tmp_path) -> None:
    orchestrator, request, fencing, _, sandbox, active, journal = _apply_setup(tmp_path)
    first = orchestrator.apply(request)
    second = LocalApplyOrchestrator(
        fencing, _CurrentAuthorization((False,)), sandbox, active, journal
    ).apply(request)
    assert second.outcome is LocalApplyOutcome.APPLIED
    assert second.receipt == first.receipt
    assert sandbox.calls == 1


def test_sandbox_partial_and_unknown_are_factual_and_never_auto_retry(tmp_path) -> None:
    sandbox = _Sandbox(SandboxLocalApplyOutcome.UNKNOWN, process_started=True)
    orchestrator, request, fencing, _, _, active, journal = _apply_setup(tmp_path, sandbox=sandbox)
    first = orchestrator.apply(request)
    restarted = LocalApplyOrchestrator(
        fencing, _CurrentAuthorization(), sandbox, active, journal
    ).apply(request)
    assert first.outcome is LocalApplyOutcome.OUTCOME_UNKNOWN
    assert first.reconciliation_required
    assert restarted.outcome is LocalApplyOutcome.OUTCOME_UNKNOWN
    assert sandbox.calls == 1


def test_authorization_invalidated_before_sandbox_start_stops_next_effect(tmp_path) -> None:
    authorization = _CurrentAuthorization((True, True, False))
    orchestrator, request, _, _, sandbox, _, _ = _apply_setup(tmp_path, authorization=authorization)
    result = orchestrator.apply(request)
    assert result.failure is LocalApplyFailure.AUTHORIZATION_INVALID
    assert sandbox.calls == 0
    assert not (tmp_path / "deployment-root/active-state/active.json").exists()


def test_fencing_transfer_before_final_promotion_yields_partial_and_preserves_previous(
    tmp_path,
) -> None:
    orchestrator, request, fencing, authorization, sandbox, active, journal = _apply_setup(tmp_path)
    token = request.deployment_fencing_token
    assert token is not None

    class TransferOnStart(_Sandbox):
        def start(self, command: SandboxLocalApplyCommandV1) -> SandboxLocalApplyResultV1:
            result = super().start(command)
            fencing.transition(
                DeploymentFencingTransitionRequestV1(
                    request.idempotency.scope,
                    RequesterReference("subject:new-owner"),
                    request.deployment_fencing_authority,
                    token.generation.value,
                    OccurrenceReference("occurrence:transfer-before-promotion"),
                    request.semantic_fingerprint,
                )
            )
            return result

    transfer = TransferOnStart()
    result = LocalApplyOrchestrator(fencing, authorization, transfer, active, journal).apply(
        request
    )
    assert result.outcome is LocalApplyOutcome.PARTIALLY_APPLIED
    assert result.failure is LocalApplyFailure.DEPLOYMENT_FENCING_INVALID
    assert transfer.calls == 1
    assert not (tmp_path / "deployment-root/active-state/active.json").exists()
    assert not hasattr(orchestrator, "repository")


def test_fencing_transfer_before_active_state_mutation_has_zero_local_mutation(tmp_path) -> None:
    _, request, fencing, _, sandbox, active, journal = _apply_setup(tmp_path)
    token = request.deployment_fencing_token
    assert token is not None

    class TransferBeforeMutation(_CurrentAuthorization):
        def validate(self, candidate: LocalApplyRequestV1) -> bool:
            valid = super().validate(candidate)
            if self.calls == 2:
                fencing.transition(
                    DeploymentFencingTransitionRequestV1(
                        request.idempotency.scope,
                        RequesterReference("subject:before-mutation"),
                        request.deployment_fencing_authority,
                        token.generation.value,
                        OccurrenceReference("occurrence:transfer-before-mutation"),
                        request.semantic_fingerprint,
                    )
                )
            return valid

    result = LocalApplyOrchestrator(
        fencing, TransferBeforeMutation(), sandbox, active, journal
    ).apply(request)
    assert result.failure is LocalApplyFailure.DEPLOYMENT_FENCING_INVALID
    assert sandbox.calls == 0
    assert not (tmp_path / "deployment-root/active-state").exists()


def test_contradictory_same_idempotency_key_is_rejected(tmp_path) -> None:
    orchestrator, request, fencing, _, _, active, journal = _apply_setup(tmp_path)
    assert orchestrator.apply(request).outcome is LocalApplyOutcome.APPLIED
    changed = CapabilityReference("sandbox-fencing:generation-2")
    semantic = local_apply_semantic_fingerprint(
        request.preparation_request,
        request.preparation_result,
        request.sandbox_authorization_reference,
        changed,
    )
    token = request.deployment_fencing_token
    assert token is not None
    next_token = fencing.transition(
        DeploymentFencingTransitionRequestV1(
            request.idempotency.scope,
            request.preparation_request.authorization.requester,
            request.deployment_fencing_authority,
            token.generation.value,
            OccurrenceReference("occurrence:contradictory-apply"),
            semantic,
        )
    )
    contradictory = replace(
        request,
        authorization_semantic_fingerprint=semantic,
        deployment_fencing_token=next_token,
        idempotency=replace(request.idempotency, semantic_fingerprint=semantic),
        sandbox_fencing_reference=changed,
    )
    result = LocalApplyOrchestrator(
        fencing, _CurrentAuthorization(), _Sandbox(), active, journal
    ).apply(contradictory)
    assert result.failure is LocalApplyFailure.IDEMPOTENCY_CONTRADICTION


def test_previous_active_revision_is_preserved_for_future_rollback_evidence(tmp_path) -> None:
    root = tmp_path / "deployment-root/active-state"
    root.mkdir(parents=True)
    (root / "active.json").write_text(
        json.dumps(
            {
                "desired_revision": "deployment-revision:previous",
                "mutation_reference": "active-state-mutation:previous",
                "prepared_revision_reference": "prepared-revision:previous",
                "previous_active_revision": None,
                "semantic_fingerprint": "sha256:" + "0" * 64,
            }
        ),
        encoding="utf-8",
    )
    orchestrator, request, _, _, _, _, _ = _apply_setup(tmp_path)
    result = orchestrator.apply(request)
    assert result.receipt is not None
    assert result.receipt.previous_active_revision is not None
    assert result.receipt.previous_active_revision.value == "deployment-revision:previous"
    assert list((root / "history").glob("*.json"))


def test_restart_during_applying_reconciles_and_replay_does_not_redeploy(tmp_path) -> None:
    orchestrator, request, fencing, _, sandbox, active, journal = _apply_setup(tmp_path)
    active.stage(request)
    restarted = LocalApplyOrchestrator(
        fencing, _CurrentAuthorization(), sandbox, active, journal
    ).apply(request)
    assert restarted.outcome is LocalApplyOutcome.OUTCOME_UNKNOWN
    assert restarted.reconciliation_required
    assert sandbox.calls == 0


def test_controlled_concrete_windows_driver_handoff_starts_only_after_containment(tmp_path) -> None:
    workspace, _, resolved = _resolved(tmp_path)
    process_request = _process_request(workspace, resolved)
    api = FakeApi()
    driver = WindowsProcessDriver(
        api,
        SandboxAuthorization(),
        SandboxFencing(),
        platform_available=True,
    )
    sandbox_fencing = CapabilityReference("sandbox-fencing:concrete-1")
    bridge = DeploymentWindowsProcessApplyAdapter(
        driver,
        (
            DeploymentWindowsProcessBindingV1(
                CapabilityReference(workspace.value),
                sandbox_fencing,
                process_request,
            ),
        ),
    )
    result = bridge.start(
        SandboxLocalApplyCommandV1(
            CapabilityReference("prepared-revision:concrete"),
            CapabilityReference(workspace.value),
            CapabilityReference("command-entrypoint:fixture"),
            CapabilityReference(process_request.grant_reference.value),
            sandbox_fencing,
            AuthorizationReference("authorization:deployment-apply"),
            DeploymentFingerprint("sha256:" + "f" * 64),
            OccurrenceReference("occurrence:concrete-apply"),
        )
    )
    assert result.outcome is SandboxLocalApplyOutcome.STARTED
    assert result.containment_established and result.process_started
    assert api.calls.index("verify") < api.calls.index("resume")
    assert api.marker == ["user-code"]
