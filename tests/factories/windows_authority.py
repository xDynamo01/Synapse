from __future__ import annotations

from datetime import datetime, timedelta, timezone

from synapse.sandbox import OpaqueReference, SandboxArtifactFingerprint, SandboxWorkspaceId
from synapse.sandbox_drivers import (
    WindowsAuthorityContextV1,
    WindowsExecutionAuthorityGuard,
    WindowsExecutionGrantStatus,
    WindowsExecutionGrantV1,
)


class ValidGrantStore:
    def validate(self, grant: WindowsExecutionGrantV1) -> bool:
        return True


OPERATIONS = tuple(
    sorted(
        {
            "destructive_cleanup",
            "artifact_publication",
            "job_assignment",
            "job_configuration",
            "job_create",
            "mutable_state_write",
            "network_policy_configure",
            "process_create",
            "process_resume",
            "secret_delivery",
            "secret_materialization",
            "process_termination",
            "stdio_setup",
            "workspace_delete_replace",
            "workspace_write",
        }
    )
)


def authority(fencing):
    guard = WindowsExecutionAuthorityGuard(ValidGrantStore(), fencing)

    def context(workspace: SandboxWorkspaceId) -> WindowsAuthorityContextV1:
        grant = WindowsExecutionGrantV1(
            OpaqueReference("grant:test"),
            OpaqueReference("subject:test"),
            OpaqueReference("requester:test"),
            OpaqueReference("workload:test"),
            OpaqueReference("plan:test"),
            OpaqueReference("attempt:test"),
            workspace,
            (),
            (),
            OPERATIONS,
            OpaqueReference("policy:test"),
            1,
            WindowsExecutionGrantStatus.ACTIVE,
            datetime.now(timezone.utc) + timedelta(hours=1),
            SandboxArtifactFingerprint.from_content(("grant", workspace)),
        )
        return WindowsAuthorityContextV1(
            OpaqueReference("session:test"),
            grant.subject_reference,
            grant.requester_reference,
            grant.workload_reference,
            grant.plan_reference,
            grant.attempt_reference,
            workspace,
            grant,
            policy_reference=grant.policy_reference,
        )

    return guard, context


def process_context(command, workspace, grant_reference):
    grant = WindowsExecutionGrantV1(
        grant_reference,
        OpaqueReference("subject:test"),
        OpaqueReference("requester:test"),
        command.workload_reference,
        command.plan_reference,
        command.attempt_reference,
        workspace,
        (),
        (),
        OPERATIONS,
        OpaqueReference("policy:test"),
        1,
        WindowsExecutionGrantStatus.ACTIVE,
        datetime.now(timezone.utc) + timedelta(hours=1),
        SandboxArtifactFingerprint.from_content(("grant", workspace, command.attempt_reference)),
    )
    return WindowsAuthorityContextV1(
        OpaqueReference("session:test"),
        grant.subject_reference,
        grant.requester_reference,
        grant.workload_reference,
        grant.plan_reference,
        grant.attempt_reference,
        workspace,
        grant,
        policy_reference=grant.policy_reference,
    )
