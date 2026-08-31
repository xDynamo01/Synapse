from __future__ import annotations

from dataclasses import replace

import pytest
from tests.test_windows_process_driver import Authorization, FakeApi, Fencing, _request, _resolved

from synapse.sandbox import OpaqueReference
from synapse.sandbox_drivers import (
    SandboxFencingDecision,
    UnavailableWindowsNetworkMechanism,
    WindowsNetworkCapabilityFactV1,
    WindowsNetworkCapabilityState,
    WindowsNetworkPolicyLayer,
    WindowsNetworkPolicyV1,
    WindowsNetworkProfile,
    WindowsProcessDriver,
    WindowsProcessStartOutcome,
)

CAPABILITY = OpaqueReference("capability:network")


class Mechanism:
    def __init__(self, *, configure=True, verify=True, cleanup=True, descendants=True):
        self.configure_ok = configure
        self.verify_ok = verify
        self.cleanup_ok = cleanup
        self.descendants = descendants
        self.calls = []

    def capability(self, profile):
        unrestricted = profile is WindowsNetworkProfile.UNRESTRICTED_BY_DRIVER_BUT_GOVERNED
        return WindowsNetworkCapabilityFactV1(
            profile,
            WindowsNetworkCapabilityState.OBSERVABLE_ONLY
            if unrestricted
            else WindowsNetworkCapabilityState.ENFORCEABLE,
            not unrestricted,
            not unrestricted,
            not unrestricted,
            self.descendants and not unrestricted,
            not unrestricted,
            not unrestricted,
            not unrestricted,
            not unrestricted,
        )

    def configure(self, policy):
        self.calls.append("network_configure")
        return (
            OpaqueReference(f"network-rule:{policy.attempt_reference.value}")
            if self.configure_ok
            else None
        )

    def verify(self, ownership_reference):
        self.calls.append("network_verify")
        return self.verify_ok

    def cleanup(self, ownership_reference):
        self.calls.append("network_cleanup")
        return self.cleanup_ok


def _policy(command, workspace, profile=WindowsNetworkProfile.DISABLED, required=True):
    return WindowsNetworkPolicyV1(
        profile,
        required,
        CAPABILITY,
        command.workload_reference,
        command.plan_reference,
        command.attempt_reference,
        workspace,
    )


def _request_with_network(tmp_path, profile=WindowsNetworkProfile.DISABLED, required=True):
    workspace, _, command = _resolved(tmp_path)
    request = _request(workspace, command)
    context = replace(
        request.authority_context,
        grant=replace(request.authority_context.grant, capabilities=(CAPABILITY,)),
    )
    return (
        workspace,
        command,
        replace(
            request,
            authority_context=context,
            network_policy=_policy(command, workspace, profile, required),
        ),
    )


def test_profiles_parse_and_default_health_is_factual() -> None:
    assert {
        WindowsNetworkProfile(item)
        for item in (
            "disabled",
            "loopback_only",
            "allowlisted",
            "unrestricted_by_driver_but_governed",
        )
    } == set(WindowsNetworkProfile)
    with pytest.raises(ValueError):
        WindowsNetworkProfile("internet_disabled")
    health = WindowsNetworkPolicyLayer().health()
    assert health.network_policy_layer_implemented
    assert not any(
        (
            health.disabled_enforceable,
            health.loopback_only_enforceable,
            health.allowlist_enforceable,
            health.descendant_coverage,
            health.ipv4_coverage,
            health.ipv6_coverage,
            health.tcp_coverage,
            health.udp_coverage,
            health.required_privilege_available,
        )
    )


def test_required_unsupported_and_grant_mismatch_block_before_process(tmp_path) -> None:
    _, _, request = _request_with_network(tmp_path)
    api = FakeApi()
    result = WindowsProcessDriver(
        api,
        Authorization(),
        Fencing(),
        network_policy_layer=WindowsNetworkPolicyLayer(),
        platform_available=True,
    ).start(request)
    assert result.outcome is WindowsProcessStartOutcome.FAILED
    assert result.diagnostic_codes == ("network_enforcement_unavailable",)
    assert "create_job" not in api.calls

    wrong = replace(
        request,
        network_policy=replace(
            request.network_policy, capability_reference=OpaqueReference("capability:wrong")
        ),
    )
    result = WindowsProcessDriver(
        api,
        Authorization(),
        Fencing(),
        network_policy_layer=WindowsNetworkPolicyLayer(),
        platform_available=True,
    ).start(wrong)
    assert result.diagnostic_codes == ("network_grant_mismatch",)


