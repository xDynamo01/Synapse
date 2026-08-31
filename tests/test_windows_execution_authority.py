from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from inspect import signature

import pytest
from tests.factories.windows_authority import ValidGrantStore, authority, process_context
from tests.test_windows_process_driver import Authorization, FakeApi, Fencing, _request, _resolved
from tests.test_windows_process_supervision import SupervisionApi
from tests.test_windows_workspace_driver import _file_fingerprint, _operation, _prepare

from synapse.sandbox import (
    OpaqueReference,
    SandboxArtifactFingerprint,
    SandboxFilesystemResource,
    SandboxLogicalPath,
    SandboxMaterializationStepOutcome,
    SandboxProcessStdioPolicy,
    SandboxWorkspaceCleanupRequest,
    SandboxWorkspaceId,
)
from synapse.sandbox_drivers import (
    ResolveWindowsCommandRequest,
    SandboxFencingDecision,
    WindowsAuthorityDecision,
    WindowsCommandConfig,
    WindowsCommandResolver,
    WindowsEntrypointBinding,
    WindowsExecutableClass,
    WindowsExecutionAuthorityGuard,
    WindowsExecutionGrantStatus,
    WindowsProcessDriver,
    WindowsProcessStartOutcome,
    WindowsProcessSupervisor,
    WindowsWorkspaceConfig,
    WindowsWorkspaceDriver,
)


class InvalidGrantStore:
    def validate(self, grant) -> bool:
        return False


class Precondition:
    def __init__(self, valid: bool) -> None:
        self.valid = valid

    def validate(self, context, operation, expected) -> bool:
        return self.valid


def _context(tmp_path):
    workspace, _, command = _resolved(tmp_path)
    return workspace, command, process_context(
        command, workspace, OpaqueReference("grant:one")
    )


def test_valid_grant_and_current_fencing_succeed(tmp_path) -> None:
    workspace, _, context = _context(tmp_path)
    check = WindowsExecutionAuthorityGuard(ValidGrantStore(), Fencing()).authorize(
        context, workspace, "process_create"
    )
    assert check.allowed and check.decision is WindowsAuthorityDecision.ALLOWED
    applied = WindowsExecutionAuthorityGuard.applied(check)
    assert applied.authorization_validated and applied.fencing_validated
    assert applied.effect_attempted and applied.effect_applied and not applied.effect_blocked


@pytest.mark.parametrize(
    ("context_change", "guard", "expected"),
    [
        (lambda context: None, lambda: WindowsExecutionAuthorityGuard(ValidGrantStore(), Fencing()), WindowsAuthorityDecision.GRANT_MISSING),
        (lambda context: context, lambda: WindowsExecutionAuthorityGuard(InvalidGrantStore(), Fencing()), WindowsAuthorityDecision.GRANT_INVALID),
        (
            lambda context: replace(
                context,
                grant=replace(context.grant, status=WindowsExecutionGrantStatus.REVOKED),
            ),
            lambda: WindowsExecutionAuthorityGuard(ValidGrantStore(), Fencing()),
            WindowsAuthorityDecision.GRANT_STALE,
        ),
        (
            lambda context: replace(context, required_capabilities=(OpaqueReference("capability:missing"),)),
            lambda: WindowsExecutionAuthorityGuard(ValidGrantStore(), Fencing()),
            WindowsAuthorityDecision.CAPABILITY_MISMATCH,
        ),
        (
            lambda context: replace(context, attempt_reference=OpaqueReference("attempt:wrong")),
            lambda: WindowsExecutionAuthorityGuard(ValidGrantStore(), Fencing()),
            WindowsAuthorityDecision.SCOPE_MISMATCH,
        ),
        (
            lambda context: context,
            lambda: WindowsExecutionAuthorityGuard(ValidGrantStore(), Fencing([SandboxFencingDecision.STALE])),
            WindowsAuthorityDecision.FENCING_STALE,
        ),
        (
            lambda context: context,
            lambda: WindowsExecutionAuthorityGuard(ValidGrantStore(), Fencing([SandboxFencingDecision.UNAVAILABLE])),
            WindowsAuthorityDecision.FENCING_UNAVAILABLE,
        ),
        (
            lambda context: context,
            lambda: WindowsExecutionAuthorityGuard(ValidGrantStore(), Fencing([SandboxFencingDecision.INVALID])),
            WindowsAuthorityDecision.FENCING_MISMATCHED,
        ),
        (
            lambda context: context,
            lambda: WindowsExecutionAuthorityGuard(ValidGrantStore(), None),
            WindowsAuthorityDecision.FENCING_MISSING,
        ),
        (
            lambda context: context,
            lambda: WindowsExecutionAuthorityGuard(None, Fencing()),
            WindowsAuthorityDecision.AUTHORITY_UNAVAILABLE,
        ),
    ],
)
def test_invalid_authority_paths_block_before_effect(tmp_path, context_change, guard, expected) -> None:
    workspace, _, context = _context(tmp_path)
    check = guard().authorize(context_change(context), workspace, "process_create")
    assert not check.allowed and check.decision is expected
    assert check.audit.effect_blocked and not check.audit.effect_attempted
    assert not check.audit.effect_applied


