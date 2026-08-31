from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta

import pytest

from synapse.sandbox import (
    InvalidMaterialization,
    SandboxArtifactFingerprint,
    SandboxArtifactInspectionResult,
    SandboxCleanupState,
    SandboxMaterializationAction,
    SandboxMaterializationApplicationService,
    SandboxMaterializationCleanupPolicy,
    SandboxMaterializationPlanId,
    SandboxMaterializationPlanService,
    SandboxMaterializationRequest,
    SandboxMaterializationResultOutcome,
    SandboxMaterializationStepOutcome,
    SandboxMaterializationStepResult,
    SandboxMaterializationVerificationOutcome,
    SandboxMaterializedFingerprintResult,
    SandboxPlanId,
    SandboxResourceDimension,
    SandboxResourceLimitService,
    SandboxSecretGrantService,
    SandboxWorkspaceVerificationResult,
    derive_identity,
)
from test_sandbox_capability_grants import pipeline
from test_sandbox_resource_limits import (
    evaluate as resource_evaluate,
)
from test_sandbox_resource_limits import (
    fact as resource_fact,
)
from test_sandbox_resource_limits import (
    limit as resource_limit,
)
from test_sandbox_resource_limits import (
    requested as resource_requested,
)
from test_sandbox_resource_limits import (
    requirement as resource_requirement,
)
from test_sandbox_resource_limits import (
    setup as resource_setup,
)
from test_sandbox_secrets_boundary import (
    evaluate as secret_evaluate,
)
from test_sandbox_secrets_boundary import (
    secret_request,
)
from test_sandbox_secrets_boundary import (
    setup as secret_setup,
)

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


def materialization_request(*, occurred_at=NOW):
    base = pipeline()
    plan = base[4]
    resource_inputs = resource_setup(
        base=base,
        requirements=(
            resource_requirement(
                SandboxResourceDimension.WALL_CLOCK_DURATION,
                hard=30_000,
            ),
        ),
        facts=(
            resource_fact(
                plan,
                SandboxResourceDimension.WALL_CLOCK_DURATION,
                hard=30_000,
            ),
        ),
    )
    resource_grants = resource_evaluate(
        resource_inputs,
        (
            resource_requested(
                resource_limit(
                    SandboxResourceDimension.WALL_CLOCK_DURATION,
                    hard=30_000,
                )
            ),
        ),
    )
    resources = SandboxResourceLimitService.build_specification(resource_grants)
    secret_inputs = secret_setup(base=base)
    assert secret_inputs[2] == resources
    secret_grants = secret_evaluate(
        secret_inputs,
        (secret_request(plan),),
    )
    secrets = SandboxSecretGrantService.build_specification(secret_grants)
    return SandboxMaterializationRequest(
        plan,
        resource_inputs[1],
        resource_inputs[2],
        resource_inputs[3],
        resource_inputs[4],
        resources,
        secrets,
        SandboxMaterializationCleanupPolicy.ON_FAILURE,
        occurred_at,
    )


class Custody:
    def __init__(
        self,
        *,
        outcome=SandboxMaterializationStepOutcome.SUCCEEDED,
        mismatch=False,
        stale=False,
    ):
        self.outcome = outcome
        self.mismatch = mismatch
        self.stale = stale
        self.calls = []

    def inspect(self, request):
        self.calls.append(request)
        observed = (
            SandboxArtifactFingerprint.from_content("substituted")
            if self.mismatch
            else request.expected_fingerprint
        )
        return SandboxArtifactInspectionResult(
            self.outcome,
            observed if self.outcome is SandboxMaterializationStepOutcome.SUCCEEDED else None,
            self.stale,
            ("artifact.safe_diagnostic",)
            if self.outcome is not SandboxMaterializationStepOutcome.SUCCEEDED
            else (),
        )


