from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest
from tests.factories.windows_authority import ValidGrantStore, authority
from tests.test_windows_process_driver import Authorization, Fencing
from tests.test_windows_process_supervision import SupervisionApi
from tests.test_windows_resource_limits import DriverResourceApi, requirement
from tests.test_windows_secret_materialization import _grant
from tests.test_windows_workspace_driver import _file_fingerprint

from synapse.sandbox import (
    OpaqueReference,
    SandboxFilesystemResource,
    SandboxLogicalPath,
    SandboxLogicalWorkspaceRoot,
    SandboxMaterializationAction,
    SandboxMaterializationCleanupPolicy,
    SandboxMaterializationOperation,
    SandboxMaterializationStepRequest,
    SandboxProcessStdioPolicy,
    SandboxWorkspaceId,
    SandboxWorkspacePreparationRequest,
)
from synapse.sandbox_driver_composition import (
    WindowsCompositionConfig,
    WindowsCompositionDependencies,
    WindowsExecutionProfileV1,
    WindowsIsolationLevel,
    build_windows_sandbox_driver,
)
from synapse.sandbox_drivers import (
    LocalArtifactCustodyConfig,
    LocalArtifactRegistration,
    ResolveWindowsCommandRequest,
    SandboxFencingDecision,
    WindowsArtifactPublicationRequestV1,
    WindowsCommandConfig,
    WindowsDeclaredOutputV1,
    WindowsDriverDurableEventV1,
    WindowsDriverEventType,
    WindowsEntrypointBinding,
    WindowsExecutableClass,
    WindowsJobResourcePolicyV1,
    WindowsNetworkPolicyV1,
    WindowsNetworkProfile,
    WindowsProcessStartOutcome,
    WindowsProcessStartRequest,
    WindowsProcessSupervisor,
    WindowsSecretDeliveryRequest,
)

NETWORK = OpaqueReference("capability:e2e-network")
PUBLICATION = OpaqueReference("capability:e2e-publication")


class E2EApi(DriverResourceApi):
    def __init__(self, fail=None):
        super().__init__()
        self.fail = fail
        self.marker = []
        self.secret_environment = ()

    def create_job(self):
        self.calls.append("create_job")
        return 0 if self.fail == "job" else 10

    def configure_kill_on_close(self, job):
        self.calls.append("configure_kill_on_close")
        return self.fail != "configure"

    def prepare_stdio(self, command, limits):
        return None

    def create_process_suspended(self, command, stdio=None, secret_environment=()):
        self.calls.append("create_suspended")
        self.secret_environment = secret_environment
        if self.fail == "create":
            raise OSError("injected")
        return 20, 30, 1234

    def assign_process(self, job, process):
        self.calls.append("assign")
        return self.fail != "assign"

    def process_in_job(self, process, job):
        self.calls.append("verify")
        return self.fail != "verify"

    def resume_thread(self, thread):
        self.calls.append("resume")
        if self.fail == "resume":
            return False
        self.marker.append("user-code")
        return True

    def terminate_suspended(self, process):
        self.calls.append("terminate")
        return True

    def close_handle(self, handle):
        self.calls.append(f"close:{handle}")
        return True


def _profile():
    return WindowsExecutionProfileV1(
        WindowsIsolationLevel.L1_JOB_CONTAINED,
        WindowsNetworkProfile.UNRESTRICTED_BY_DRIVER_BUT_GOVERNED,
        requires_secret=True,
        requires_publication=True,
        requires_durable_state=True,
    )


