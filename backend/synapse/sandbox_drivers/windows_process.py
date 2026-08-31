"""Win32 suspended process creation with mandatory Job Object containment."""

from __future__ import annotations

import ctypes
import msvcrt
import os
from ctypes import wintypes
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Protocol

from synapse.sandbox import (
    OpaqueReference,
    SandboxArtifactFingerprint,
    SandboxProcessStdioPolicy,
    SandboxWorkspaceId,
)

from .local_artifact_custody import fingerprint_local_artifact
from .windows_authority import (
    WindowsAuthorityContextV1,
    WindowsExecutionAuthorityGuard,
    WindowsExecutionGrantV1,
)
from .windows_command import ResolvedCommandV1
from .windows_network import (
    WindowsNetworkApplicationV1,
    WindowsNetworkPolicyLayer,
    WindowsNetworkPolicyV1,
)
from .windows_output import (
    WindowsCapturedOutputV1,
    WindowsOutputCapture,
    WindowsOutputLimits,
    WindowsOutputReader,
    WindowsOutputStream,
)
from .windows_resources import (
    WindowsJobResourceApi,
    WindowsJobResourceApplication,
    WindowsJobResourceDimension,
    WindowsJobResourceEnforcer,
    WindowsJobResourcePolicyV1,
    WindowsJobRuntimeMetricsV1,
    WindowsNativeJobLimits,
    WindowsResourceCapability,
    WindowsResourceCapabilityState,
)
from .windows_secrets import (
    WindowsSecretDeliveryRequest,
    WindowsSecretMaterialization,
    WindowsSecretMaterializationError,
    WindowsSecretMaterializer,
)
from .windows_workspace import SandboxFencingValidationPort

CREATE_SUSPENDED = 0x00000004
CREATE_UNICODE_ENVIRONMENT = 0x00000400
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
STARTF_USESTDHANDLES = 0x00000100
PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002
HANDLE_FLAG_INHERIT = 0x00000001
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
JOB_OBJECT_CPU_RATE_CONTROL_INFORMATION = 15
JOB_OBJECT_LIMIT_PROCESS_TIME = 0x00000002
JOB_OBJECT_LIMIT_JOB_TIME = 0x00000004
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOB_OBJECT_CPU_RATE_CONTROL_ENABLE = 0x00000001
JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP = 0x00000004
STILL_ACTIVE = 259


class WindowsProcessStartOutcome(StrEnum):
    STARTED = "started"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class WindowsStdioSetupError(OSError):
    def __init__(self, diagnostic_code: str) -> None:
        super().__init__(diagnostic_code)
        self.diagnostic_code = diagnostic_code


class WindowsExecutionAuthorizationPort(Protocol):
    def validate(
        self,
        command: ResolvedCommandV1,
        grant_reference: OpaqueReference,
    ) -> bool: ...


class WindowsProcessApi(WindowsJobResourceApi, Protocol):
    def create_job(self) -> int: ...
    def configure_kill_on_close(self, job: int) -> bool: ...
    def prepare_stdio(
        self, command: ResolvedCommandV1, limits: WindowsOutputLimits
    ) -> WindowsPreparedStdio | None: ...
    def create_process_suspended(
        self,
        command: ResolvedCommandV1,
        stdio: WindowsPreparedStdio | None = None,
        secret_environment: tuple[tuple[str, str], ...] = (),
    ) -> tuple[int, int, int]: ...
    def assign_process(self, job: int, process: int) -> bool: ...
    def process_in_job(self, process: int, job: int) -> bool: ...
    def resume_thread(self, thread: int) -> bool: ...
    def terminate_suspended(self, process: int) -> bool: ...
    def close_handle(self, handle: int) -> bool: ...


@dataclass(frozen=True, slots=True)
class WindowsProcessStartRequest:
    command: ResolvedCommandV1
    grant_reference: OpaqueReference
    expected_command_fingerprint: SandboxArtifactFingerprint
    workspace_id: SandboxWorkspaceId
    driver_attempt_reference: OpaqueReference
    secrets_resolved: bool = True
    secret_deliveries: tuple[WindowsSecretDeliveryRequest, ...] = ()
    output_limits: WindowsOutputLimits = WindowsOutputLimits()
    resource_policy: WindowsJobResourcePolicyV1 | None = None
    authority_context: WindowsAuthorityContextV1 | None = None
    network_policy: WindowsNetworkPolicyV1 | None = None


@dataclass(slots=True)
class _CommandGrantValidator:
    authorization: WindowsExecutionAuthorizationPort
    command: ResolvedCommandV1

    def validate(self, grant: WindowsExecutionGrantV1) -> bool:
        return self.authorization.validate(self.command, grant.grant_reference)


