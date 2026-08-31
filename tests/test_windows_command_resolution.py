from __future__ import annotations

from dataclasses import replace

import pytest

from synapse.sandbox import (
    OpaqueReference,
    SandboxFilesystemResource,
    SandboxLogicalPath,
    SandboxProcessStdioPolicy,
    SandboxWorkspaceId,
)
from synapse.sandbox_drivers import (
    ResolveWindowsCommandRequest,
    WindowsCommandConfig,
    WindowsCommandPolicy,
    WindowsCommandResolver,
    WindowsEntrypointBinding,
    WindowsExecutableClass,
    WindowsShellMode,
    fingerprint_local_artifact,
    windows_command_line,
)


def _workspace(tmp_path):
    root = tmp_path / "workspaces"
    workspace = SandboxWorkspaceId("workspace:command")
    physical = root / "workspace-command"
    for name in ("input", "work", "output", "temp", "state"):
        (physical / name).mkdir(parents=True)
    return root, workspace, physical


def _request(workspace, entrypoint="app", arguments=(), environment=()):
    return ResolveWindowsCommandRequest(
        OpaqueReference("plan:one"),
        OpaqueReference("workload:one"),
        OpaqueReference("attempt:one"),
        workspace,
        entrypoint,
        arguments,
        SandboxFilesystemResource.WORKSPACE,
        None,
        environment,
        SandboxProcessStdioPolicy.CLOSED,
        SandboxProcessStdioPolicy.CAPTURED,
        SandboxProcessStdioPolicy.CAPTURED,
        OpaqueReference("occurrence:one"),
    )


def _binding(path, *, kind=WindowsExecutableClass.WORKSPACE_EXECUTABLE, name="app", interpreter=None):
    return WindowsEntrypointBinding(
        name,
        kind,
        OpaqueReference("executable:" + name),
        SandboxFilesystemResource.INPUT,
        SandboxLogicalPath.parse(path.name, case_sensitive=False),
        fingerprint_local_artifact(path),
        interpreter_name=interpreter,
    )


def test_materialized_exe_resolves_structured_argv_without_execution(tmp_path) -> None:
    root, workspace, physical = _workspace(tmp_path)
    executable = physical / "input" / "app.exe"
    executable.write_bytes(b"inert")
    resolver = WindowsCommandResolver(
        WindowsCommandConfig(root, (_binding(executable),))
    )
    request = _request(
        workspace, arguments=("space value", "", 'quote"value', "C:\\path\\", "ação")
    )
    result = resolver.resolve(request)
    assert result.command is not None
    assert result.command.argv[1:] == request.arguments
    assert result.command.shell_mode is WindowsShellMode.DIRECT
    assert result.command.windows_command_line == windows_command_line(result.command.argv)
    assert not hasattr(resolver, "execute")


def test_host_executable_requires_exact_allowlist_and_never_global_path(tmp_path) -> None:
    root, workspace, _ = _workspace(tmp_path)
    host = tmp_path / "host.exe"
    host.write_bytes(b"host")
    binding = WindowsEntrypointBinding(
        "host", WindowsExecutableClass.HOST_EXECUTABLE, OpaqueReference("executable:host"), host_executable_name="tool"
    )
    allowed = WindowsCommandResolver(
        WindowsCommandConfig(root, (binding,), (("tool", host),))
    )
    assert allowed.resolve(_request(workspace, "host")).command is not None
    denied = WindowsCommandResolver(WindowsCommandConfig(root, (binding,)))
    assert denied.resolve(_request(workspace, "host")).diagnostic_codes == (
        "interpreter_unavailable",
    )


def test_powershell_python_and_batch_policy_are_explicit(tmp_path) -> None:
    root, workspace, physical = _workspace(tmp_path)
    powershell = tmp_path / "powershell.exe"
    python = tmp_path / "python.exe"
    powershell.write_bytes(b"host")
    python.write_bytes(b"host")
    ps1 = physical / "input" / "script.ps1"
    py = physical / "input" / "script.py"
    cmd = physical / "input" / "script.cmd"
    for path in (ps1, py, cmd):
        path.write_text("inert")
    bindings = (
        _binding(ps1, kind=WindowsExecutableClass.POWERSHELL_SCRIPT, name="ps", interpreter="powershell"),
        _binding(py, kind=WindowsExecutableClass.PYTHON_SCRIPT, name="py", interpreter="python"),
        _binding(cmd, name="batch"),
    )
    denied = WindowsCommandResolver(WindowsCommandConfig(root, bindings))
    assert denied.resolve(_request(workspace, "ps")).diagnostic_codes == ("shell_not_allowed",)
    assert denied.resolve(_request(workspace, "batch")).diagnostic_codes == ("unsupported_executable_type",)
    allowed = WindowsCommandResolver(
        WindowsCommandConfig(
            root,
            bindings,
            (("powershell", powershell), ("python", python)),
            policy=WindowsCommandPolicy(powershell=True, python=True),
        )
    )
    ps = allowed.resolve(_request(workspace, "ps")).command
    py_result = allowed.resolve(_request(workspace, "py")).command
    assert ps is not None and ps.argv[1] == "-File"
    assert py_result is not None and py_result.shell_mode is WindowsShellMode.PYTHON_FILE