def _journey(tmp_path, api):
    workspace = SandboxWorkspaceId("workspace:e2e")
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir(parents=True)
    executable = artifact_root / "fixture.exe"
    executable.write_bytes(b"controlled-executable")
    executable_fp = _file_fingerprint(b"controlled-executable")
    artifact_ref = OpaqueReference("artifact:e2e-executable")
    custody = LocalArtifactCustodyConfig(
        (("inputs", artifact_root),),
        (
            (
                LocalArtifactRegistration(
                    artifact_ref, "inputs", "fixture.exe", OpaqueReference("provenance:e2e")
                )
            ),
        ),
    )
    entrypoint = WindowsEntrypointBinding(
        "fixture",
        WindowsExecutableClass.WORKSPACE_EXECUTABLE,
        OpaqueReference("executable:e2e"),
        SandboxFilesystemResource.INPUT,
        SandboxLogicalPath.parse("fixture.exe", case_sensitive=False),
        executable_fp,
    )
    output_bytes = b"controlled-result"
    declared = WindowsDeclaredOutputV1(
        "result.bin",
        _file_fingerprint(output_bytes),
        OpaqueReference("output-binding:e2e"),
        OpaqueReference("execution:e2e"),
    )
    _, context_factory = authority(Fencing())
    context = context_factory(workspace)
    context = replace(context, grant=replace(context.grant, capabilities=(NETWORK, PUBLICATION)))
    secret_ref = OpaqueReference("secret:e2e")
    from synapse.sandbox_drivers import InMemoryWindowsSecretProvider

    provider = InMemoryWindowsSecretProvider({secret_ref: b"synthetic-e2e-secret"})
    workspace_root = tmp_path / "workspaces"
    runtime_config = WindowsCompositionConfig(
        workspace_root,
        WindowsCommandConfig(workspace_root, (entrypoint,)),
        WindowsCompositionDependencies(
            api,
            Authorization(),
            ValidGrantStore(),
            Fencing([SandboxFencingDecision.VALID] * 100),
            lambda selected: context if selected == workspace else None,
            provider,
        ),
        artifact_custody=custody,
        publication_custody_root=tmp_path / "publication",
        declared_outputs=((workspace, declared),),
        driver_state_path=tmp_path / "driver.sqlite3",
        platform_windows=True,
    )
    runtime = build_windows_sandbox_driver(runtime_config)
    runtime.initialize()
    runtime.workspace.prepare(
        SandboxWorkspacePreparationRequest(
            workspace,
            SandboxLogicalWorkspaceRoot("workspace"),
            SandboxMaterializationCleanupPolicy.AFTER_USE,
        )
    )
    runtime.workspace.apply(
        SandboxMaterializationStepRequest(
            workspace,
            SandboxMaterializationOperation(
                1,
                SandboxMaterializationAction.BIND_READONLY_INPUT,
                SandboxFilesystemResource.INPUT,
                SandboxLogicalPath.parse("fixture.exe", case_sensitive=False),
                artifact_ref,
                executable_fp,
            ),
        )
    )
    command = runtime.command.resolve(
        ResolveWindowsCommandRequest(
            context.plan_reference,
            context.workload_reference,
            context.attempt_reference,
            workspace,
            "fixture",
            (),
            SandboxFilesystemResource.WORKSPACE,
            None,
            (),
            SandboxProcessStdioPolicy.CLOSED,
            SandboxProcessStdioPolicy.DISCARD,
            SandboxProcessStdioPolicy.DISCARD,
            OpaqueReference("occurrence:e2e-command"),
        )
    ).command
    assert command is not None
    secret_grant = replace(
        _grant(command, workspace),
        declaration=replace(_grant(command, workspace).declaration, secret_ref=secret_ref),
        authorization_ref=context.grant.grant_reference,
    )
    request = WindowsProcessStartRequest(
        command,
        context.grant.grant_reference,
        command.command_fingerprint,
        workspace,
        OpaqueReference("driver-attempt:e2e"),
        secret_deliveries=(WindowsSecretDeliveryRequest("E2E_SECRET", secret_grant),),
        resource_policy=WindowsJobResourcePolicyV1((requirement(),)),
        authority_context=context,
        network_policy=WindowsNetworkPolicyV1(
            WindowsNetworkProfile.UNRESTRICTED_BY_DRIVER_BUT_GOVERNED,
            True,
            NETWORK,
            command.workload_reference,
            command.plan_reference,
            command.attempt_reference,
            workspace,
        ),
    )
    return runtime, runtime_config, request, output_bytes, executable


