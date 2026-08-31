from __future__ import annotations

import ctypes
import io
import os
import sys
import threading
from pathlib import Path

import pytest
from tests.factories.windows_authority import process_context
from tests.test_windows_process_driver import Authorization, FakeApi, Fencing

from synapse.sandbox import (
    OpaqueReference,
    SandboxFilesystemResource,
    SandboxLogicalPath,
    SandboxProcessStdioPolicy,
    SandboxWorkspaceId,
)
from synapse.sandbox_drivers import (
    NativeWindowsProcessApi,
    ResolveWindowsCommandRequest,
    WindowsCommandConfig,
    WindowsCommandPolicy,
    WindowsCommandResolver,
    WindowsEntrypointBinding,
    WindowsExecutableClass,
    WindowsOutputCapture,
    WindowsOutputDecodingStatus,
    WindowsOutputLimits,
    WindowsOutputReader,
    WindowsOutputState,
    WindowsOutputStream,
    WindowsProcessDriver,
    WindowsProcessStartOutcome,
    WindowsProcessStartRequest,
    WindowsStdioSetupError,
    fingerprint_local_artifact,
)


class FailingReader(io.BytesIO):
    def read(self, size=-1):
        raise OSError("sensitive raw payload must not escape")


class BlockingReader(io.BytesIO):
    def __init__(self) -> None:
        super().__init__()
        self.release = threading.Event()

    def read(self, size=-1):
        self.release.wait()
        return b""


class CountingReader(io.BytesIO):
    def __init__(self, value: bytes) -> None:
        super().__init__(value)
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1
        super().close()


@pytest.mark.parametrize(
    ("payload", "limit", "truncated", "retained"),
    [
        (b"", 4, False, b""),
        (b"abcd", 4, False, b"abcd"),
        (b"abcde", 4, True, b"abcd"),
        (b"x" * 2_000_000, 32, True, b"x" * 32),
        (b"a\r\nb\n", 16, False, b"a\r\nb\n"),
    ],
    ids=("empty", "exact-limit", "one-over", "very-large", "raw-newlines"),
)
def test_reader_is_bounded_binary_safe_and_reports_truncation(
    payload, limit, truncated, retained
) -> None:
    reader = WindowsOutputReader(WindowsOutputStream.STDOUT, io.BytesIO(payload), limit)
    assert reader.start()
    result = reader.finalize(2)
    assert result.retained_bytes == retained
    assert result.bytes_retained <= limit
    assert result.bytes_observed == len(payload)
    assert result.truncated is truncated
    assert result.state is WindowsOutputState.FINALIZED
    assert len(result.retained_checksum) == 64
    assert len(result.capture_fingerprint) == 64


def test_invalid_utf8_preserves_raw_bytes_and_text_projection_is_optional() -> None:
    reader = WindowsOutputReader(WindowsOutputStream.STDERR, io.BytesIO(b"\xff\x00"), 8)
    reader.start()
    result = reader.finalize(2)
    assert result.retained_bytes == b"\xff\x00"
    assert result.decoding_status is WindowsOutputDecodingStatus.INVALID_UTF8
    assert result.decode_utf8() is None


def test_stdout_and_stderr_drain_concurrently_without_global_order_claim() -> None:
    capture = WindowsOutputCapture(
        WindowsOutputReader(WindowsOutputStream.STDOUT, io.BytesIO(b"a" * 500_000), 10),
        WindowsOutputReader(WindowsOutputStream.STDERR, io.BytesIO(b"b" * 500_000), 11),
    )
    assert capture.start()
    stdout, stderr = capture.finalize(2)
    assert stdout.stream is WindowsOutputStream.STDOUT
    assert stderr.stream is WindowsOutputStream.STDERR
    assert stdout.bytes_observed == stderr.bytes_observed == 500_000
    assert stdout.bytes_retained == 10 and stderr.bytes_retained == 11


def test_reader_failure_is_not_projected_as_empty_valid_output_or_leaked() -> None:
    reader = WindowsOutputReader(WindowsOutputStream.STDOUT, FailingReader(), 10)
    reader.start()
    result = reader.finalize(2)
    assert result.state is WindowsOutputState.FAILED
    assert result.diagnostics == ("read_failed",)
    assert "sensitive" not in repr(result)


def test_open_descendant_pipe_is_incomplete_without_blocking_indefinitely() -> None:
    source = BlockingReader()
    reader = WindowsOutputReader(WindowsOutputStream.STDOUT, source, 10)
    reader.start()
    result = reader.finalize(0.01)
    assert result.state is WindowsOutputState.INCOMPLETE
    assert result.diagnostics == ("output_incomplete",)
    source.release.set()
    assert reader.finalize(2).state is WindowsOutputState.FINALIZED


def test_cleanup_is_idempotent_and_close_failure_is_factual() -> None:
    source = CountingReader(b"")
    reader = WindowsOutputReader(WindowsOutputStream.STDOUT, source, 1)
    reader.start()
    reader.finalize(2)
    assert reader.close() and reader.close()
    assert source.close_calls == 1


