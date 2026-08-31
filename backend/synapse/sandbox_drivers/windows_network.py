"""Factual Windows network-policy capability and enforcement boundary."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol

from synapse.sandbox import OpaqueReference, SandboxNetworkGrant, SandboxWorkspaceId

from .windows_authority import WindowsAuthorityContextV1


class WindowsNetworkProfile(StrEnum):
    DISABLED = "disabled"
    LOOPBACK_ONLY = "loopback_only"
    ALLOWLISTED = "allowlisted"
    UNRESTRICTED_BY_DRIVER_BUT_GOVERNED = "unrestricted_by_driver_but_governed"


class WindowsNetworkCapabilityState(StrEnum):
    SUPPORTED = "supported"
    CONFIGURED = "configured"
    ENFORCEABLE = "enforceable"
    ENFORCED = "enforced"
    OBSERVABLE_ONLY = "observable_only"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class WindowsNetworkPolicyV1:
    profile: WindowsNetworkProfile
    required: bool
    capability_reference: OpaqueReference
    workload_reference: OpaqueReference
    plan_reference: OpaqueReference
    attempt_reference: OpaqueReference
    workspace_id: SandboxWorkspaceId
    grants: tuple[SandboxNetworkGrant, ...] = ()


@dataclass(frozen=True, slots=True)
class WindowsNetworkCapabilityFactV1:
    profile: WindowsNetworkProfile
    state: WindowsNetworkCapabilityState
    mechanism_present: bool
    privilege_available: bool
    configuration_permitted: bool
    descendant_coverage: bool
    ipv4_coverage: bool
    ipv6_coverage: bool
    tcp_coverage: bool
    udp_coverage: bool
    diagnostic_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WindowsNetworkHealth:
    network_policy_layer_implemented: bool
    disabled_enforceable: bool
    loopback_only_enforceable: bool
    allowlist_enforceable: bool
    descendant_coverage: bool
    ipv4_coverage: bool
    ipv6_coverage: bool
    tcp_coverage: bool
    udp_coverage: bool
    required_privilege_available: bool


@dataclass(frozen=True, slots=True)
class WindowsNetworkApplicationV1:
    accepted: bool
    configured: bool
    enforced: bool
    mutation_attempted: bool
    cleanup_requested: bool
    cleanup_proven: bool
    ownership_reference: OpaqueReference | None
    capability: WindowsNetworkCapabilityFactV1
    diagnostic_codes: tuple[str, ...]


class WindowsNetworkMechanismPort(Protocol):
    def capability(self, profile: WindowsNetworkProfile) -> WindowsNetworkCapabilityFactV1: ...
    def configure(self, policy: WindowsNetworkPolicyV1) -> OpaqueReference | None: ...
    def verify(self, ownership_reference: OpaqueReference) -> bool: ...
    def cleanup(self, ownership_reference: OpaqueReference) -> bool: ...


class UnavailableWindowsNetworkMechanism:
    """Factual V1 host discovery result: Job Objects do not isolate networking."""

    def capability(self, profile: WindowsNetworkProfile) -> WindowsNetworkCapabilityFactV1:
        unrestricted = profile is WindowsNetworkProfile.UNRESTRICTED_BY_DRIVER_BUT_GOVERNED
        return WindowsNetworkCapabilityFactV1(
            profile,
            WindowsNetworkCapabilityState.OBSERVABLE_ONLY
            if unrestricted
            else WindowsNetworkCapabilityState.UNAVAILABLE,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            () if unrestricted else ("network_mechanism_unavailable",),
        )

    def configure(self, policy: WindowsNetworkPolicyV1) -> OpaqueReference | None:
        return None

    def verify(self, ownership_reference: OpaqueReference) -> bool:
        return False

    def cleanup(self, ownership_reference: OpaqueReference) -> bool:
        return False


class WindowsNetworkPolicyLayer:
    def __init__(self, mechanism: WindowsNetworkMechanismPort | None = None) -> None:
        self._mechanism = mechanism or UnavailableWindowsNetworkMechanism()

    def health(self) -> WindowsNetworkHealth:
        facts = {profile: self._mechanism.capability(profile) for profile in WindowsNetworkProfile}
        disabled = facts[WindowsNetworkProfile.DISABLED]
        loopback = facts[WindowsNetworkProfile.LOOPBACK_ONLY]
        allowlist = facts[WindowsNetworkProfile.ALLOWLISTED]
        restrictive = (disabled, loopback, allowlist)
        return WindowsNetworkHealth(
            True,
            disabled.state is WindowsNetworkCapabilityState.ENFORCEABLE,
            loopback.state is WindowsNetworkCapabilityState.ENFORCEABLE,
            allowlist.state is WindowsNetworkCapabilityState.ENFORCEABLE,
            all(item.descendant_coverage for item in restrictive),
            all(item.ipv4_coverage for item in restrictive),
            all(item.ipv6_coverage for item in restrictive),
            all(item.tcp_coverage for item in restrictive),
            all(item.udp_coverage for item in restrictive),
            all(item.privilege_available for item in restrictive),
        )

    def assess(
        self,
        policy: WindowsNetworkPolicyV1,
        context: WindowsAuthorityContextV1 | None,
        workspace_id: SandboxWorkspaceId,
    ) -> WindowsNetworkApplicationV1:
        capability = self._mechanism.capability(policy.profile)
        mismatch = self._correspondence(policy, context, workspace_id)
        if mismatch is not None:
            return self._application(False, capability, mismatch)
        if policy.profile is WindowsNetworkProfile.UNRESTRICTED_BY_DRIVER_BUT_GOVERNED:
            return WindowsNetworkApplicationV1(
                True, False, False, False, False, False, None, capability, ()
            )
        complete = all(
            (
                capability.descendant_coverage,
                capability.ipv4_coverage,
                capability.ipv6_coverage,
                capability.tcp_coverage,
                capability.udp_coverage,
                capability.privilege_available,
                capability.configuration_permitted,
            )
        )
        if capability.state is not WindowsNetworkCapabilityState.ENFORCEABLE or not complete:
            accepted = not policy.required
            return self._application(accepted, capability, "network_enforcement_unavailable")
        return self._application(True, capability, "network_configuration_required")

    def configure(self, policy: WindowsNetworkPolicyV1) -> WindowsNetworkApplicationV1:
        capability = self._mechanism.capability(policy.profile)
        try:
            ownership = self._mechanism.configure(policy)
        except OSError:
            ownership = None
        if ownership is None:
            failed = replace(capability, state=WindowsNetworkCapabilityState.FAILED)
            return WindowsNetworkApplicationV1(
                False,
                False,
                False,
                True,
                False,
                False,
                None,
                failed,
                ("network_configuration_failed",),
            )
        configured = replace(capability, state=WindowsNetworkCapabilityState.CONFIGURED)
        return WindowsNetworkApplicationV1(
            True, True, False, True, False, False, ownership, configured, ()
        )

    def verify(self, application: WindowsNetworkApplicationV1) -> WindowsNetworkApplicationV1:
        ownership = application.ownership_reference
        if ownership is None:
            return application
        try:
            verified = self._mechanism.verify(ownership)
        except OSError:
            verified = False
        if not verified:
            return replace(
                application,
                accepted=False,
                capability=replace(
                    application.capability, state=WindowsNetworkCapabilityState.FAILED
                ),
                diagnostic_codes=("network_verification_failed",),
            )
        return replace(
            application,
            enforced=True,
            capability=replace(
                application.capability, state=WindowsNetworkCapabilityState.ENFORCED
            ),
        )

    def cleanup(self, application: WindowsNetworkApplicationV1) -> WindowsNetworkApplicationV1:
        ownership = application.ownership_reference
        if ownership is None:
            return application
        try:
            proven = self._mechanism.cleanup(ownership)
        except OSError:
            proven = False
        return replace(
            application,
            cleanup_requested=True,
            cleanup_proven=proven,
            diagnostic_codes=application.diagnostic_codes
            + (() if proven else ("network_cleanup_unproven",)),
        )

    @staticmethod
    def requires_host_effect(application: WindowsNetworkApplicationV1) -> bool:
        return application.diagnostic_codes == ("network_configuration_required",)

    @staticmethod
    def _correspondence(
        policy: WindowsNetworkPolicyV1,
        context: WindowsAuthorityContextV1 | None,
        workspace_id: SandboxWorkspaceId,
    ) -> str | None:
        if context is None or context.grant is None:
            return "network_authorization_invalid"
        if policy.workload_reference != context.workload_reference:
            return "network_workload_mismatch"
        if policy.plan_reference != context.plan_reference:
            return "network_plan_mismatch"
        if policy.attempt_reference != context.attempt_reference:
            return "network_attempt_mismatch"
        if policy.workspace_id != workspace_id or context.workspace_id != workspace_id:
            return "network_workspace_mismatch"
        if policy.capability_reference not in context.grant.capabilities:
            return "network_grant_mismatch"
        if any(grant.scope_ref.value != workspace_id.value for grant in policy.grants):
            return "network_scope_mismatch"
        if policy.profile is WindowsNetworkProfile.ALLOWLISTED and not policy.grants:
            return "network_grant_mismatch"
        return None

    @staticmethod
    def _application(
        accepted: bool,
        capability: WindowsNetworkCapabilityFactV1,
        code: str,
    ) -> WindowsNetworkApplicationV1:
        return WindowsNetworkApplicationV1(
            accepted, False, False, False, False, False, None, capability, (code,)
        )
