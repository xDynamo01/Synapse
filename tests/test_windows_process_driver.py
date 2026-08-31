from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from tests.factories.windows_authority import process_context

from synapse.sandbox import (
    OpaqueReference,
    SandboxFilesystemResource,
    SandboxLogicalPath,
    SandboxProcessStdioPolicy,
    SandboxWorkspaceId,
)
from synapse.sandbox_drivers import (
    CREATE_SUSPENDED,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    NativeWindowsProcessApi,
    ResolveWindowsCommandRequest,
    SandboxFencingDecision,
    WindowsCommandConfig,
    WindowsCommandPolicy,
    WindowsCommandResolver,
    WindowsEntrypointBinding,
    WindowsExecutableClass,
    WindowsJobRuntimeMetricsV1,
    WindowsNativeJobLimits,
    WindowsProcessDriver,
    WindowsProcessStartOutcome,
    WindowsProcessStartRequest,
    fingerprint_local_artifact,
)
from synapse.sandbox_drivers.windows_process import (
    _EXTENDED_LIMIT,
    _PROCESS_INFORMATION,
    _STARTUPINFOW,
)


@dataclass
class Authorization:
    valid: bool = True
    calls: int = 0

    def validate(self, command, grant_reference) -> bool:
        self.calls += 1
        return self.valid


@dataclass
class Fencing:
    decisions: list[SandboxFencingDecision] = field(
        default_factory=lambda: [SandboxFencingDecision.VALID] * 20
    )

    def validate(self, workspace_id, operation):
        return self.decisions.pop(0)


@dataclass
class FakeApi:
    fail: str | None = None
    calls: list[str] = field(default_factory=list)
    closed: list[int] = field(default_factory=list)
    marker: list[str] = field(default_factory=list)

    def create_job(self):
        self.calls.append("create_job")
        return 0 if self.fail == "job" else 10

    def configure_kill_on_close(self, job):
        self.calls.append("configure_kill_on_close")
        return self.fail != "configure"

    def resource_capabilities(self):
        return ()

    def configure_job_limits(self, job, limits):
        return True

    def query_job_limits(self, job):
        return WindowsNativeJobLimits()

    def collect_job_metrics(self, job):
        return WindowsJobRuntimeMetricsV1(True, 0, 0, 0, 0, 0)

    def prepare_stdio(self, command, limits):
        return None

    def create_process_suspended(self, command, stdio=None):
        self.calls.append("create_suspended")
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
        self.closed.append(handle)
        return True


def _resolved(tmp_path):
    root = tmp_path / "workspaces"
    workspace = SandboxWorkspaceId("workspace:process")
    physical = root / "workspace-process"
    for name in ("input", "work", "output", "temp", "state"):
        (physical / name).mkdir(parents=True)
    executable = physical / "input" / "fixture.exe"
    executable.write_bytes(b"controlled-fixture")
    binding = WindowsEntrypointBinding(
        "fixture",
        WindowsExecutableClass.WORKSPACE_EXECUTABLE,
        OpaqueReference("executable:fixture"),
        SandboxFilesystemResource.INPUT,
        SandboxLogicalPath.parse("fixture.exe", case_sensitive=False),
        fingerprint_local_artifact(executable),
    )
    resolver = WindowsCommandResolver(WindowsCommandConfig(root, (binding,)))
    request = ResolveWindowsCommandRequest(
        OpaqueReference("plan:one"),
        OpaqueReference("workload:one"),
        OpaqueReference("attempt:one"),
        workspace,
        "fixture",
        (),
        SandboxFilesystemResource.WORKSPACE,
        None,
        (),
        SandboxProcessStdioPolicy.CLOSED,
        SandboxProcessStdioPolicy.DISCARD,
        SandboxProcessStdioPolicy.DISCARD,
        OpaqueReference("occurrence:one"),
    )
    command = resolver.resolve(request).command
    assert command is not None
    return workspace, executable, command


def _request(workspace, command, *, authorized=True, secrets=True):
    grant = OpaqueReference("grant:one")
    return WindowsProcessStartRequest(
        command,
        grant,
        command.command_fingerprint,
        workspace,
        OpaqueReference("driver-attempt:one"),
        secrets,
        authority_context=process_context(command, workspace, grant),
    )


def test_constants_and_health_are_factual(tmp_path) -> None:
    assert CREATE_SUSPENDED == 0x4
    assert JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE == 0x2000
    driver = WindowsProcessDriver(FakeApi(), Authorization(), Fencing(), platform_available=False)
    health = driver.health()
    assert health.process_creation_implemented and not health.platform_available
    assert not health.full_security_sandbox and not health.network_isolation
    assert ctypes.sizeof(_STARTUPINFOW) >= ctypes.sizeof(ctypes.c_void_p) * 3
    assert ctypes.sizeof(_PROCESS_INFORMATION) >= ctypes.sizeof(ctypes.c_void_p) * 2
    assert ctypes.sizeof(_EXTENDED_LIMIT) > ctypes.sizeof(ctypes.c_void_p)


