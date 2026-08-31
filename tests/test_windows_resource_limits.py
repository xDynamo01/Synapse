from __future__ import annotations

import ctypes
import os

import pytest
from tests.factories.windows_authority import process_context
from tests.test_windows_output_capture import _native_command
from tests.test_windows_process_driver import Authorization, FakeApi, Fencing, _request, _resolved

from synapse.sandbox import (
    OpaqueReference,
    SandboxResourceDimension,
    SandboxResourceEnforcement,
    SandboxResourceGrant,
    SandboxResourceLimit,
    SandboxResourceScope,
    SandboxResourceUnit,
)
from synapse.sandbox_drivers import (
    MAX_SIGNED_64,
    NativeWindowsProcessApi,
    WindowsJobResourceDimension,
    WindowsJobResourceEnforcer,
    WindowsJobResourcePolicyV1,
    WindowsJobResourceRequirement,
    WindowsJobRuntimeMetricsV1,
    WindowsNativeJobLimits,
    WindowsOutputLimits,
    WindowsProcessDriver,
    WindowsProcessStartOutcome,
    WindowsProcessStartRequest,
    WindowsResourceCapability,
    WindowsResourceCapabilityState,
)


def requirement(
    dimension=WindowsJobResourceDimension.PROCESS_COUNT,
    requested=2,
    granted=2,
    required=True,
):
    return WindowsJobResourceRequirement(dimension, requested, granted, required)


class ResourceApi:
    def __init__(
        self,
        *,
        capabilities=None,
        configure=True,
        observed=None,
        query_failure=False,
        metrics_failure=False,
    ) -> None:
        self.capabilities = capabilities or (
            WindowsResourceCapability(
                WindowsJobResourceDimension.PROCESS_COUNT,
                WindowsResourceCapabilityState.CONFIGURABLE,
                True,
            ),
        )
        self.configure = configure
        self.observed = observed
        self.query_failure = query_failure
        self.metrics_failure = metrics_failure
        self.configured = None

    def resource_capabilities(self):
        return self.capabilities

    def configure_job_limits(self, job, limits):
        self.configured = limits
        return self.configure

    def query_job_limits(self, job):
        if self.query_failure:
            raise OSError("injected")
        return self.observed or self.configured

    def collect_job_metrics(self, job):
        if self.metrics_failure:
            raise OSError("injected")
        return WindowsJobRuntimeMetricsV1(True, 1, 2, 3, 4, 5)


def test_valid_required_policy_is_configured_and_verified() -> None:
    api = ResourceApi()
    result = WindowsJobResourceEnforcer(api).apply(
        10, WindowsJobResourcePolicyV1((requirement(),))
    )
    assert result.accepted and not result.diagnostics
    assert api.configured == WindowsNativeJobLimits(active_process_limit=2)
    assert result.facts[0].configured and result.facts[0].active
    assert result.facts[0].capability_state is WindowsResourceCapabilityState.ENFORCED


def test_unsupported_required_blocks_but_optional_remains_factual() -> None:
    capability = WindowsResourceCapability(
        WindowsJobResourceDimension.PROCESS_COUNT,
        WindowsResourceCapabilityState.OBSERVABLE_ONLY,
        True,
    )
    for required, accepted, diagnostics in (
        (True, False, ("required_resource_enforcement_unavailable",)),
        (False, True, ()),
    ):
        result = WindowsJobResourceEnforcer(ResourceApi(capabilities=(capability,))).apply(
            10, WindowsJobResourcePolicyV1((requirement(required=required),))
        )
        assert result.accepted is accepted and result.diagnostics == diagnostics
        assert not result.facts[0].configured and not result.facts[0].active
        assert result.facts[0].capability_state is WindowsResourceCapabilityState.OBSERVABLE_ONLY