class Workspace:
    def __init__(self, *, fail_action=None, cleanup_fails=False):
        self.fail_action = fail_action
        self.cleanup_fails = cleanup_fails
        self.calls = []

    def prepare(self, request):
        self.calls.append(("prepare", request))
        return self._result(SandboxMaterializationAction.PREPARE_WORKSPACE)

    def apply(self, request):
        self.calls.append(("apply", request))
        return self._result(request.operation.action)

    def seal(self, request):
        self.calls.append(("seal", request))
        return self._result(SandboxMaterializationAction.SEAL_WORKSPACE)

    def cleanup(self, request):
        self.calls.append(("cleanup", request))
        if self.cleanup_fails:
            return SandboxMaterializationStepResult(
                SandboxMaterializationStepOutcome.FAILED,
                ("cleanup.failed",),
            )
        return SandboxMaterializationStepResult(
            SandboxMaterializationStepOutcome.SUCCEEDED,
            (),
        )

    def _result(self, action):
        if action is self.fail_action:
            return SandboxMaterializationStepResult(
                SandboxMaterializationStepOutcome.FAILED,
                ("workspace.step_failed",),
            )
        return SandboxMaterializationStepResult(
            SandboxMaterializationStepOutcome.SUCCEEDED,
            (),
        )


class Verification:
    def __init__(self, plan, *, stage_mismatch=False, workspace_mismatch=False):
        self.plan = plan
        self.stage_mismatch = stage_mismatch
        self.workspace_mismatch = workspace_mismatch
        self.calls = []
        self.expected = {
            (operation.destination_resource, operation.destination): operation.expected_fingerprint
            for operation in plan.operations
            if operation.destination_resource is not None
            and operation.destination is not None
            and operation.expected_fingerprint is not None
        }

    def refingerprint(self, request):
        self.calls.append(("refingerprint", request))
        fingerprint = self.expected[(request.destination_resource, request.destination)]
        if self.stage_mismatch:
            fingerprint = SandboxArtifactFingerprint.from_content("changed")
        return SandboxMaterializedFingerprintResult(
            SandboxMaterializationStepOutcome.SUCCEEDED,
            fingerprint,
            (),
        )

    def verify(self, request):
        self.calls.append(("verify", request))
        fingerprint = request.expected_workspace_fingerprint
        if self.workspace_mismatch:
            fingerprint = SandboxArtifactFingerprint.from_content("wrong-workspace")
        return SandboxWorkspaceVerificationResult(
            SandboxMaterializationStepOutcome.SUCCEEDED,
            fingerprint,
            (),
        )


def execute(
    request=None,
    *,
    custody=None,
    workspace=None,
    stage_mismatch=False,
    workspace_mismatch=False,
):
    request = request or materialization_request()
    plan = SandboxMaterializationPlanService.build(request)
    selected_custody = custody or Custody()
    selected_workspace = workspace or Workspace()
    verification = Verification(
        plan,
        stage_mismatch=stage_mismatch,
        workspace_mismatch=workspace_mismatch,
    )
    result = SandboxMaterializationApplicationService(
        selected_custody,
        selected_workspace,
        verification,
    ).materialize(request)
    return plan, result, selected_custody, selected_workspace, verification


def test_plan_requires_all_exact_prior_specification_bindings_before_ports() -> None:
    request = materialization_request()
    network_type = type(request.network)
    mismatched_network_content = (
        SandboxPlanId("plan:other"),
        request.network.plan_fingerprint,
        request.network.grant_set_id,
        request.network.grant_set_fingerprint,
        request.network.grants,
        request.network.required_enforcements,
    )
    mismatched_network = network_type(
        *mismatched_network_content,
        SandboxArtifactFingerprint.from_content(mismatched_network_content),
    )
    mismatched = replace(
        request,
        network=mismatched_network,
    )
    custody = Custody()
    workspace = Workspace()
    with pytest.raises(InvalidMaterialization):
        SandboxMaterializationApplicationService(
            custody,
            workspace,
            Verification(SandboxMaterializationPlanService.build(request)),
        ).materialize(mismatched)
    assert custody.calls == []
    assert workspace.calls == []