def test_start_order_proves_containment_before_user_code(tmp_path) -> None:
    workspace, _, command = _resolved(tmp_path)
    api = FakeApi()
    observed_before_resume = []
    driver = WindowsProcessDriver(
        api,
        Authorization(),
        Fencing(),
        before_resume=lambda: observed_before_resume.append(tuple(api.marker)),
        platform_available=True,
    )
    result = driver.start(_request(workspace, command))
    assert result.outcome is WindowsProcessStartOutcome.STARTED
    assert observed_before_resume == [()]
    assert api.calls[:6] == [
        "create_job", "configure_kill_on_close", "create_suspended", "assign", "verify", "resume"
    ]
    assert api.marker == ["user-code"]
    assert result.process_created and result.containment_established and result.process_started
    assert result.managed_process is not None
    assert result.managed_process.process_id == 1234
    assert result.managed_process.process_reference.value != "1234"
    assert result.managed_process.close_custody_handles()
    assert sorted(api.closed) == [10, 20, 30]


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        ("job", "job_creation_failed"),
        ("configure", "job_configuration_failed"),
        ("create", "process_creation_failed"),
        ("assign", "job_assignment_failed"),
        ("verify", "containment_verification_failed"),
        ("resume", "resume_failed"),
    ],
)
def test_partial_start_failures_never_report_started_and_cleanup(tmp_path, failure, code) -> None:
    workspace, _, command = _resolved(tmp_path)
    api = FakeApi(failure)
    result = WindowsProcessDriver(
        api, Authorization(), Fencing(), platform_available=True
    ).start(_request(workspace, command))
    assert result.outcome is WindowsProcessStartOutcome.FAILED
    assert not result.process_started and result.diagnostic_codes == (code,)
    assert not api.marker
    if failure in {"assign", "verify", "resume"}:
        assert result.cleanup_proven
        assert api.closed == [30, 20, 10]


def test_stale_before_create_and_invalid_grant_have_zero_process_creation(tmp_path) -> None:
    workspace, _, command = _resolved(tmp_path)
    for authorization, fencing, code in (
        (Authorization(False), Fencing(), "grant_invalid"),
        (Authorization(), Fencing([SandboxFencingDecision.STALE]), "fencing_stale"),
    ):
        api = FakeApi()
        result = WindowsProcessDriver(api, authorization, fencing, platform_available=True).start(
            _request(workspace, command)
        )
        assert result.diagnostic_codes == (code,)
        assert "create_suspended" not in api.calls


def test_stale_before_resume_terminates_suspended_process_without_user_code(tmp_path) -> None:
    workspace, _, command = _resolved(tmp_path)
    api = FakeApi()
    fencing = Fencing(
        [SandboxFencingDecision.VALID] * 6 + [SandboxFencingDecision.STALE]
    )
    result = WindowsProcessDriver(api, Authorization(), fencing, platform_available=True).start(
        _request(workspace, command)
    )
    assert result.diagnostic_codes == ("fencing_stale",)
    assert "resume" not in api.calls and not api.marker
    assert result.cleanup_proven


def test_stale_executable_invalid_cwd_and_unresolved_secret_create_nothing(tmp_path) -> None:
    workspace, executable, command = _resolved(tmp_path)
    executable.write_bytes(b"replaced")
    api = FakeApi()
    assert WindowsProcessDriver(api, Authorization(), Fencing(), platform_available=True).start(
        _request(workspace, command)
    ).diagnostic_codes == ("executable_stale",)
    assert "create_suspended" not in api.calls
    executable.write_bytes(b"controlled-fixture")
    command.working_directory.rmdir()
    api = FakeApi()
    assert WindowsProcessDriver(api, Authorization(), Fencing(), platform_available=True).start(
        _request(workspace, command)
    ).diagnostic_codes == ("cwd_invalid",)
    assert "create_suspended" not in api.calls
    command.working_directory.mkdir()
    api = FakeApi()
    assert WindowsProcessDriver(api, Authorization(), Fencing(), platform_available=True).start(
        _request(workspace, command, secrets=False)
    ).diagnostic_codes == ("secret_materialization_required",)
    assert "create_suspended" not in api.calls


@pytest.mark.skipif(os.name != "nt", reason="Win32 smoke requires Windows")
def test_native_controlled_smoke_has_no_marker_before_job_contained_resume(tmp_path) -> None:
    root = tmp_path / "workspaces"
    workspace = SandboxWorkspaceId("workspace:native")
    physical = root / "workspace-native"
    for name in ("input", "work", "output", "temp", "state"):
        (physical / name).mkdir(parents=True)
    script = physical / "input" / "marker.py"
    marker = physical / "output" / "started.txt"
    script.write_text(
        "from pathlib import Path\nimport sys\nPath(sys.argv[1]).write_text('started')\n"
    )
    binding = WindowsEntrypointBinding(
        "marker",
        WindowsExecutableClass.PYTHON_SCRIPT,
        OpaqueReference("executable:marker"),
        SandboxFilesystemResource.INPUT,
        SandboxLogicalPath.parse("marker.py", case_sensitive=False),
        fingerprint_local_artifact(script),
        interpreter_name="python",
    )
    resolver = WindowsCommandResolver(
        WindowsCommandConfig(
            root,
            (binding,),
            (("python", Path(sys.executable)),),
            policy=WindowsCommandPolicy(python=True),
        )
    )
    command = resolver.resolve(
        ResolveWindowsCommandRequest(
            OpaqueReference("plan:native"),
            OpaqueReference("workload:native"),
            OpaqueReference("attempt:native"),
            workspace,
            "marker",
            (str(marker),),
            SandboxFilesystemResource.WORKSPACE,
            None,
            (),
            SandboxProcessStdioPolicy.CLOSED,
            SandboxProcessStdioPolicy.DISCARD,
            SandboxProcessStdioPolicy.DISCARD,
            OpaqueReference("occurrence:native"),
        )
    ).command
    assert command is not None
    observed = []
    driver = WindowsProcessDriver(
        NativeWindowsProcessApi(),
        Authorization(),
        Fencing(),
        before_resume=lambda: observed.append(marker.exists()),
    )
    result = driver.start(_request(workspace, command))
    assert result.outcome is WindowsProcessStartOutcome.STARTED
    assert observed == [False]
    assert result.managed_process is not None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    assert kernel32.WaitForSingleObject(result.managed_process.process_handle, 10_000) == 0
    assert marker.read_text() == "started"
    assert result.managed_process.close_custody_handles()