@pytest.mark.parametrize(
    ("api", "code"),
    [
        (ResourceApi(configure=False), "job_configuration_failed"),
        (ResourceApi(query_failure=True), "job_verification_failed"),
        (
            ResourceApi(observed=WindowsNativeJobLimits(active_process_limit=3)),
            "job_verification_failed",
        ),
    ],
)
def test_configuration_and_verification_fail_closed(api, code) -> None:
    result = WindowsJobResourceEnforcer(api).apply(
        10, WindowsJobResourcePolicyV1((requirement(),))
    )
    assert not result.accepted and result.diagnostics == (code,)


def test_requested_above_grant_is_rejected_before_job_configuration() -> None:
    api = ResourceApi()
    result = WindowsJobResourceEnforcer(api).apply(
        10, WindowsJobResourcePolicyV1((requirement(requested=3, granted=2),))
    )
    assert not result.accepted
    assert result.diagnostics == ("requested_limit_exceeds_grant",)
    assert api.configured is None


def test_policy_maps_frozen_sandbox_grants_without_expanding_authority() -> None:
    requested = SandboxResourceLimit(
        SandboxResourceDimension.PROCESS_COUNT,
        SandboxResourceUnit.COUNT,
        SandboxResourceScope.PROCESS_TREE,
        4,
    )
    effective = SandboxResourceLimit(
        SandboxResourceDimension.PROCESS_COUNT,
        SandboxResourceUnit.COUNT,
        SandboxResourceScope.PROCESS_TREE,
        2,
    )
    grant = SandboxResourceGrant(
        requested,
        effective,
        effective,
        effective,
        (SandboxResourceEnforcement.PROCESS_TREE,),
        ("resource.intersection_satisfied",),
    )
    policy = WindowsJobResourcePolicyV1.from_sandbox_grants((grant,))
    assert policy.requirements == (
        WindowsJobResourceRequirement(
            WindowsJobResourceDimension.PROCESS_COUNT, 4, 2, True
        ),
    )
    result = WindowsJobResourceEnforcer(ResourceApi()).apply(10, policy)
    assert result.diagnostics == ("requested_limit_exceeds_grant",)


@pytest.mark.parametrize("value", (-1, 0, MAX_SIGNED_64 + 1, True))
def test_integer_boundaries_reject_invalid_values(value) -> None:
    with pytest.raises(ValueError, match="resource_policy_invalid"):
        requirement(requested=value)


def test_time_conversion_overflow_and_cpu_rate_range_are_rejected() -> None:
    policy = WindowsJobResourcePolicyV1(
        (
            requirement(
                WindowsJobResourceDimension.PROCESS_CPU_TIME,
                MAX_SIGNED_64 // 10_000 + 1,
                MAX_SIGNED_64 // 10_000 + 1,
            ),
        )
    )
    capability = WindowsResourceCapability(
        WindowsJobResourceDimension.PROCESS_CPU_TIME,
        WindowsResourceCapabilityState.CONFIGURABLE,
        True,
    )
    with pytest.raises(ValueError, match="resource_policy_invalid"):
        WindowsJobResourceEnforcer(ResourceApi(capabilities=(capability,))).apply(10, policy)
    with pytest.raises(ValueError, match="resource_policy_invalid"):
        requirement(WindowsJobResourceDimension.CPU_RATE, 10_001, 10_001)


def test_metrics_unavailable_does_not_erase_enforcement_fact() -> None:
    api = ResourceApi(metrics_failure=True)
    enforcer = WindowsJobResourceEnforcer(api)
    application = enforcer.apply(10, WindowsJobResourcePolicyV1((requirement(),)))
    metrics = enforcer.metrics(10)
    assert application.facts[0].active
    assert not metrics.available and metrics.diagnostics == ("metrics_unavailable",)