def test_expiry_is_revalidated_at_each_mutation(tmp_path) -> None:
    workspace, _, context = _context(tmp_path)
    current = [datetime.now(timezone.utc)]
    guard = WindowsExecutionAuthorityGuard(
        ValidGrantStore(), Fencing(), now=lambda: current[0]
    )
    assert guard.authorize(context, workspace, "process_create").allowed
    current[0] = context.grant.expires_at + timedelta(microseconds=1)
    check = guard.authorize(context, workspace, "process_resume")
    assert check.decision is WindowsAuthorityDecision.GRANT_STALE


def test_precondition_is_distinct_from_current_ownership(tmp_path) -> None:
    workspace, _, context = _context(tmp_path)
    context = replace(context, expected_precondition=context.grant.grant_fingerprint)
    unavailable = WindowsExecutionAuthorityGuard(ValidGrantStore(), Fencing()).authorize(
        context, workspace, "workspace_delete_replace"
    )
    stale = WindowsExecutionAuthorityGuard(
        ValidGrantStore(), Fencing(), preconditions=Precondition(False)
    ).authorize(context, workspace, "workspace_delete_replace")
    assert unavailable.decision is WindowsAuthorityDecision.AUTHORITY_UNAVAILABLE
    assert stale.decision is WindowsAuthorityDecision.PRECONDITION_STALE


def test_same_idempotency_reference_does_not_bypass_stale_fencing(tmp_path) -> None:
    workspace, _, context = _context(tmp_path)
    context = replace(context, idempotency_reference=OpaqueReference("request:same"))
    guard = WindowsExecutionAuthorityGuard(
        ValidGrantStore(), Fencing([SandboxFencingDecision.VALID, SandboxFencingDecision.STALE])
    )
    assert guard.authorize(context, workspace, "workspace_write").allowed
    second = guard.authorize(context, workspace, "workspace_write")
    assert second.decision is WindowsAuthorityDecision.FENCING_STALE


def test_process_creation_has_literal_zero_effect_when_generation_transfers(tmp_path) -> None:
    workspace, _, command = _resolved(tmp_path)
    api = FakeApi()
    request = _request(workspace, command)
    result = WindowsProcessDriver(
        api,
        Authorization(),
        Fencing([SandboxFencingDecision.VALID] * 4 + [SandboxFencingDecision.STALE]),
        platform_available=True,
    ).start(request)
    assert result.outcome is WindowsProcessStartOutcome.FAILED
    assert result.diagnostic_codes == ("fencing_stale",)
    assert "create_suspended" not in api.calls and "resume" not in api.calls