@dataclass(slots=True)
class WindowsPreparedStdio:
    stdin_handle: int
    stdout_handle: int
    stderr_handle: int
    inherited_handles: tuple[int, ...]
    parent_child_handles: tuple[int, ...]
    capture: WindowsOutputCapture | None
    _api: WindowsProcessApi
    _child_handles_closed: bool = False

    def close_parent_child_handles(self) -> bool:
        if self._child_handles_closed:
            return True
        closed = all(self._api.close_handle(handle) for handle in self.parent_child_handles)
        self._child_handles_closed = closed
        return closed

    def close_all(self) -> bool:
        child_closed = self.close_parent_child_handles()
        capture_closed = self.capture.close() if self.capture is not None else True
        return child_closed and capture_closed


@dataclass(slots=True)
class ManagedWindowsProcess:
    process_handle: int
    job_handle: int
    process_id: int
    process_reference: OpaqueReference
    driver_attempt_reference: OpaqueReference
    _api: WindowsProcessApi
    output_capture: WindowsOutputCapture | None = None
    network_application: WindowsNetworkApplicationV1 | None = None
    _network_layer: WindowsNetworkPolicyLayer | None = None
    _closed: bool = False

    def finalize_output(
        self, timeout_seconds: float | None = None
    ) -> tuple[WindowsCapturedOutputV1, ...]:
        if self.output_capture is None:
            return ()
        return self.output_capture.finalize(timeout_seconds)

    def close_custody_handles(self) -> bool:
        if self._closed:
            return True
        process_closed = self._api.close_handle(self.process_handle)
        job_closed = self._api.close_handle(self.job_handle)
        output_closed = self.output_capture.close() if self.output_capture is not None else True
        network_closed = True
        if (
            self.network_application is not None
            and self.network_application.ownership_reference is not None
            and self._network_layer is not None
        ):
            self.network_application = self._network_layer.cleanup(self.network_application)
            network_closed = self.network_application.cleanup_proven
        self._closed = process_closed and job_closed and output_closed and network_closed
        return self._closed


@dataclass(frozen=True, slots=True)
class WindowsProcessStartResult:
    outcome: WindowsProcessStartOutcome
    process_created: bool
    containment_established: bool
    process_started: bool
    cleanup_proven: bool
    managed_process: ManagedWindowsProcess | None
    diagnostic_codes: tuple[str, ...]
    resource_application: WindowsJobResourceApplication = WindowsJobResourceApplication(
        True, (), ()
    )
    network_application: WindowsNetworkApplicationV1 | None = None


@dataclass(frozen=True, slots=True)
class WindowsProcessDriverHealth:
    process_creation_implemented: bool
    platform_available: bool
    suspended_creation_supported: bool
    job_containment_supported: bool
    kill_on_close_configured: bool
    descendant_containment_semantics: bool
    stdout_capture_implemented: bool = True
    stderr_capture_implemented: bool = True
    concurrent_drain_available: bool = True
    byte_limits_enforced: bool = True
    truncation_reporting_available: bool = True
    binary_safe_capture: bool = True
    output_publication_available: bool = False
    process_count_enforcement: bool = False
    process_memory_enforcement: bool = False
    job_memory_enforcement: bool = False
    cpu_time_enforcement: bool = False
    cpu_rate_enforcement: bool = False
    runtime_metrics_available: bool = False
    filesystem_security_isolation: bool = False
    network_isolation: bool = False
    restricted_identity: bool = False
    full_security_sandbox: bool = False