def test_optional_unsupported_and_unrestricted_are_factual_not_enforced(tmp_path) -> None:
    _, _, optional = _request_with_network(tmp_path, required=False)
    result = WindowsProcessDriver(
        FakeApi(),
        Authorization(),
        Fencing(),
        network_policy_layer=WindowsNetworkPolicyLayer(),
        platform_available=True,
    ).start(optional)
    assert result.outcome is WindowsProcessStartOutcome.STARTED
    assert result.network_application is not None and not result.network_application.enforced
    assert result.network_application.diagnostic_codes == ("network_enforcement_unavailable",)

    _, _, governed = _request_with_network(
        tmp_path / "governed", WindowsNetworkProfile.UNRESTRICTED_BY_DRIVER_BUT_GOVERNED
    )
    result = WindowsProcessDriver(
        FakeApi(),
        Authorization(),
        Fencing(),
        network_policy_layer=WindowsNetworkPolicyLayer(),
        platform_available=True,
    ).start(governed)
    assert result.outcome is WindowsProcessStartOutcome.STARTED
    assert (
        result.network_application is not None and not result.network_application.mutation_attempted
    )


@pytest.mark.parametrize(
    ("configure", "verify", "code"),
    [(False, True, "network_configuration_failed"), (True, False, "network_verification_failed")],
)
def test_configuration_and_verification_fail_closed(tmp_path, configure, verify, code) -> None:
    _, _, request = _request_with_network(tmp_path)
    api, mechanism = FakeApi(), Mechanism(configure=configure, verify=verify)
    result = WindowsProcessDriver(
        api,
        Authorization(),
        Fencing(),
        network_policy_layer=WindowsNetworkPolicyLayer(mechanism),
        platform_available=True,
    ).start(request)
    assert result.outcome is WindowsProcessStartOutcome.FAILED
    assert result.diagnostic_codes == (code,)
    assert "resume" not in api.calls


def test_fencing_stale_prevents_mutation_and_policy_is_verified_before_resume(tmp_path) -> None:
    _, _, request = _request_with_network(tmp_path)
    mechanism = Mechanism()
    fencing = Fencing([SandboxFencingDecision.VALID] * 6 + [SandboxFencingDecision.STALE])
    api = FakeApi()
    result = WindowsProcessDriver(
        api,
        Authorization(),
        fencing,
        network_policy_layer=WindowsNetworkPolicyLayer(mechanism),
        platform_available=True,
    ).start(request)
    assert result.outcome is WindowsProcessStartOutcome.FAILED
    assert mechanism.calls == [] and "resume" not in api.calls

    mechanism2, api2 = Mechanism(), FakeApi()
    result2 = WindowsProcessDriver(
        api2,
        Authorization(),
        Fencing(),
        network_policy_layer=WindowsNetworkPolicyLayer(mechanism2),
        platform_available=True,
    ).start(request)
    assert result2.outcome is WindowsProcessStartOutcome.STARTED
    assert mechanism2.calls[:2] == ["network_configure", "network_verify"]
    assert api2.marker == ["user-code"]


def test_descendant_gap_blocks_required_and_cleanup_is_not_presumed(tmp_path) -> None:
    _, _, request = _request_with_network(tmp_path)
    result = WindowsProcessDriver(
        FakeApi(),
        Authorization(),
        Fencing(),
        network_policy_layer=WindowsNetworkPolicyLayer(Mechanism(descendants=False)),
        platform_available=True,
    ).start(request)
    assert result.diagnostic_codes == ("network_enforcement_unavailable",)

    mechanism = Mechanism(cleanup=False)
    result = WindowsProcessDriver(
        FakeApi(),
        Authorization(),
        Fencing(),
        network_policy_layer=WindowsNetworkPolicyLayer(mechanism),
        platform_available=True,
    ).start(request)
    assert result.managed_process is not None
    assert not result.managed_process.close_custody_handles()
    assert result.managed_process.network_application is not None
    assert result.managed_process.network_application.cleanup_requested
    assert not result.managed_process.network_application.cleanup_proven
    assert "network_cleanup_unproven" in result.managed_process.network_application.diagnostic_codes


def test_job_object_is_never_reported_as_network_isolation() -> None:
    fact = UnavailableWindowsNetworkMechanism().capability(WindowsNetworkProfile.DISABLED)
    assert fact.state is WindowsNetworkCapabilityState.UNAVAILABLE
    assert not fact.mechanism_present and not fact.descendant_coverage
