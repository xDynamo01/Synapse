import hashlib

from .skills_support import package as _package
from .skills_support import runtime as _runtime


class Boundary:
    def __init__(self):
        self.calls = []

    def preview(self, descriptor, inputs, *, actor_id):
        self.calls.append(("preview", actor_id))
        return {"approval_required": True}

    def execute(self, descriptor, inputs, *, actor_id, approval_id=None):
        self.calls.append(("execute", approval_id))
        return {"status": "completed"}


def test_skill_script_uses_only_execution_boundary(tmp_path):
    runtime = _runtime(tmp_path)
    boundary = Boundary()
    runtime.script_execution = boundary
    package = _package(tmp_path, "script-boundary")
    script = package / "scripts" / "check.py"
    script.parent.mkdir()
    script.write_text("pass", encoding="utf-8")
    checksum = hashlib.sha256(script.read_bytes()).hexdigest()
    manifest = (package / "manifest.yaml").read_text(encoding="utf-8")
    (package / "manifest.yaml").write_text(
        manifest.replace(
            "scripts: []",
            f"scripts: [{{script_id: check, runtime: python, entrypoint: scripts/check.py, checksum: {checksum}, required_tools: [sandbox_run]}}]",
        ),
        encoding="utf-8",
    )
    runtime.install(package)
    assert runtime.preview_script("script-boundary", "1.0.0", "check", {}, actor_id="agent")[
        "approval_required"
    ]
    assert (
        runtime.execute_script(
            "script-boundary", "1.0.0", "check", {}, actor_id="agent", approval_id="approval-1"
        )["status"]
        == "completed"
    )
    assert boundary.calls == [("preview", "agent"), ("execute", "approval-1")]
