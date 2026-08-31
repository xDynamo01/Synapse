"""Read-only Windows command resolution; this module never starts a process."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

from synapse.sandbox import (
    OpaqueReference,
    SandboxArtifactFingerprint,
    SandboxFilesystemResource,
    SandboxLogicalPath,
    SandboxProcessStdioPolicy,
    SandboxWorkspaceId,
)

from .local_artifact_custody import fingerprint_local_artifact

COMMAND_RESOLUTION_VERSION = "windows-command-resolution-v1"


class WindowsExecutableClass(StrEnum):
    WORKSPACE_EXECUTABLE = "workspace-executable"
    HOST_EXECUTABLE = "host-executable"
    POWERSHELL_SCRIPT = "powershell-script"
    PYTHON_SCRIPT = "python-script"


class WindowsShellMode(StrEnum):
    DIRECT = "direct"
    POWERSHELL_FILE = "powershell-file"
    PYTHON_FILE = "python-file"


@dataclass(frozen=True, slots=True)
class WindowsEntrypointBinding:
    logical_name: str
    executable_class: WindowsExecutableClass
    executable_reference: OpaqueReference
    workspace_resource: SandboxFilesystemResource | None = None
    workspace_path: SandboxLogicalPath | None = None
    expected_fingerprint: SandboxArtifactFingerprint | None = None
    host_executable_name: str | None = None
    interpreter_name: str | None = None


@dataclass(frozen=True, slots=True)
class WindowsCommandPolicy:
    direct_executable: bool = True
    powershell: bool = False
    python: bool = False
    cmd_batch: bool = False
    maximum_arguments: int = 128
    maximum_argument_bytes: int = 32_768
    maximum_environment_bytes: int = 32_768
    maximum_command_line_units: int = 32_767


@dataclass(frozen=True, slots=True)
class WindowsCommandConfig:
    workspace_root: Path
    entrypoints: tuple[WindowsEntrypointBinding, ...]
    host_executables: tuple[tuple[str, Path], ...] = ()
    base_environment: tuple[tuple[str, str], ...] = ()
    environment_values: tuple[tuple[OpaqueReference, str], ...] = ()
    secret_references: tuple[OpaqueReference, ...] = ()
    policy: WindowsCommandPolicy = WindowsCommandPolicy()
    config_version: str = COMMAND_RESOLUTION_VERSION


@dataclass(frozen=True, slots=True)
class ResolveWindowsCommandRequest:
    plan_reference: OpaqueReference
    workload_reference: OpaqueReference
    attempt_reference: OpaqueReference
    workspace_id: SandboxWorkspaceId
    logical_entrypoint: str
    arguments: tuple[str, ...]
    working_root: SandboxFilesystemResource
    working_path: SandboxLogicalPath | None
    environment: tuple[tuple[str, OpaqueReference], ...]
    stdin: SandboxProcessStdioPolicy
    stdout: SandboxProcessStdioPolicy
    stderr: SandboxProcessStdioPolicy
    occurrence_reference: OpaqueReference


@dataclass(frozen=True, slots=True)
class ResolvedCommandV1:
    plan_reference: OpaqueReference
    workload_reference: OpaqueReference
    attempt_reference: OpaqueReference
    workspace_id: SandboxWorkspaceId
    executable_reference: OpaqueReference
    executable_path: Path
    integrity_bindings: tuple[tuple[Path, SandboxArtifactFingerprint], ...]
    argv: tuple[str, ...]
    windows_command_line: str
    working_directory: Path
    environment: tuple[tuple[str, str], ...]
    stdin: SandboxProcessStdioPolicy
    stdout: SandboxProcessStdioPolicy
    stderr: SandboxProcessStdioPolicy
    shell_mode: WindowsShellMode
    command_fingerprint: SandboxArtifactFingerprint
    occurrence_reference: OpaqueReference
    config_version: str
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WindowsCommandResolutionResult:
    command: ResolvedCommandV1 | None
    diagnostic_codes: tuple[str, ...]
    secret_materialization_required: bool = False


@dataclass(frozen=True, slots=True)
class WindowsCommandResolutionHealth:
    resolver_implemented: bool
    direct_executable_supported: bool
    host_executable_supported: bool
    python_interpreter_supported: bool
    powershell_supported: bool
    cmd_batch_supported: bool
    environment_resolution_supported: bool
    secret_materialization_available: bool = False
    process_execution_available: bool = False


class WindowsCommandResolver:
    _RESOURCE = {
        SandboxFilesystemResource.ARTIFACT: "input",
        SandboxFilesystemResource.INPUT: "input",
        SandboxFilesystemResource.WORKSPACE: "work",
        SandboxFilesystemResource.OUTPUT: "output",
        SandboxFilesystemResource.TEMPORARY: "temp",
        SandboxFilesystemResource.STATE: "state",
    }

    def __init__(self, config: WindowsCommandConfig) -> None:
        self._root = config.workspace_root.resolve(strict=False)
        self._entrypoints = {item.logical_name: item for item in config.entrypoints}
        self._host = {name.casefold(): path.resolve(strict=False) for name, path in config.host_executables}
        self._base = config.base_environment
        self._values = dict(config.environment_values)
        self._secrets = set(config.secret_references)
        self._policy = config.policy
        self._version = config.config_version

    def health(self) -> WindowsCommandResolutionHealth:
        return WindowsCommandResolutionHealth(
            True,
            self._policy.direct_executable,
            bool(self._host),
            self._policy.python,
            self._policy.powershell,
            self._policy.cmd_batch,
            True,
        )

    def resolve(self, request: ResolveWindowsCommandRequest) -> WindowsCommandResolutionResult:
        binding = self._entrypoints.get(request.logical_entrypoint)
        if binding is None:
            return self._failed("entrypoint_unresolved")
        try:
            executable, prefix, mode, integrity = self._resolve_executable(request, binding)
            arguments = self._arguments(request.arguments)
            cwd = self._workspace_path(
                request.workspace_id, request.working_root, request.working_path
            )
            environment = self._environment(request.environment)
            argv = (*prefix, *arguments)
            command_line = windows_command_line(argv)
            if len(command_line) > self._policy.maximum_command_line_units:
                return self._failed("command_line_too_large")
            semantic = (
                COMMAND_RESOLUTION_VERSION,
                request.plan_reference,
                request.workload_reference,
                request.attempt_reference,
                request.workspace_id,
                binding.executable_reference,
                tuple(argv),
                request.working_root,
                request.working_path,
                tuple((name, SandboxArtifactFingerprint.from_content(value)) for name, value in environment),
                request.stdin,
                request.stdout,
                request.stderr,
                mode,
                self._version,
            )
            fingerprint = SandboxArtifactFingerprint.from_content(semantic)
            return WindowsCommandResolutionResult(
                ResolvedCommandV1(
                    request.plan_reference,
                    request.workload_reference,
                    request.attempt_reference,
                    request.workspace_id,
                    binding.executable_reference,
                    executable,
                    integrity,
                    tuple(argv),
                    command_line,
                    cwd,
                    environment,
                    request.stdin,
                    request.stdout,
                    request.stderr,
                    mode,
                    fingerprint,
                    request.occurrence_reference,
                    self._version,
                    (
                        "resolved-command-is-not-execution-authorization",
                        "fencing-must-be-revalidated-before-process-start",
                    ),
                ),
                (),
            )
        except _ResolutionError as error:
            return self._failed(error.code, secret=error.secret)

    def _resolve_executable(
        self,
        request: ResolveWindowsCommandRequest,
        binding: WindowsEntrypointBinding,
    ) -> tuple[
        Path,
        tuple[str, ...],
        WindowsShellMode,
        tuple[tuple[Path, SandboxArtifactFingerprint], ...],
    ]:
        if binding.executable_class is WindowsExecutableClass.HOST_EXECUTABLE:
            if not self._policy.direct_executable:
                raise _ResolutionError("grant_capability_mismatch")
            executable = self._host_path(binding.host_executable_name)
            return executable, (str(executable),), WindowsShellMode.DIRECT, (
                (executable, fingerprint_local_artifact(executable)),
            )
        script = self._bound_workspace_file(request.workspace_id, binding)
        assert binding.expected_fingerprint is not None
        script_fingerprint = binding.expected_fingerprint
        suffix = script.suffix.casefold()
        if binding.executable_class is WindowsExecutableClass.WORKSPACE_EXECUTABLE:
            if not self._policy.direct_executable or suffix not in {".exe", ".com"}:
                raise _ResolutionError("unsupported_executable_type")
            return script, (str(script),), WindowsShellMode.DIRECT, (
                (script, script_fingerprint),
            )
        if binding.executable_class is WindowsExecutableClass.POWERSHELL_SCRIPT:
            if suffix != ".ps1" or not self._policy.powershell:
                raise _ResolutionError("shell_not_allowed")
            interpreter = self._host_path(binding.interpreter_name)
            return interpreter, (str(interpreter), "-File", str(script)), WindowsShellMode.POWERSHELL_FILE, (
                (interpreter, fingerprint_local_artifact(interpreter)),
                (script, script_fingerprint),
            )
        if binding.executable_class is WindowsExecutableClass.PYTHON_SCRIPT:
            if suffix != ".py" or not self._policy.python:
                raise _ResolutionError("interpreter_unavailable")
            interpreter = self._host_path(binding.interpreter_name)
            return interpreter, (str(interpreter), str(script)), WindowsShellMode.PYTHON_FILE, (
                (interpreter, fingerprint_local_artifact(interpreter)),
                (script, script_fingerprint),
            )
        raise _ResolutionError("unsupported_executable_type")

    def _bound_workspace_file(
        self, workspace: SandboxWorkspaceId, binding: WindowsEntrypointBinding
    ) -> Path:
        if binding.workspace_resource is None or binding.workspace_path is None or binding.expected_fingerprint is None:
            raise _ResolutionError("entrypoint_unresolved")
        path = self._workspace_path(workspace, binding.workspace_resource, binding.workspace_path)
        if not path.is_file():
            raise _ResolutionError("executable_unavailable")
        try:
            observed = fingerprint_local_artifact(path)
        except (OSError, ValueError):
            raise _ResolutionError("executable_unavailable") from None
        if observed != binding.expected_fingerprint:
            raise _ResolutionError("executable_fingerprint_stale")
        return path

    def _host_path(self, name: str | None) -> Path:
        if name is None or name.casefold() not in self._host:
            raise _ResolutionError("interpreter_unavailable")
        path = self._host[name.casefold()]
        if not path.is_file() or _is_reparse(path):
            raise _ResolutionError("executable_unavailable")
        return path

    def _workspace_path(
        self,
        workspace: SandboxWorkspaceId,
        resource: SandboxFilesystemResource,
        logical: SandboxLogicalPath | None,
    ) -> Path:
        if resource not in self._RESOURCE:
            raise _ResolutionError("cwd_invalid")
        workspace_root = self._root / workspace.value.replace(":", "-")
        target = workspace_root / self._RESOURCE[resource]
        if logical is not None:
            relative = PurePosixPath(logical.value)
            if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
                raise _ResolutionError("cwd_invalid")
            target = target.joinpath(*relative.parts)
        resolved = target.resolve(strict=False)
        if not resolved.is_relative_to(workspace_root.resolve(strict=False)):
            raise _ResolutionError("cwd_outside_workspace")
        current = target
        while current != workspace_root.parent:
            if current.exists() and _is_reparse(current):
                raise _ResolutionError("cwd_outside_workspace")
            if current == workspace_root:
                break
            current = current.parent
        if not target.exists():
            raise _ResolutionError("cwd_invalid")
        return target

    def _arguments(self, arguments: tuple[str, ...]) -> tuple[str, ...]:
        if len(arguments) > self._policy.maximum_arguments:
            raise _ResolutionError("argument_invalid")
        if any("\0" in value or any(ord(char) < 32 for char in value) for value in arguments):
            raise _ResolutionError("argument_invalid")
        if sum(len(value.encode("utf-16-le")) for value in arguments) > self._policy.maximum_argument_bytes:
            raise _ResolutionError("command_line_too_large")
        return arguments

    def _environment(
        self, requested: tuple[tuple[str, OpaqueReference], ...]
    ) -> tuple[tuple[str, str], ...]:
        values: dict[str, tuple[str, str]] = {}
        for name, value in self._base:
            self._add_environment(values, name, value)
        for name, reference in requested:
            if reference in self._secrets:
                raise _ResolutionError("secret_materialization_required", secret=True)
            if reference not in self._values:
                raise _ResolutionError("environment_invalid")
            self._add_environment(values, name, self._values[reference])
        result = tuple(sorted(values.values(), key=lambda item: item[0].casefold()))
        units = sum(len(name) + len(value) + 2 for name, value in result) + 1
        if units > self._policy.maximum_environment_bytes:
            raise _ResolutionError("environment_too_large")
        return result

    @staticmethod
    def _add_environment(
        values: dict[str, tuple[str, str]], name: str, value: str
    ) -> None:
        if not name or "=" in name or "\0" in name or "\0" in value:
            raise _ResolutionError("environment_invalid")
        key = name.casefold()
        if key in values:
            raise _ResolutionError("environment_case_collision")
        values[key] = (name.upper(), value)

    @staticmethod
    def _failed(code: str, *, secret: bool = False) -> WindowsCommandResolutionResult:
        return WindowsCommandResolutionResult(None, (code,), secret)


class _ResolutionError(RuntimeError):
    def __init__(self, code: str, *, secret: bool = False) -> None:
        self.code = code
        self.secret = secret


def windows_quote_argument(argument: str) -> str:
    quote = not argument or " " in argument or "\t" in argument
    result = '"' if quote else ""
    backslashes = 0
    for character in argument:
        if character == "\\":
            backslashes += 1
        elif character == '"':
            result += "\\" * (backslashes * 2 + 1) + '"'
            backslashes = 0
        else:
            result += "\\" * backslashes + character
            backslashes = 0
    result += "\\" * (backslashes * 2 if quote else backslashes)
    return result + ('"' if quote else "")


def windows_command_line(argv: tuple[str, ...]) -> str:
    return " ".join(windows_quote_argument(argument) for argument in argv)


def _is_reparse(path: Path) -> bool:
    attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
