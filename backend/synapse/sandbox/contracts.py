"""Read-only fact-provider ports for future Sandbox adapters."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from .identities import OpaqueReference, SandboxArtifactFingerprint
from .models import CapabilityDeclaration, ResourceLimit


@runtime_checkable
class SandboxAdmissionFactsProvider(Protocol):
    def admission_facts(self, subject: OpaqueReference) -> SandboxArtifactFingerprint: ...


@runtime_checkable
class SandboxPolicySnapshotProvider(Protocol):
    def policy_snapshot(self, policy_ref: OpaqueReference) -> SandboxArtifactFingerprint: ...


@runtime_checkable
class SandboxApprovalFactsProvider(Protocol):
    def approval_facts(self, approval_ref: OpaqueReference) -> SandboxArtifactFingerprint: ...


@runtime_checkable
class SandboxArtifactFactsProvider(Protocol):
    def artifact_facts(self, artifact_ref: OpaqueReference) -> SandboxArtifactFingerprint: ...


@runtime_checkable
class SandboxIsolationCapabilityProvider(Protocol):
    def declared_capabilities(
        self, isolation_profile_ref: OpaqueReference
    ) -> tuple[CapabilityDeclaration, ...]: ...

    def resource_limits(
        self, isolation_profile_ref: OpaqueReference
    ) -> tuple[ResourceLimit, ...]: ...


@runtime_checkable
class SandboxClock(Protocol):
    def now(self) -> datetime: ...
