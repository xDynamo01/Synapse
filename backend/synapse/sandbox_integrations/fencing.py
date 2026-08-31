"""Consumer-owned bridge from Coding Sessions fencing into workspace effects."""

from __future__ import annotations

from dataclasses import dataclass

from synapse.coding_sessions import (
    CodingSessionFingerprint,
    CodingSessionLeaseFactIdentity,
    FencingAuthority,
    FencingOperationClass,
    FencingScope,
    FencingTokenV1,
    FencingValidationState,
)
from synapse.sandbox import SandboxWorkspaceId
from synapse.sandbox_drivers import SandboxFencingDecision


@dataclass(frozen=True, slots=True)
class CodingSessionsWorkspaceFencingValidator:
    authority: FencingAuthority
    token: FencingTokenV1 | None
    scope: FencingScope
    ownership_identity: CodingSessionLeaseFactIdentity | None
    authority_identity: str
    binding_fingerprint: CodingSessionFingerprint | None = None

    def validate(
        self, workspace_id: SandboxWorkspaceId, operation: str
    ) -> SandboxFencingDecision:
        if self.scope.workspace_reference != workspace_id.value:
            return SandboxFencingDecision.INVALID
        operation_class = {
            "destructive_cleanup": FencingOperationClass.DESTRUCTIVE_CLEANUP,
            "workspace_delete_replace": FencingOperationClass.WORKSPACE_DELETE_REPLACE,
            "mutable_state_write": FencingOperationClass.MUTABLE_RESULT_STATE_PUBLICATION,
        }.get(operation, FencingOperationClass.WORKSPACE_WRITE)
        result = self.authority.validate(
            self.token,
            scope=self.scope,
            ownership_identity=self.ownership_identity,
            authority_identity=self.authority_identity,
            operation=operation_class,
            binding_fingerprint=self.binding_fingerprint,
        )
        return {
            FencingValidationState.VALID: SandboxFencingDecision.VALID,
            FencingValidationState.STALE: SandboxFencingDecision.STALE,
            FencingValidationState.UNAVAILABLE: SandboxFencingDecision.UNAVAILABLE,
            FencingValidationState.MISMATCHED: SandboxFencingDecision.INVALID,
            FencingValidationState.INVALID: SandboxFencingDecision.INVALID,
        }[result.state]