class DriverResourceApi(FakeApi):
    def __init__(self, capability_state=WindowsResourceCapabilityState.CONFIGURABLE):
        super().__init__()
        self.capability_state = capability_state
        self.limits = None

    def resource_capabilities(self):
        self.calls.append("resource_capabilities")
        return (
            WindowsResourceCapability(
                WindowsJobResourceDimension.PROCESS_COUNT,
                self.capability_state,
                True,
            ),
        )

    def configure_job_limits(self, job, limits):
        self.calls.append("configure_limits")
        self.limits = limits
        return True

    def query_job_limits(self, job):
        self.calls.append("verify_limits")
        return self.limits


def test_required_limits_are_verified_before_process_creation_and_resume(tmp_path) -> None:
    workspace, _, command = _resolved(tmp_path)
    api = DriverResourceApi()
    request = _request(workspace, command)
    request = type(request)(
        request.command,
        request.grant_reference,
        request.expected_command_fingerprint,
        request.workspace_id,
        request.driver_attempt_reference,
        resource_policy=WindowsJobResourcePolicyV1((requirement(),)),
        authority_context=request.authority_context,
    )
    result = WindowsProcessDriver(
        api, Authorization(), Fencing(), platform_available=True
    ).start(request)
    assert result.outcome is WindowsProcessStartOutcome.STARTED
    assert api.calls.index("configure_limits") < api.calls.index("create_suspended")
    assert api.calls.index("verify_limits") < api.calls.index("create_suspended")
    assert api.calls.index("verify_limits") < api.calls.index("resume")


def test_unavailable_required_limit_never_creates_or_resumes_process(tmp_path) -> None:
    workspace, _, command = _resolved(tmp_path)
    api = DriverResourceApi(WindowsResourceCapabilityState.UNAVAILABLE)
    request = _request(workspace, command)
    request = type(request)(
        request.command,
        request.grant_reference,
        request.expected_command_fingerprint,
        request.workspace_id,
        request.driver_attempt_reference,
        resource_policy=WindowsJobResourcePolicyV1((requirement(),)),
        authority_context=request.authority_context,
    )
    result = WindowsProcessDriver(
        api, Authorization(), Fencing(), platform_available=True
    ).start(request)
    assert result.diagnostic_codes == ("required_resource_enforcement_unavailable",)
    assert "create_suspended" not in api.calls and "resume" not in api.calls


@pytest.mark.skipif(os.name != "nt", reason="Win32 smoke requires Windows")
def test_native_job_limits_configure_verify_and_metrics() -> None:
    api = NativeWindowsProcessApi()
    job = api.create_job()
    try:
        assert api.configure_kill_on_close(job)
        limits = WindowsNativeJobLimits(
            active_process_limit=2,
            process_memory_bytes=256 * 1024 * 1024,
            job_memory_bytes=512 * 1024 * 1024,
            process_cpu_time_100ns=10_000_000,
            job_cpu_time_100ns=20_000_000,
            cpu_rate=5_000,
        )
        assert api.configure_job_limits(job, limits)
        assert api.query_job_limits(job) == limits
        metrics = api.collect_job_metrics(job)
        assert metrics.available and metrics.active_process_count == 0
    finally:
        assert api.close_handle(job)


@pytest.mark.skipif(os.name != "nt", reason="Win32 smoke requires Windows")
def test_native_capability_matrix_is_dimension_specific() -> None:
    capabilities = NativeWindowsProcessApi().resource_capabilities()
    assert {item.dimension for item in capabilities} == set(WindowsJobResourceDimension)
    assert all(item.observable for item in capabilities)
    assert all(item.state is WindowsResourceCapabilityState.CONFIGURABLE for item in capabilities)