def test_no_guard_or_context_is_not_a_permissive_workspace_fallback(tmp_path) -> None:
    parameters = signature(WindowsWorkspaceDriver).parameters
    assert parameters["authority"].default is parameters["authority_context"].default
    assert str(parameters["authority"].default) == "<class 'inspect._empty'>"


def test_workspace_health_scopes_claim_to_sandbox_not_repository(tmp_path) -> None:
    guard, context = authority(Fencing())
    driver = WindowsWorkspaceDriver(
        WindowsWorkspaceConfig(tmp_path / "root"), guard, context
    )
    health = driver.health()
    assert health.sandbox_end_to_end_fencing_enforced
    assert not health.repository_end_to_end_fencing_enforced


def test_controlled_end_to_end_authority_journey(tmp_path) -> None:
    workspace = SandboxWorkspaceId("workspace:e2e-authority")
    source = tmp_path / "fixture.exe"
    source.write_bytes(b"controlled-e2e")
    artifact = OpaqueReference("artifact:e2e")
    fingerprint = _file_fingerprint(b"controlled-e2e")
    workspace_fencing = Fencing([SandboxFencingDecision.VALID] * 100)
    guard, context_for = authority(workspace_fencing)
    workspace_driver = WindowsWorkspaceDriver(
        WindowsWorkspaceConfig(tmp_path / "workspaces", ((artifact, source),)),
        guard,
        context_for,
    )
    assert _prepare(workspace_driver, workspace).outcome is SandboxMaterializationStepOutcome.SUCCEEDED
    assert workspace_driver.apply(
        _operation(workspace, artifact, fingerprint, "fixture.exe")
    ).outcome is SandboxMaterializationStepOutcome.SUCCEEDED

    binding = WindowsEntrypointBinding(
        "fixture",
        WindowsExecutableClass.WORKSPACE_EXECUTABLE,
        OpaqueReference("executable:e2e"),
        SandboxFilesystemResource.INPUT,
        SandboxLogicalPath.parse("fixture.exe", case_sensitive=False),
        fingerprint,
    )
    command = WindowsCommandResolver(
        WindowsCommandConfig(tmp_path / "workspaces", (binding,))
    ).resolve(
        ResolveWindowsCommandRequest(
            OpaqueReference("plan:e2e"),
            OpaqueReference("workload:e2e"),
            OpaqueReference("attempt:e2e"),
            workspace,
            "fixture",
            (),
            SandboxFilesystemResource.WORKSPACE,
            None,
            (),
            SandboxProcessStdioPolicy.CLOSED,
            SandboxProcessStdioPolicy.DISCARD,
            SandboxProcessStdioPolicy.DISCARD,
            OpaqueReference("occurrence:e2e"),
        )
    ).command
    assert command is not None
    process_fencing = Fencing()
    request = _request(workspace, command)
    started = WindowsProcessDriver(
        FakeApi(), Authorization(), process_fencing, platform_available=True
    ).start(request)
    assert started.outcome is WindowsProcessStartOutcome.STARTED
    assert started.managed_process is not None

    supervision_api = SupervisionApi()
    supervisor = WindowsProcessSupervisor(
        started.managed_process,
        supervision_api,
        Authorization(),
        Fencing(),
        workspace,
        request.grant_reference,
        command,
        request.authority_context,
        started_monotonic=0.0,
        monotonic=lambda: 1.0,
    )
    assert supervisor.observe().observation_available
    assert supervisor.request_termination().termination_requested
    supervision_api.root_active = False
    supervision_api.exit_code = 1
    supervision_api.process_ids = ()
    assert supervisor.confirm_termination().proven
    assert workspace_driver.cleanup(
        SandboxWorkspaceCleanupRequest(
            workspace, SandboxArtifactFingerprint.from_content("plan:e2e")
        )
    ).outcome is SandboxMaterializationStepOutcome.SUCCEEDED