def test_unknown_entrypoint_stale_executable_and_wrong_workspace_fail(tmp_path) -> None:
    root, workspace, physical = _workspace(tmp_path)
    executable = physical / "input" / "app.exe"
    executable.write_bytes(b"before")
    resolver = WindowsCommandResolver(WindowsCommandConfig(root, (_binding(executable),)))
    assert resolver.resolve(_request(workspace, "missing")).diagnostic_codes == ("entrypoint_unresolved",)
    executable.write_bytes(b"after")
    assert resolver.resolve(_request(workspace)).diagnostic_codes == ("executable_fingerprint_stale",)
    assert resolver.resolve(_request(SandboxWorkspaceId("workspace:other"))).diagnostic_codes == ("cwd_invalid",)


def test_cwd_is_workspace_contained_and_environment_is_minimal(tmp_path, monkeypatch) -> None:
    root, workspace, physical = _workspace(tmp_path)
    executable = physical / "input" / "app.exe"
    executable.write_bytes(b"app")
    reference = OpaqueReference("environment:mode")
    monkeypatch.setenv("HOST_SECRET_TOKEN", "must-not-leak")
    resolver = WindowsCommandResolver(
        WindowsCommandConfig(
            root,
            (_binding(executable),),
            base_environment=(("SYSTEMROOT", "C:\\Windows"),),
            environment_values=((reference, "safe"),),
        )
    )
    command = resolver.resolve(_request(workspace, environment=(("MODE", reference),))).command
    assert command is not None
    assert command.environment == (("MODE", "safe"), ("SYSTEMROOT", "C:\\Windows"))
    assert "HOST_SECRET_TOKEN" not in dict(command.environment)
    with pytest.raises(ValueError):
        SandboxLogicalPath.parse("../outside", case_sensitive=False)


def test_environment_collision_invalid_names_limits_and_secret_refs(tmp_path) -> None:
    root, workspace, physical = _workspace(tmp_path)
    executable = physical / "input" / "app.exe"
    executable.write_bytes(b"app")
    one = OpaqueReference("environment:one")
    secret = OpaqueReference("secret:one")
    resolver = WindowsCommandResolver(
        WindowsCommandConfig(
            root,
            (_binding(executable),),
            environment_values=((one, "value"),),
            secret_references=(secret,),
            policy=WindowsCommandPolicy(maximum_environment_bytes=10),
        )
    )
    collision = _request(workspace, environment=(("Mode", one), ("MODE", one)))
    assert resolver.resolve(collision).diagnostic_codes == ("environment_case_collision",)
    assert resolver.resolve(_request(workspace, environment=(("BAD=NAME", one),))).diagnostic_codes == ("environment_invalid",)
    secret_result = resolver.resolve(_request(workspace, environment=(("TOKEN", secret),)))
    assert secret_result.secret_materialization_required
    assert "secret:one" not in repr(secret_result)
    assert resolver.resolve(_request(workspace, environment=(("LONG", one),))).diagnostic_codes == ("environment_too_large",)


def test_command_fingerprint_is_deterministic_and_excludes_occurrence(tmp_path) -> None:
    root, workspace, physical = _workspace(tmp_path)
    executable = physical / "input" / "app.exe"
    executable.write_bytes(b"app")
    resolver = WindowsCommandResolver(WindowsCommandConfig(root, (_binding(executable),)))
    first = resolver.resolve(_request(workspace)).command
    second = resolver.resolve(
        replace(_request(workspace), occurrence_reference=OpaqueReference("occurrence:two"))
    ).command
    assert first is not None and second is not None
    assert first.command_fingerprint == second.command_fingerprint
    assert first.occurrence_reference != second.occurrence_reference


@pytest.mark.parametrize(
    "argv",
    [
        ("app.exe", "space value", ""),
        ("app.exe", 'a"b', r"ends\\"),
        ("app.exe", "Unicode-ação"),
    ],
)
def test_windows_quoting_matches_stdlib_list2cmdline(argv) -> None:
    import subprocess

    assert windows_command_line(argv) == subprocess.list2cmdline(argv)