def test_plan_is_canonical_fingerprint_bound_and_occurrence_independent() -> None:
    request = materialization_request()
    replay = replace(request, occurred_at=NOW + timedelta(hours=1))
    first = SandboxMaterializationPlanService.build(request)
    second = SandboxMaterializationPlanService.build(replay)
    assert first == second
    assert first.materialization_plan_fingerprint == second.materialization_plan_fingerprint
    assert tuple(item.ordinal for item in first.operations) == tuple(
        range(1, len(first.operations) + 1)
    )


def test_duplicate_logical_destination_fails_closed_in_public_plan_artifact() -> None:
    plan = SandboxMaterializationPlanService.build(materialization_request())
    duplicated = (plan.artifact_inputs[0], plan.artifact_inputs[0])
    semantic = (
        plan.format_version,
        plan.plan_id,
        plan.plan_fingerprint,
        plan.capability_grant_set_fingerprint,
        plan.filesystem_specification_fingerprint,
        plan.network_specification_fingerprint,
        plan.process_specification_fingerprint,
        plan.resource_specification_fingerprint,
        plan.secret_specification_fingerprint,
        plan.workspace_id,
        plan.workspace_root,
        plan.artifact_inputs,
        duplicated,
        plan.writable_outputs,
        plan.temporary_areas,
        plan.state_roots,
        plan.runtime_assets,
        plan.operations,
        plan.expected_workspace_fingerprint,
        plan.cleanup_policy,
    )
    fingerprint = SandboxArtifactFingerprint.from_content(semantic)
    identity = derive_identity(SandboxMaterializationPlanId, fingerprint)
    with pytest.raises(
        InvalidMaterialization,
        match="sandbox materialization is structurally invalid",
    ):
        type(plan)(
            plan.format_version,
            SandboxMaterializationPlanId(identity.value),
            fingerprint,
            plan.plan_id,
            plan.plan_fingerprint,
            plan.capability_grant_set_fingerprint,
            plan.filesystem_specification_fingerprint,
            plan.network_specification_fingerprint,
            plan.process_specification_fingerprint,
            plan.resource_specification_fingerprint,
            plan.secret_specification_fingerprint,
            plan.workspace_id,
            plan.workspace_root,
            plan.artifact_inputs,
            duplicated,
            plan.writable_outputs,
            plan.temporary_areas,
            plan.state_roots,
            plan.runtime_assets,
            plan.operations,
            plan.expected_workspace_fingerprint,
            plan.cleanup_policy,
        )


def test_artifact_substitution_fails_before_workspace_preparation() -> None:
    custody = Custody(mismatch=True)
    workspace = Workspace()
    _, result, _, _, _ = execute(custody=custody, workspace=workspace)
    assert result.outcome is SandboxMaterializationResultOutcome.FAILED
    assert result.verification.outcome is SandboxMaterializationVerificationOutcome.MISMATCH
    assert result.record is None
    assert workspace.calls == []


@pytest.mark.parametrize(
    "custody",
    [
        Custody(outcome=SandboxMaterializationStepOutcome.UNAVAILABLE),
        Custody(stale=True),
    ],
)
def test_missing_or_stale_artifact_fails_closed_before_partial_materialization(custody) -> None:
    workspace = Workspace()
    _, result, _, _, _ = execute(custody=custody, workspace=workspace)
    assert result.record is None
    assert workspace.calls == []
    assert result.cleanup_state is SandboxCleanupState.NOT_REQUIRED
    if custody.stale:
        assert result.verification.outcome is SandboxMaterializationVerificationOutcome.STALE


def test_external_diagnostics_are_safe_codes_not_sensitive_references() -> None:
    custody = Custody(outcome=SandboxMaterializationStepOutcome.UNAVAILABLE)
    custody.inspect = lambda request: SandboxArtifactInspectionResult(
        SandboxMaterializationStepOutcome.UNAVAILABLE,
        None,
        False,
        (r"C:\host\secret\artifact.bin?token=private",),
    )
    _, result, _, _, _ = execute(custody=custody)
    assert result.verification.diagnostic_codes == ("artifact.unavailable",)
    assert "token=private" not in repr(result.verification)


