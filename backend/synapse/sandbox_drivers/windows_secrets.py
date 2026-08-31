"""Ephemeral, driver-local secret materialization for Windows process starts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from threading import Lock
from typing import Callable, Protocol

from synapse.sandbox import (
    OpaqueReference,
    SandboxArtifactFingerprint,
    SandboxSecretGrant,
    SandboxSecretOperation,
    SandboxWorkspaceId,
)

from .windows_authority import WindowsAuthorityContextV1, WindowsExecutionGrantStatus


class WindowsSecretDeliveryMode(StrEnum):
    ENVIRONMENT = "environment"


class WindowsSecretLifecycleState(StrEnum):
    REQUESTED = "requested"
    RESOLVED = "resolved"
    MATERIALIZED = "materialized"
    AVAILABLE_TO_CHILD = "available_to_child"
    REVOCATION_REQUESTED = "revocation_requested"
    REVOKED = "revoked"
    REVOCATION_UNPROVEN = "revocation_unproven"


class WindowsSecretMaterializationError(RuntimeError):
    """Redaction-safe materialization failure."""


@dataclass(frozen=True, slots=True)
class WindowsSecretDeliveryRequest:
    environment_name: str
    grant: SandboxSecretGrant
    mode: WindowsSecretDeliveryMode = WindowsSecretDeliveryMode.ENVIRONMENT


@dataclass(frozen=True, slots=True)
class WindowsSecretSafeFactV1:
    secret_reference: OpaqueReference
    materialization_reference: OpaqueReference
    delivery_mode: WindowsSecretDeliveryMode
    workspace_id: SandboxWorkspaceId
    state: WindowsSecretLifecycleState
    safe_fingerprint: SandboxArtifactFingerprint
    reconciliation_required: bool


@dataclass(frozen=True, slots=True)
class WindowsSecretHealth:
    provider_configured: bool
    resolution_available: bool
    pipe_delivery_available: bool
    environment_delivery_available: bool
    temporary_file_delivery_available: bool
    revocation_capability: bool
    durable_plaintext_persistence: bool = False


class WindowsSecretProviderPort(Protocol):
    def resolve(self, reference: OpaqueReference) -> bytearray: ...
    def revoke(self, materialization_reference: OpaqueReference) -> bool: ...


class InMemoryWindowsSecretProvider:
    """Explicit controlled provider; values are never exposed by repr."""

    def __init__(self, values: dict[OpaqueReference, bytes]) -> None:
        self._values = {reference: bytes(value) for reference, value in values.items()}
        self._revoked: set[OpaqueReference] = set()
        self._lock = Lock()

    def __repr__(self) -> str:
        return "InMemoryWindowsSecretProvider(<redacted>)"

    def resolve(self, reference: OpaqueReference) -> bytearray:
        with self._lock:
            value = self._values.get(reference)
            if value is None:
                raise WindowsSecretMaterializationError("secret_reference_unknown")
            return bytearray(value)

    def revoke(self, materialization_reference: OpaqueReference) -> bool:
        with self._lock:
            self._revoked.add(materialization_reference)
        return True


class WindowsSecretMaterialization:
    __slots__ = ("_buffer", "_provider", "fact", "environment_name")

    def __init__(
        self,
        buffer: bytearray,
        provider: WindowsSecretProviderPort,
        fact: WindowsSecretSafeFactV1,
        environment_name: str,
    ) -> None:
        self._buffer = buffer
        self._provider = provider
        self.fact = fact
        self.environment_name = environment_name

    def __repr__(self) -> str:
        return f"WindowsSecretMaterialization(fact={self.fact!r}, value=<redacted>)"

    def environment_value(self) -> str:
        try:
            return self._buffer.decode("utf-8")
        except UnicodeDecodeError as error:
            raise WindowsSecretMaterializationError("secret_format_invalid") from error

    def available_to_child(self) -> None:
        self._state(WindowsSecretLifecycleState.AVAILABLE_TO_CHILD, False)

    def revoke(self) -> bool:
        self._state(WindowsSecretLifecycleState.REVOCATION_REQUESTED, True)
        for index in range(len(self._buffer)):
            self._buffer[index] = 0
        try:
            proven = self._provider.revoke(self.fact.materialization_reference)
        except Exception:
            proven = False
        self._state(
            WindowsSecretLifecycleState.REVOKED
            if proven
            else WindowsSecretLifecycleState.REVOCATION_UNPROVEN,
            not proven,
        )
        return proven

    def _state(self, state: WindowsSecretLifecycleState, reconciliation: bool) -> None:
        self.fact = WindowsSecretSafeFactV1(
            self.fact.secret_reference,
            self.fact.materialization_reference,
            self.fact.delivery_mode,
            self.fact.workspace_id,
            state,
            self.fact.safe_fingerprint,
            reconciliation,
        )


class WindowsSecretMaterializer:
    def __init__(
        self,
        provider: WindowsSecretProviderPort,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._provider = provider
        self._now = now
        self._usage: dict[tuple[OpaqueReference, OpaqueReference], int] = {}
        self._lock = Lock()

    def health(self) -> WindowsSecretHealth:
        return WindowsSecretHealth(True, True, False, True, False, True)

    def materialize(
        self,
        request: WindowsSecretDeliveryRequest,
        context: WindowsAuthorityContextV1 | None,
        workspace_id: SandboxWorkspaceId,
    ) -> WindowsSecretMaterialization:
        code = self._validate(request, context, workspace_id)
        if code is not None:
            raise WindowsSecretMaterializationError(code)
        assert context is not None and context.grant is not None
        grant = request.grant
        key = (grant.declaration.secret_ref, context.attempt_reference)
        with self._lock:
            used = self._usage.get(key, 0)
            if used >= grant.maximum_usage_count:
                raise WindowsSecretMaterializationError("secret_usage_exhausted")
            self._usage[key] = used + 1
        identity = OpaqueReference(
            "secret-materialization:"
            + SandboxArtifactFingerprint.from_content(
                (grant.declaration.secret_ref, context.attempt_reference, used + 1)
            ).value
        )
        try:
            value = self._provider.resolve(grant.declaration.secret_ref)
        except WindowsSecretMaterializationError:
            raise
        except Exception as error:
            raise WindowsSecretMaterializationError("secret_materialization_failed") from error
        safe = SandboxArtifactFingerprint.from_content(
            (grant.declaration.secret_ref, identity, request.mode, workspace_id)
        )
        fact = WindowsSecretSafeFactV1(
            grant.declaration.secret_ref,
            identity,
            request.mode,
            workspace_id,
            WindowsSecretLifecycleState.MATERIALIZED,
            safe,
            False,
        )
        return WindowsSecretMaterialization(value, self._provider, fact, request.environment_name)

    def _validate(
        self,
        request: WindowsSecretDeliveryRequest,
        context: WindowsAuthorityContextV1 | None,
        workspace_id: SandboxWorkspaceId,
    ) -> str | None:
        if request.mode is not WindowsSecretDeliveryMode.ENVIRONMENT:
            return "secret_delivery_unsupported"
        if (
            not request.environment_name
            or "=" in request.environment_name
            or "\0" in request.environment_name
        ):
            return "secret_delivery_invalid"
        if context is None or context.grant is None:
            return "secret_authorization_invalid"
        grant, execution = request.grant, context.grant
        if execution.status is not WindowsExecutionGrantStatus.ACTIVE:
            return "secret_revoked"
        now = self._now()
        if now < grant.not_before or now >= grant.expires_at or now >= execution.expires_at:
            return "secret_expired"
        if grant.subject != context.subject_reference:
            return "secret_subject_mismatch"
        if grant.workload_id.value != context.workload_reference.value:
            return "secret_workload_mismatch"
        if grant.plan_id.value != context.plan_reference.value:
            return "secret_plan_mismatch"
        if grant.attempt_id.value != context.attempt_reference.value:
            return "secret_attempt_mismatch"
        if (
            grant.declaration.scope_ref.value != workspace_id.value
            or context.workspace_id != workspace_id
        ):
            return "secret_scope_mismatch"
        if grant.authorization_ref != execution.grant_reference:
            return "secret_grant_mismatch"
        required = {SandboxSecretOperation.RESOLVE_REFERENCE, SandboxSecretOperation.ACQUIRE_LEASE}
        if not required.issubset(set(grant.operations)):
            return "secret_authorization_invalid"
        return None

    @staticmethod
    def replay(fact: WindowsSecretSafeFactV1) -> WindowsSecretSafeFactV1:
        if fact.state is WindowsSecretLifecycleState.REVOKED:
            return fact
        return WindowsSecretSafeFactV1(
            fact.secret_reference,
            fact.materialization_reference,
            fact.delivery_mode,
            fact.workspace_id,
            WindowsSecretLifecycleState.REVOCATION_UNPROVEN,
            fact.safe_fingerprint,
            True,
        )