class WindowsProcessDriver:
    def __init__(
        self,
        api: WindowsProcessApi,
        authorization: WindowsExecutionAuthorizationPort,
        fencing: SandboxFencingValidationPort,
        *,
        before_resume: Callable[[], None] | None = None,
        secret_materializer: WindowsSecretMaterializer | None = None,
        network_policy_layer: WindowsNetworkPolicyLayer | None = None,
        platform_available: bool | None = None,
    ) -> None:
        self._api = api
        self._authorization = authorization
        self._fencing = fencing
        self._before_resume = before_resume
        self._secret_materializer = secret_materializer
        self._network_policy_layer = network_policy_layer
        self._platform = os.name == "nt" if platform_available is None else platform_available

    def health(self) -> WindowsProcessDriverHealth:
        supported: set[WindowsJobResourceDimension] = set()
        metrics = False
        if self._platform:
            try:
                capabilities = self._api.resource_capabilities()
                supported = {
                    item.dimension
                    for item in capabilities
                    if item.state is WindowsResourceCapabilityState.CONFIGURABLE
                }
                metrics = any(item.observable for item in capabilities)
            except OSError:
                pass
        return WindowsProcessDriverHealth(
            True,
            self._platform,
            self._platform,
            self._platform,
            self._platform,
            self._platform,
            process_count_enforcement=WindowsJobResourceDimension.PROCESS_COUNT in supported,
            process_memory_enforcement=WindowsJobResourceDimension.PROCESS_MEMORY in supported,
            job_memory_enforcement=WindowsJobResourceDimension.JOB_MEMORY in supported,
            cpu_time_enforcement=bool(
                {
                    WindowsJobResourceDimension.PROCESS_CPU_TIME,
                    WindowsJobResourceDimension.JOB_CPU_TIME,
                }
                & supported
            ),
            cpu_rate_enforcement=WindowsJobResourceDimension.CPU_RATE in supported,
            runtime_metrics_available=metrics,
        )

    def start(self, request: WindowsProcessStartRequest) -> WindowsProcessStartResult:
        command = request.command
        if not self._platform:
            return self._result(WindowsProcessStartOutcome.UNAVAILABLE, "platform_unavailable")
        if (
            request.workspace_id != command.workspace_id
            or request.expected_command_fingerprint != command.command_fingerprint
        ):
            return self._result(WindowsProcessStartOutcome.FAILED, "command_correspondence_invalid")
        if not request.secrets_resolved:
            return self._result(
                WindowsProcessStartOutcome.FAILED, "secret_materialization_required"
            )
        if not self._integrity_current(command):
            return self._result(WindowsProcessStartOutcome.FAILED, "executable_stale")
        if not self._cwd_safe(command):
            return self._result(WindowsProcessStartOutcome.FAILED, "cwd_invalid")
        network_application: WindowsNetworkApplicationV1 | None = None
        network_effect_required = False
        if request.network_policy is not None:
            if self._network_policy_layer is None:
                return self._result(
                    WindowsProcessStartOutcome.FAILED, "network_policy_layer_unavailable"
                )
            network_application = self._network_policy_layer.assess(
                request.network_policy, request.authority_context, request.workspace_id
            )
            if not network_application.accepted:
                return self._result(
                    WindowsProcessStartOutcome.FAILED,
                    network_application.diagnostic_codes[0],
                )
            network_effect_required = self._network_policy_layer.requires_host_effect(
                network_application
            )
        materials: list[WindowsSecretMaterialization] = []
        if request.secret_deliveries:
            names = [item.environment_name.casefold() for item in request.secret_deliveries]
            if len(names) != len(set(names)):
                return self._result(WindowsProcessStartOutcome.FAILED, "secret_delivery_invalid")
            denied = self._authority(request, "secret_materialization")
            if denied is not None:
                return denied
            if self._secret_materializer is None:
                return self._result(
                    WindowsProcessStartOutcome.FAILED, "secret_provider_unavailable"
                )
            try:
                for item in request.secret_deliveries:
                    materials.append(
                        self._secret_materializer.materialize(
                            item, request.authority_context, request.workspace_id
                        )
                    )
            except WindowsSecretMaterializationError as error:
                cleanup = all(item.revoke() for item in materials)
                return self._result(WindowsProcessStartOutcome.FAILED, str(error), cleanup=cleanup)
        denied = self._authority(request, "job_create")
        if denied is not None:
            self._revoke_materials(materials)
            return denied

        job = self._api.create_job()
        if not job:
            self._revoke_materials(materials)
            return self._result(WindowsProcessStartOutcome.FAILED, "job_creation_failed")
        denied = self._authority(request, "job_configuration", cleanup_handle=job)
        if denied is not None:
            self._revoke_materials(materials)
            return denied
        if not self._api.configure_kill_on_close(job):
            cleanup = self._api.close_handle(job)
            secrets_cleanup = self._revoke_materials(materials)
            return self._result(
                WindowsProcessStartOutcome.FAILED,
                "job_configuration_failed",
                cleanup=cleanup and secrets_cleanup,
            )
        denied = self._authority(request, "job_configuration", cleanup_handle=job)
        if denied is not None:
            self._revoke_materials(materials)
            return denied
        resource_application = WindowsJobResourceEnforcer(self._api).apply(
            job, request.resource_policy
        )
        if not resource_application.accepted:
            cleanup = self._api.close_handle(job)
            secrets_cleanup = self._revoke_materials(materials)
            return WindowsProcessStartResult(
                WindowsProcessStartOutcome.FAILED,
                False,
                False,
                False,
                cleanup and secrets_cleanup,
                None,
                resource_application.diagnostics,
                resource_application,
            )
        stdio: WindowsPreparedStdio | None = None
        try:
            denied = self._authority(request, "stdio_setup", cleanup_handle=job)
            if denied is not None:
                self._revoke_materials(materials)
                return denied
            stdio = self._api.prepare_stdio(command, request.output_limits)
            denied = self._authority(request, "process_create", cleanup_handle=job)
            if denied is not None:
                if stdio is not None:
                    stdio.close_all()
                self._revoke_materials(materials)
                return denied
            secret_environment = tuple(
                (item.environment_name, item.environment_value()) for item in materials
            )
            if materials:
                process, thread, pid = self._api.create_process_suspended(
                    command, stdio, secret_environment
                )
            else:
                process, thread, pid = (
                    self._api.create_process_suspended(command)
                    if stdio is None
                    else self._api.create_process_suspended(command, stdio)
                )
            secret_environment = ()
        except WindowsStdioSetupError as error:
            secrets_cleanup = self._revoke_materials(materials)
            stdio_cleanup = stdio.close_all() if stdio is not None else True
            cleanup = self._api.close_handle(job)
            return self._result(
                WindowsProcessStartOutcome.FAILED,
                error.diagnostic_code,
                cleanup=cleanup and stdio_cleanup and secrets_cleanup,
            )
        except OSError:
            secrets_cleanup = self._revoke_materials(materials)
            stdio_cleanup = stdio.close_all() if stdio is not None else True
            cleanup = self._api.close_handle(job)
            return self._result(
                WindowsProcessStartOutcome.FAILED,
                "process_creation_failed",
                cleanup=cleanup and stdio_cleanup and secrets_cleanup,
            )
        if not process or not thread:
            secrets_cleanup = self._revoke_materials(materials)
            stdio_cleanup = stdio.close_all() if stdio is not None else True
            cleanup = self._api.close_handle(job)
            return self._result(
                WindowsProcessStartOutcome.FAILED,
                "process_creation_failed",
                cleanup=cleanup and stdio_cleanup and secrets_cleanup,
            )
        if stdio is not None:
            if not stdio.close_parent_child_handles():
                self._revoke_materials(materials)
                return self._rollback(
                    job, process, thread, "stdio_child_handle_close_failed", stdio
                )
            if stdio.capture is not None and not stdio.capture.start():
                self._revoke_materials(materials)
                return self._rollback(job, process, thread, "reader_startup_failed", stdio)
        denied = self._authority_after_create(
            request, job, process, thread, stdio, "job_assignment"
        )
        if denied is not None:
            self._revoke_materials(materials)
            return denied
        if not self._api.assign_process(job, process):
            self._revoke_materials(materials)
            return self._rollback(job, process, thread, "job_assignment_failed", stdio)
        if not self._api.process_in_job(process, job):
            self._revoke_materials(materials)
            return self._rollback(job, process, thread, "containment_verification_failed", stdio)
        if network_effect_required:
            assert request.network_policy is not None
            assert self._network_policy_layer is not None
            denied = self._authority_after_create(
                request, job, process, thread, stdio, "network_policy_configure"
            )
            if denied is not None:
                return denied
            network_application = self._network_policy_layer.configure(request.network_policy)
            if not network_application.accepted:
                return self._rollback(job, process, thread, "network_configuration_failed", stdio)
            network_application = self._network_policy_layer.verify(network_application)
            if not network_application.enforced:
                self._network_policy_layer.cleanup(network_application)
                return self._rollback(job, process, thread, "network_verification_failed", stdio)
        if self._before_resume is not None:
            self._before_resume()
        if materials:
            denied = self._authority_after_create(
                request, job, process, thread, stdio, "secret_delivery"
            )
            if denied is not None:
                self._revoke_materials(materials)
                return denied
            for material in materials:
                material.available_to_child()
            if not self._revoke_materials(materials):
                return self._rollback(job, process, thread, "secret_revocation_unproven", stdio)
        denied = self._authority_after_create(
            request, job, process, thread, stdio, "process_resume"
        )
        if denied is not None:
            return denied
        if not self._integrity_current(command):
            return self._rollback(job, process, thread, "executable_stale_before_resume", stdio)
        if not self._api.resume_thread(thread):
            return self._rollback(job, process, thread, "resume_failed", stdio)
        thread_closed = self._api.close_handle(thread)
        if not thread_closed:
            return self._rollback(job, process, thread, "thread_handle_close_failed", stdio)
        managed = ManagedWindowsProcess(
            process,
            job,
            pid,
            OpaqueReference(f"process-observation:{request.driver_attempt_reference.value}"),
            request.driver_attempt_reference,
            self._api,
            stdio.capture if stdio is not None else None,
            network_application,
            self._network_policy_layer,
        )
        return WindowsProcessStartResult(
            WindowsProcessStartOutcome.STARTED,
            True,
            True,
            True,
            False,
            managed,
            (),
            resource_application,
            network_application,
        )

    @staticmethod
    def _revoke_materials(materials: list[WindowsSecretMaterialization]) -> bool:
        return all(material.revoke() for material in materials)

    def _rollback(
        self,
        job: int,
        process: int,
        thread: int,
        code: str,
        stdio: WindowsPreparedStdio | None = None,
    ) -> WindowsProcessStartResult:
        terminated = self._api.terminate_suspended(process)
        thread_closed = self._api.close_handle(thread)
        process_closed = self._api.close_handle(process)
        job_closed = self._api.close_handle(job)
        output_closed = stdio.close_all() if stdio is not None else True
        return WindowsProcessStartResult(
            WindowsProcessStartOutcome.FAILED,
            True,
            code not in {"job_assignment_failed", "containment_verification_failed"},
            False,
            terminated and thread_closed and process_closed and job_closed and output_closed,
            None,
            (code,),
        )

    def _guard(self, command: ResolvedCommandV1) -> WindowsExecutionAuthorityGuard:
        return WindowsExecutionAuthorityGuard(
            _CommandGrantValidator(self._authorization, command), self._fencing
        )

    def _authority(
        self,
        request: WindowsProcessStartRequest,
        operation: str,
        *,
        cleanup_handle: int | None = None,
    ) -> WindowsProcessStartResult | None:
        check = self._guard(request.command).authorize(
            request.authority_context, request.workspace_id, operation
        )
        if check.allowed:
            return None
        cleanup = self._api.close_handle(cleanup_handle) if cleanup_handle is not None else True
        return self._result(
            WindowsProcessStartOutcome.FAILED, check.decision.value, cleanup=cleanup
        )

    def _authority_after_create(
        self,
        request: WindowsProcessStartRequest,
        job: int,
        process: int,
        thread: int,
        stdio: WindowsPreparedStdio | None,
        operation: str,
    ) -> WindowsProcessStartResult | None:
        check = self._guard(request.command).authorize(
            request.authority_context, request.workspace_id, operation
        )
        if check.allowed:
            return None
        return self._rollback(job, process, thread, check.decision.value, stdio)

    @staticmethod
    def _integrity_current(command: ResolvedCommandV1) -> bool:
        try:
            return all(
                fingerprint_local_artifact(path) == expected
                for path, expected in command.integrity_bindings
            )
        except (OSError, ValueError):
            return False

    @staticmethod
    def _cwd_safe(command: ResolvedCommandV1) -> bool:
        return command.working_directory.is_dir() and not command.working_directory.is_symlink()

    @staticmethod
    def _result(
        outcome: WindowsProcessStartOutcome,
        code: str,
        *,
        cleanup: bool = True,
    ) -> WindowsProcessStartResult:
        return WindowsProcessStartResult(outcome, False, False, False, cleanup, None, (code,))