def _native_command(tmp_path: Path, source: str):
    root = tmp_path / "workspaces"
    workspace = SandboxWorkspaceId("workspace:output")
    physical = root / "workspace-output"
    for name in ("input", "work", "output", "temp", "state"):
        (physical / name).mkdir(parents=True)
    script = physical / "input" / "emit.py"
    script.write_text(source, encoding="utf-8")
    binding = WindowsEntrypointBinding(
        "emit",
        WindowsExecutableClass.PYTHON_SCRIPT,
        OpaqueReference("executable:emit"),
        SandboxFilesystemResource.INPUT,
        SandboxLogicalPath.parse("emit.py", case_sensitive=False),
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
            OpaqueReference("plan:output"),
            OpaqueReference("workload:output"),
            OpaqueReference("attempt:output"),
            workspace,
            "emit",
            (),
            SandboxFilesystemResource.WORKSPACE,
            None,
            (),
            SandboxProcessStdioPolicy.CLOSED,
            SandboxProcessStdioPolicy.CAPTURED,
            SandboxProcessStdioPolicy.CAPTURED,
            OpaqueReference("occurrence:output"),
        )
    ).command
    assert command is not None
    return workspace, command


@pytest.mark.parametrize("code", ("pipe_creation_failed", "inheritance_setup_failed"))
def test_stdio_setup_failures_never_start_or_leak_raw_output(tmp_path, code) -> None:
    class SetupFailureApi(FakeApi):
        def prepare_stdio(self, command, limits):
            raise WindowsStdioSetupError(code)

    workspace, command = _native_command(tmp_path, "print('not started')\n")
    api = SetupFailureApi()
    grant = OpaqueReference("grant:output")
    result = WindowsProcessDriver(
        api, Authorization(), Fencing(), platform_available=True
    ).start(
        WindowsProcessStartRequest(
            command,
            grant,
            command.command_fingerprint,
            workspace,
            OpaqueReference("driver-attempt:setup-failure"),
            authority_context=process_context(command, workspace, grant),
        )
    )
    assert result.diagnostic_codes == (code,)
    assert not result.process_created and "create_suspended" not in api.calls
    assert "not started" not in repr(result)


@pytest.mark.skipif(os.name != "nt", reason="Win32 smoke requires Windows")
def test_native_stdout_stderr_binary_truncation_and_simultaneous_volume(tmp_path) -> None:
    workspace, command = _native_command(
        tmp_path,
        "import os\n"
        "os.write(1, b'out\\xff\\r\\n' + b'x' * 200000)\n"
        "os.write(2, b'err\\x00\\n' + b'y' * 200000)\n",
    )
    grant = OpaqueReference("grant:output")
    result = WindowsProcessDriver(
        NativeWindowsProcessApi(), Authorization(), Fencing()
    ).start(
        WindowsProcessStartRequest(
            command,
            grant,
            command.command_fingerprint,
            workspace,
            OpaqueReference("driver-attempt:output"),
            output_limits=WindowsOutputLimits(32, 33),
            authority_context=process_context(command, workspace, grant),
        )
    )
    assert result.outcome is WindowsProcessStartOutcome.STARTED
    assert result.managed_process is not None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    assert kernel32.WaitForSingleObject(result.managed_process.process_handle, 10_000) == 0
    capture = result.managed_process.output_capture
    assert capture is not None
    stdout, stderr = capture.finalize(5)
    assert stdout.retained_bytes.startswith(b"out\xff\r\n")
    assert stderr.retained_bytes.startswith(b"err\x00\n")
    assert stdout.truncated and stderr.truncated
    assert stdout.bytes_observed > stdout.configured_limit
    assert stderr.bytes_observed > stderr.configured_limit
    assert result.managed_process.close_custody_handles()


@pytest.mark.skipif(os.name != "nt", reason="Win32 smoke requires Windows")
def test_native_root_exit_with_descendant_pipe_is_incomplete_until_job_termination(tmp_path) -> None:
    workspace, command = _native_command(
        tmp_path,
        "import subprocess, sys\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        "print('root-exit')\n",
    )
    api = NativeWindowsProcessApi()
    grant = OpaqueReference("grant:output")
    result = WindowsProcessDriver(api, Authorization(), Fencing()).start(
        WindowsProcessStartRequest(
            command,
            grant,
            command.command_fingerprint,
            workspace,
            OpaqueReference("driver-attempt:descendant"),
            output_limits=WindowsOutputLimits(128, 128),
            authority_context=process_context(command, workspace, grant),
        )
    )
    assert result.managed_process is not None
    managed = result.managed_process
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    assert kernel32.WaitForSingleObject(managed.process_handle, 10_000) == 0
    first = managed.finalize_output(0.01)
    assert first and any(item.state is WindowsOutputState.INCOMPLETE for item in first)
    assert api.terminate_job(managed.job_handle, 1)
    final = managed.finalize_output(5)
    assert all(item.state is WindowsOutputState.FINALIZED for item in final)
    assert managed.close_custody_handles()