def _native_start(tmp_path, source, requirements):
    workspace, command = _native_command(tmp_path, source)
    api = NativeWindowsProcessApi()
    grant = OpaqueReference("grant:resources")
    result = WindowsProcessDriver(api, Authorization(), Fencing()).start(
        WindowsProcessStartRequest(
            command,
            grant,
            command.command_fingerprint,
            workspace,
            OpaqueReference("driver-attempt:resources"),
            output_limits=WindowsOutputLimits(256, 256),
            resource_policy=WindowsJobResourcePolicyV1(tuple(sorted(requirements, key=lambda item: item.dimension.value))),
            authority_context=process_context(command, workspace, grant),
        )
    )
    assert result.outcome is WindowsProcessStartOutcome.STARTED
    assert result.managed_process is not None
    return api, result.managed_process


@pytest.mark.skipif(os.name != "nt", reason="Win32 smoke requires Windows")
def test_native_process_count_within_and_above_limit_are_factual(tmp_path) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    within_api, within = _native_start(
        tmp_path / "within",
        "import subprocess, sys\n"
        "p=subprocess.Popen([sys._base_executable, '-c', 'print(123)'])\n"
        "print('child-rc', p.wait())\n",
        (requirement(requested=3, granted=3),),
    )
    assert kernel32.WaitForSingleObject(within.process_handle, 10_000) == 0
    within_output = within.finalize_output(5)
    assert b"child-rc 0" in within_output[0].retained_bytes
    assert within_api.query_job_limits(within.job_handle).active_process_limit == 3
    assert within.close_custody_handles()

    above_api, above = _native_start(
        tmp_path / "above",
        "import subprocess, sys\n"
        "try:\n"
        " p=subprocess.Popen([sys._base_executable, '-c', 'print(123)'])\n"
        " print('child-rc', p.wait())\n"
        "except OSError:\n"
        " print('child-rejected')\n",
        (requirement(requested=2, granted=2),),
    )
    assert kernel32.WaitForSingleObject(above.process_handle, 10_000) == 0
    above_output = above.finalize_output(5)
    observed = above_output[0].retained_bytes
    assert b"child-rejected" in observed or b"child-rc 0" not in observed
    assert above_api.query_job_limits(above.job_handle).active_process_limit == 2
    assert above.close_custody_handles()


@pytest.mark.skipif(os.name != "nt", reason="Win32 smoke requires Windows")
def test_native_job_memory_small_and_exceeding_workloads_are_distinct(tmp_path) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    limit = 256 * 1024 * 1024
    small_api, small = _native_start(
        tmp_path / "small",
        "x=bytearray(1024*1024)\nprint('small-ok', len(x))\n",
        (requirement(WindowsJobResourceDimension.JOB_MEMORY, limit, limit),),
    )
    assert kernel32.WaitForSingleObject(small.process_handle, 10_000) == 0
    assert small_api.process_state(small.process_handle) == (False, 0)
    assert b"small-ok" in small.finalize_output(5)[0].retained_bytes
    assert small.close_custody_handles()

    large_api, large = _native_start(
        tmp_path / "large",
        "x=bytearray(1024*1024*1024)\nprint('unexpected-allocation', len(x))\n",
        (requirement(WindowsJobResourceDimension.JOB_MEMORY, limit, limit),),
    )
    assert kernel32.WaitForSingleObject(large.process_handle, 15_000) == 0
    active, exit_code = large_api.process_state(large.process_handle)
    assert not active and exit_code != 0
    assert b"unexpected-allocation" not in large.finalize_output(5)[0].retained_bytes
    assert large.close_custody_handles()


@pytest.mark.skipif(os.name != "nt", reason="Win32 smoke requires Windows")
def test_native_cpu_time_limit_is_not_wall_clock_timeout(tmp_path) -> None:
    api, managed = _native_start(
        tmp_path,
        "value=0\nwhile True:\n value += 1\n",
        (
            requirement(
                WindowsJobResourceDimension.PROCESS_CPU_TIME,
                100,
                100,
            ),
        ),
    )
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    assert kernel32.WaitForSingleObject(managed.process_handle, 10_000) == 0
    active, exit_code = api.process_state(managed.process_handle)
    assert not active and exit_code is not None
    assert managed.close_custody_handles()