def test_nominal_composed_campaign_reaches_publication_cleanup_and_replay(tmp_path) -> None:
    api = E2EApi()
    runtime, config, request, output_bytes, source_artifact = _journey(tmp_path, api)
    assert runtime.execution_readiness(_profile()).executable
    started = runtime.execute(_profile(), request)
    assert started.outcome is WindowsProcessStartOutcome.STARTED
    assert api.marker == ["user-code"]
    assert api.secret_environment == (("E2E_SECRET", "synthetic-e2e-secret"),)
    assert api.calls.index("verify") < api.calls.index("resume")
    assert api.calls.index("verify_limits") < api.calls.index("create_suspended")

    assert started.managed_process is not None
    supervision_api = SupervisionApi(root_active=False, exit_code=0, process_ids=())
    supervisor = WindowsProcessSupervisor(
        started.managed_process,
        supervision_api,
        Authorization(),
        Fencing(),
        request.workspace_id,
        request.grant_reference,
        request.command,
        request.authority_context,
        started_monotonic=0.0,
        monotonic=lambda: 1.0,
    )
    proof = supervisor.confirm_termination()
    assert proof.proven and proof.proof is not None
    output = config.workspace_root / "workspace-e2e" / "output" / "result.bin"
    output.write_bytes(output_bytes)
    candidate, diagnostics = runtime.publication.inspect(
        execution_reference=OpaqueReference("execution:e2e"),
        attempt_reference=request.authority_context.attempt_reference,
        workspace_id=request.workspace_id,
        declared=config.declared_outputs[0][1],
        occurrence_reference=OpaqueReference("occurrence:e2e-publication"),
    )
    assert candidate is not None and diagnostics == ()
    publication = runtime.publication.publish(
        WindowsArtifactPublicationRequestV1(
            candidate,
            candidate.fingerprint,
            OpaqueReference("publication:e2e"),
            PUBLICATION,
            request.authority_context,
        )
    )
    assert publication.publication_verified and source_artifact.exists()
    cleanup = runtime.cleanup.run(
        request.driver_attempt_reference,
        request.workspace_id,
        (("handle_resources", started.managed_process.close_custody_handles),),
        request.authority_context,
    )
    assert not cleanup.reconciliation_required
    runtime.state_store.append(
        WindowsDriverDurableEventV1(
            OpaqueReference("driver-event:e2e-resumed"),
            request.driver_attempt_reference,
            request.workspace_id,
            1,
            WindowsDriverEventType.PROCESS_RESUMED,
            datetime.now(timezone.utc),
            process_created=True,
            job_created=True,
            job_configured=True,
            containment_verified=True,
            process_resumed=True,
            historical_root_pid=1234,
        )
    )
    runtime.state_store.append(
        WindowsDriverDurableEventV1(
            OpaqueReference("driver-event:e2e-proof"),
            request.driver_attempt_reference,
            request.workspace_id,
            2,
            WindowsDriverEventType.TERMINATION_PROVEN,
            datetime.now(timezone.utc),
            termination_proof_reference=OpaqueReference("termination-proof:e2e"),
        )
    )
    runtime.state_store.append(
        WindowsDriverDurableEventV1(
            OpaqueReference("driver-event:e2e-completed"),
            request.driver_attempt_reference,
            request.workspace_id,
            3,
            WindowsDriverEventType.ATTEMPT_COMPLETED,
            datetime.now(timezone.utc),
            publication_state="published",
            cleanup_state="completed",
        )
    )
    restarted = build_windows_sandbox_driver(config)
    restarted.initialize()
    replay = restarted.replay()
    assert len(replay) == 1 and replay[0].handles_recoverable is False
    assert replay[0].historical_event_count == 3
    assert api.marker == ["user-code"]
    assert not list(tmp_path.rglob("*.publishing"))


@pytest.mark.parametrize("failure", ("job", "configure", "create", "assign", "verify", "resume"))
def test_composed_partial_start_failure_matrix_never_executes_user_code(tmp_path, failure) -> None:
    api = E2EApi(failure)
    runtime, _, request, _, _ = _journey(tmp_path, api)
    result = runtime.execute(_profile(), request)
    assert result.outcome is WindowsProcessStartOutcome.FAILED
    assert api.marker == []
    assert not result.process_started
    assert not list(tmp_path.rglob("*.publishing"))