def test_post_stage_refingerprint_mismatch_requires_cleanup() -> None:
    _, result, _, workspace, verification = execute(stage_mismatch=True)
    assert result.outcome is SandboxMaterializationResultOutcome.CLEANUP_REQUIRED
    assert result.verification.outcome is SandboxMaterializationVerificationOutcome.CLEANUP_REQUIRED
    assert result.record is None
    assert any(name == "cleanup" for name, _ in workspace.calls)
    assert any(name == "refingerprint" for name, _ in verification.calls)


def test_partial_failure_cleanup_failure_remains_visible_and_unverified() -> None:
    workspace = Workspace(
        fail_action=SandboxMaterializationAction.BIND_RUNTIME_ASSET,
        cleanup_fails=True,
    )
    _, result, _, _, _ = execute(workspace=workspace)
    assert result.outcome is SandboxMaterializationResultOutcome.CLEANUP_REQUIRED
    assert result.verification.outcome is SandboxMaterializationVerificationOutcome.CLEANUP_FAILED
    assert result.cleanup_state is SandboxCleanupState.FAILED
    assert result.record is None


def test_verification_or_seal_failure_never_produces_record() -> None:
    _, mismatch, _, workspace, _ = execute(workspace_mismatch=True)
    assert mismatch.record is None
    assert (
        mismatch.verification.outcome is SandboxMaterializationVerificationOutcome.CLEANUP_REQUIRED
    )
    assert any(name == "cleanup" for name, _ in workspace.calls)

    seal_workspace = Workspace(fail_action=SandboxMaterializationAction.SEAL_WORKSPACE)
    _, seal_failure, _, _, _ = execute(workspace=seal_workspace)
    assert seal_failure.record is None
    assert seal_failure.cleanup_state is SandboxCleanupState.VERIFIED


def test_verified_and_sealed_materialization_produces_replayable_record_only() -> None:
    plan, first, _, _, _ = execute()
    _, replay, _, _, _ = execute(
        replace(materialization_request(), occurred_at=NOW + timedelta(minutes=5))
    )
    assert first.outcome is SandboxMaterializationResultOutcome.SUCCEEDED
    assert first.record is not None
    assert replay.record is not None
    assert first.record.materialization_id == replay.record.materialization_id
    assert first.record.materialization_fingerprint == replay.record.materialization_fingerprint
    assert first.record.occurred_at != replay.record.occurred_at
    assert first.record.verification.outcome is SandboxMaterializationVerificationOutcome.VERIFIED
    assert first.record.materialization_plan_id == plan.materialization_plan_id
    for forbidden in ("authorized", "executable", "materialized_secret"):
        assert not hasattr(first.record, forbidden)


def test_secret_references_are_bound_but_never_materialized() -> None:
    request = materialization_request()
    plan = SandboxMaterializationPlanService.build(request)
    assert request.secrets is not None
    assert plan.secret_specification_fingerprint == request.secrets.specification_fingerprint
    secret_refs = {grant.declaration.secret_ref for grant in request.secrets.leases}
    operation_refs = {operation.source_ref for operation in plan.operations}
    assert secret_refs.isdisjoint(operation_refs)


def test_public_contracts_expose_no_host_path_or_operational_surface() -> None:
    request = materialization_request()
    plan = SandboxMaterializationPlanService.build(request)
    public_fields = {
        field.name
        for contract in (
            type(request),
            type(plan),
            type(plan.operations[0]),
        )
        for field in fields(contract)
    }
    assert not public_fields & {
        "host_path",
        "absolute_path",
        "command",
        "shell",
        "socket",
        "secret_value",
    }
    rendered = repr(plan)
    assert "C:\\" not in rendered
    assert "/home/" not in rendered
    assert plan.workspace_root.value == "workspace"