class _STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [("StartupInfo", _STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]


class _SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", ctypes.c_void_p),
        ("bInheritHandle", wintypes.BOOL),
    ]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_ulonglong)
        for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    ]


class _BASIC_LIMIT(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _EXTENDED_LIMIT(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BASIC_LIMIT),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _CPU_RATE_CONTROL(ctypes.Structure):
    _fields_ = [("ControlFlags", wintypes.DWORD), ("CpuRate", wintypes.DWORD)]


class _BASIC_ACCOUNTING(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.c_longlong),
        ("TotalKernelTime", ctypes.c_longlong),
        ("ThisPeriodTotalUserTime", ctypes.c_longlong),
        ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
        ("TotalPageFaultCount", wintypes.DWORD),
        ("TotalProcesses", wintypes.DWORD),
        ("ActiveProcesses", wintypes.DWORD),
        ("TotalTerminatedProcesses", wintypes.DWORD),
    ]


class NativeWindowsProcessApi:
    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("windows process API unavailable")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._create_job = kernel32.CreateJobObjectW
        self._create_job.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self._create_job.restype = wintypes.HANDLE
        self._set_job = kernel32.SetInformationJobObject
        self._set_job.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self._set_job.restype = wintypes.BOOL
        self._create_process = kernel32.CreateProcessW
        self._create_process.argtypes = [
            wintypes.LPCWSTR,
            wintypes.LPWSTR,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.LPCWSTR,
            ctypes.POINTER(_STARTUPINFOW),
            ctypes.POINTER(_PROCESS_INFORMATION),
        ]
        self._create_process.restype = wintypes.BOOL
        self._create_pipe = kernel32.CreatePipe
        self._create_pipe.argtypes = [
            ctypes.POINTER(wintypes.HANDLE),
            ctypes.POINTER(wintypes.HANDLE),
            ctypes.POINTER(_SECURITY_ATTRIBUTES),
            wintypes.DWORD,
        ]
        self._create_pipe.restype = wintypes.BOOL
        self._set_handle_information = kernel32.SetHandleInformation
        self._set_handle_information.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD]
        self._set_handle_information.restype = wintypes.BOOL
        self._initialize_attribute_list = kernel32.InitializeProcThreadAttributeList
        self._initialize_attribute_list.argtypes = [
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self._initialize_attribute_list.restype = wintypes.BOOL
        self._update_attribute = kernel32.UpdateProcThreadAttribute
        self._update_attribute.argtypes = [
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_size_t,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        self._update_attribute.restype = wintypes.BOOL
        self._delete_attribute_list = kernel32.DeleteProcThreadAttributeList
        self._delete_attribute_list.argtypes = [ctypes.c_void_p]
        self._delete_attribute_list.restype = None
        self._assign = kernel32.AssignProcessToJobObject
        self._assign.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self._assign.restype = wintypes.BOOL
        self._in_job = kernel32.IsProcessInJob
        self._in_job.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
        self._in_job.restype = wintypes.BOOL
        self._resume = kernel32.ResumeThread
        self._resume.argtypes = [wintypes.HANDLE]
        self._resume.restype = wintypes.DWORD
        self._terminate = kernel32.TerminateProcess
        self._terminate.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self._terminate.restype = wintypes.BOOL
        self._close = kernel32.CloseHandle
        self._close.argtypes = [wintypes.HANDLE]
        self._close.restype = wintypes.BOOL
        self._wait = kernel32.WaitForSingleObject
        self._wait.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self._wait.restype = wintypes.DWORD
        self._exit_code = kernel32.GetExitCodeProcess
        self._exit_code.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self._exit_code.restype = wintypes.BOOL
        self._query_job = kernel32.QueryInformationJobObject
        self._query_job.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self._query_job.restype = wintypes.BOOL
        self._terminate_job = kernel32.TerminateJobObject
        self._terminate_job.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self._terminate_job.restype = wintypes.BOOL

    def create_job(self) -> int:
        return int(self._create_job(None, None) or 0)

    def configure_kill_on_close(self, job: int) -> bool:
        info = _EXTENDED_LIMIT()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        return bool(
            self._set_job(
                job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info)
            )
        )

    def resource_capabilities(self) -> tuple[WindowsResourceCapability, ...]:
        probes = {
            WindowsJobResourceDimension.PROCESS_COUNT: WindowsNativeJobLimits(
                active_process_limit=2
            ),
            WindowsJobResourceDimension.PROCESS_MEMORY: WindowsNativeJobLimits(
                process_memory_bytes=256 * 1024 * 1024
            ),
            WindowsJobResourceDimension.JOB_MEMORY: WindowsNativeJobLimits(
                job_memory_bytes=512 * 1024 * 1024
            ),
            WindowsJobResourceDimension.PROCESS_CPU_TIME: WindowsNativeJobLimits(
                process_cpu_time_100ns=10_000_000
            ),
            WindowsJobResourceDimension.JOB_CPU_TIME: WindowsNativeJobLimits(
                job_cpu_time_100ns=20_000_000
            ),
            WindowsJobResourceDimension.CPU_RATE: WindowsNativeJobLimits(cpu_rate=5_000),
        }
        capabilities: list[WindowsResourceCapability] = []
        for dimension, limits in probes.items():
            job = self.create_job()
            if not job:
                capabilities.append(
                    WindowsResourceCapability(
                        dimension, WindowsResourceCapabilityState.UNAVAILABLE, False
                    )
                )
                continue
            state = WindowsResourceCapabilityState.FAILED
            observable = False
            try:
                if self.configure_kill_on_close(job) and self.configure_job_limits(job, limits):
                    observed = self.query_job_limits(job)
                    if observed == limits:
                        state = WindowsResourceCapabilityState.CONFIGURABLE
                observable = self.collect_job_metrics(job).available
            except OSError:
                state = WindowsResourceCapabilityState.FAILED
            finally:
                self.close_handle(job)
            capabilities.append(WindowsResourceCapability(dimension, state, observable))
        return tuple(capabilities)

    def configure_job_limits(self, job: int, limits: WindowsNativeJobLimits) -> bool:
        info = _EXTENDED_LIMIT()
        flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if limits.active_process_limit is not None:
            flags |= JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            info.BasicLimitInformation.ActiveProcessLimit = limits.active_process_limit
        if limits.process_memory_bytes is not None:
            flags |= JOB_OBJECT_LIMIT_PROCESS_MEMORY
            info.ProcessMemoryLimit = limits.process_memory_bytes
        if limits.job_memory_bytes is not None:
            flags |= JOB_OBJECT_LIMIT_JOB_MEMORY
            info.JobMemoryLimit = limits.job_memory_bytes
        if limits.process_cpu_time_100ns is not None:
            flags |= JOB_OBJECT_LIMIT_PROCESS_TIME
            info.BasicLimitInformation.PerProcessUserTimeLimit = limits.process_cpu_time_100ns
        if limits.job_cpu_time_100ns is not None:
            flags |= JOB_OBJECT_LIMIT_JOB_TIME
            info.BasicLimitInformation.PerJobUserTimeLimit = limits.job_cpu_time_100ns
        info.BasicLimitInformation.LimitFlags = flags
        if not self._set_job(
            job,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            return False
        if limits.cpu_rate is not None:
            cpu = _CPU_RATE_CONTROL(
                JOB_OBJECT_CPU_RATE_CONTROL_ENABLE | JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP,
                limits.cpu_rate,
            )
            if not self._set_job(
                job,
                JOB_OBJECT_CPU_RATE_CONTROL_INFORMATION,
                ctypes.byref(cpu),
                ctypes.sizeof(cpu),
            ):
                return False
        return True

    def query_job_limits(self, job: int) -> WindowsNativeJobLimits:
        info = _EXTENDED_LIMIT()
        returned = wintypes.DWORD()
        if not self._query_job(
            job,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
            ctypes.byref(returned),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        flags = int(info.BasicLimitInformation.LimitFlags)
        cpu_rate: int | None = None
        cpu = _CPU_RATE_CONTROL()
        if (
            self._query_job(
                job,
                JOB_OBJECT_CPU_RATE_CONTROL_INFORMATION,
                ctypes.byref(cpu),
                ctypes.sizeof(cpu),
                ctypes.byref(returned),
            )
            and cpu.ControlFlags & JOB_OBJECT_CPU_RATE_CONTROL_ENABLE
        ):
            cpu_rate = int(cpu.CpuRate)
        return WindowsNativeJobLimits(
            int(info.BasicLimitInformation.ActiveProcessLimit)
            if flags & JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            else None,
            int(info.ProcessMemoryLimit) if flags & JOB_OBJECT_LIMIT_PROCESS_MEMORY else None,
            int(info.JobMemoryLimit) if flags & JOB_OBJECT_LIMIT_JOB_MEMORY else None,
            int(info.BasicLimitInformation.PerProcessUserTimeLimit)
            if flags & JOB_OBJECT_LIMIT_PROCESS_TIME
            else None,
            int(info.BasicLimitInformation.PerJobUserTimeLimit)
            if flags & JOB_OBJECT_LIMIT_JOB_TIME
            else None,
            cpu_rate,
        )

    def collect_job_metrics(self, job: int) -> WindowsJobRuntimeMetricsV1:
        accounting = _BASIC_ACCOUNTING()
        returned = wintypes.DWORD()
        if not self._query_job(
            job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), ctypes.byref(returned)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        extended = _EXTENDED_LIMIT()
        if not self._query_job(
            job,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(extended),
            ctypes.sizeof(extended),
            ctypes.byref(returned),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return WindowsJobRuntimeMetricsV1(
            True,
            int(accounting.ActiveProcesses),
            int(accounting.TotalUserTime),
            int(accounting.TotalKernelTime),
            int(extended.PeakProcessMemoryUsed),
            int(extended.PeakJobMemoryUsed),
        )

    def prepare_stdio(
        self, command: ResolvedCommandV1, limits: WindowsOutputLimits
    ) -> WindowsPreparedStdio:
        child_handles: list[int] = []
        readers: dict[WindowsOutputStream, WindowsOutputReader] = {}
        drains: list[WindowsOutputReader] = []

        def output_handle(
            policy: SandboxProcessStdioPolicy,
            stream: WindowsOutputStream,
            limit: int,
        ) -> int:
            read = wintypes.HANDLE()
            write = wintypes.HANDLE()
            security = _SECURITY_ATTRIBUTES(ctypes.sizeof(_SECURITY_ATTRIBUTES), None, True)
            if not self._create_pipe(
                ctypes.byref(read), ctypes.byref(write), ctypes.byref(security), 0
            ):
                raise WindowsStdioSetupError("pipe_creation_failed")
            read_value, write_value = int(read.value or 0), int(write.value or 0)
            if not self._set_handle_information(read_value, HANDLE_FLAG_INHERIT, 0):
                self.close_handle(read_value)
                self.close_handle(write_value)
                raise WindowsStdioSetupError("inheritance_setup_failed")
            child_handles.append(write_value)
            fd = msvcrt.open_osfhandle(read_value, os.O_RDONLY | os.O_BINARY)
            source = os.fdopen(fd, "rb", buffering=0)
            if policy is SandboxProcessStdioPolicy.CAPTURED:
                readers[stream] = WindowsOutputReader(stream, source, limit)
            elif policy is SandboxProcessStdioPolicy.DISCARD:
                drains.append(WindowsOutputReader(stream, source, 0))
            else:
                source.close()
            return write_value

        stdout_handle = output_handle(
            command.stdout, WindowsOutputStream.STDOUT, limits.stdout_bytes
        )
        stderr_handle = output_handle(
            command.stderr, WindowsOutputStream.STDERR, limits.stderr_bytes
        )
        # stdin is an explicit EOF pipe; the parent never retains a write end.
        stdin_read = wintypes.HANDLE()
        stdin_write = wintypes.HANDLE()
        security = _SECURITY_ATTRIBUTES(ctypes.sizeof(_SECURITY_ATTRIBUTES), None, True)
        if not self._create_pipe(
            ctypes.byref(stdin_read), ctypes.byref(stdin_write), ctypes.byref(security), 0
        ):
            for handle in child_handles:
                self.close_handle(handle)
            raise WindowsStdioSetupError("pipe_creation_failed")
        self.close_handle(int(stdin_write.value or 0))
        stdin_handle = int(stdin_read.value or 0)
        child_handles.append(stdin_handle)
        capture = WindowsOutputCapture(
            readers.get(WindowsOutputStream.STDOUT),
            readers.get(WindowsOutputStream.STDERR),
            tuple(drains),
        )
        return WindowsPreparedStdio(
            stdin_handle,
            stdout_handle,
            stderr_handle,
            tuple(child_handles),
            tuple(child_handles),
            capture,
            self,
        )

    def create_process_suspended(
        self,
        command: ResolvedCommandV1,
        stdio: WindowsPreparedStdio | None = None,
        secret_environment: tuple[tuple[str, str], ...] = (),
    ) -> tuple[int, int, int]:
        startup_ex = _STARTUPINFOEXW()
        startup_ex.StartupInfo.cb = ctypes.sizeof(startup_ex)
        process = _PROCESS_INFORMATION()
        command_line = ctypes.create_unicode_buffer(command.windows_command_line)
        names = {name.casefold() for name, _ in command.environment}
        if any(name.casefold() in names for name, _ in secret_environment):
            raise OSError("secret_environment_collision")
        environment = ctypes.create_unicode_buffer(
            "\0".join(f"{k}={v}" for k, v in (*command.environment, *secret_environment)) + "\0\0"
        )
        inherit = stdio is not None
        flags = CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT
        attribute_buffer = None
        if stdio is not None:
            startup_ex.StartupInfo.dwFlags = STARTF_USESTDHANDLES
            startup_ex.StartupInfo.hStdInput = stdio.stdin_handle
            startup_ex.StartupInfo.hStdOutput = stdio.stdout_handle
            startup_ex.StartupInfo.hStdError = stdio.stderr_handle
            size = ctypes.c_size_t()
            self._initialize_attribute_list(None, 1, 0, ctypes.byref(size))
            attribute_buffer = ctypes.create_string_buffer(size.value)
            startup_ex.lpAttributeList = ctypes.cast(attribute_buffer, ctypes.c_void_p)
            if not self._initialize_attribute_list(
                startup_ex.lpAttributeList, 1, 0, ctypes.byref(size)
            ):
                raise WindowsStdioSetupError("inheritance_setup_failed")
            handles = (wintypes.HANDLE * len(stdio.inherited_handles))(*stdio.inherited_handles)
            if not self._update_attribute(
                startup_ex.lpAttributeList,
                0,
                PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                ctypes.byref(handles),
                ctypes.sizeof(handles),
                None,
                None,
            ):
                self._delete_attribute_list(startup_ex.lpAttributeList)
                raise WindowsStdioSetupError("inheritance_setup_failed")
            flags |= EXTENDED_STARTUPINFO_PRESENT
        try:
            ok = self._create_process(
                str(command.executable_path),
                command_line,
                None,
                None,
                inherit,
                flags,
                environment,
                str(command.working_directory),
                ctypes.byref(startup_ex.StartupInfo),
                ctypes.byref(process),
            )
            if not ok:
                raise ctypes.WinError(ctypes.get_last_error())
            return int(process.hProcess), int(process.hThread), int(process.dwProcessId)
        finally:
            if stdio is not None and startup_ex.lpAttributeList:
                self._delete_attribute_list(startup_ex.lpAttributeList)

    def assign_process(self, job: int, process: int) -> bool:
        return bool(self._assign(job, process))

    def process_in_job(self, process: int, job: int) -> bool:
        result = wintypes.BOOL()
        return bool(self._in_job(process, job, ctypes.byref(result))) and bool(result.value)

    def resume_thread(self, thread: int) -> bool:
        return self._resume(thread) != 0xFFFFFFFF

    def terminate_suspended(self, process: int) -> bool:
        return bool(self._terminate(process, 1))

    def close_handle(self, handle: int) -> bool:
        return bool(self._close(handle))

    def process_state(self, process: int) -> tuple[bool, int | None]:
        wait = self._wait(process, 0)
        if wait == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
        code = wintypes.DWORD()
        if not self._exit_code(process, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        active = wait == 0x102 and code.value == STILL_ACTIVE
        return active, None if active else int(code.value)

    def active_processes(self, job: int) -> tuple[int, tuple[int, ...]]:
        info = _BASIC_ACCOUNTING()
        returned = wintypes.DWORD()
        if not self._query_job(
            job, 1, ctypes.byref(info), ctypes.sizeof(info), ctypes.byref(returned)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(info.ActiveProcesses), ()

    def terminate_job(self, job: int, exit_code: int) -> bool:
        return bool(self._terminate_job(job, exit_code))
