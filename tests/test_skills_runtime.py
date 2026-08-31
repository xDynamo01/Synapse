from __future__ import annotations

import hashlib
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from synapse.bootstrap.adapters.skills import SkillRecordStoreAdapter
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.project_governance.models import ProjectContext
from synapse.skills.errors import (
    SkillConflict,
    SkillContextBudgetExceeded,
    SkillDependencyCycle,
    SkillIdConflict,
    SkillInUse,
    SkillPackageInvalid,
)
from synapse.skills.models import (
    SkillAssignment,
    SkillLoadRequest,
    SkillResolutionRequest,
    SkillScope,
)
from synapse.skills.runtime import SkillsRuntime
from synapse.storage.collection import FileCollection


def _runtime(tmp_path: Path) -> SkillsRuntime:
    data_dir = DataDir(tmp_path)
    data_dir.bootstrap()
    events = EventBus(tmp_path)
    stores = {
        name: SkillRecordStoreAdapter(
            FileCollection(
                collection_id=f"skill_{name}",
                root=tmp_path / "skills" / name,
                current_schema_version=1,
                events=events,
            )
        )
        for name in ("assignments", "leases", "installations")
    }
    return SkillsRuntime(
        data_dir,
        events,
        assignments=stores["assignments"],
        leases=stores["leases"],
        installations=stores["installations"],
    )


def _package(
    root: Path,
    skill_id: str,
    *,
    version: str = "1.0.0",
    dependencies: str = "[]",
    conflicts: str = "[]",
    tools: str = "[]",
    capabilities: str = "[]",
    instructions: str = "Use the documented workflow.",
) -> Path:
    package = root / "skills" / "candidates" / f"{skill_id}-{version}"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text(f"# {skill_id}\n\n{instructions}\n", encoding="utf-8")
    (package / "references").mkdir()
    (package / "references" / "guide.md").write_text("guide", encoding="utf-8")
    (package / "manifest.yaml").write_text(
        f"""skill_id: {skill_id}
name: {skill_id}
version: {version}
description: Professional {skill_id} workflow
summary: Deterministic {skill_id} guidance
authorship: [synapse]
status: active
scopes: [system, agent, project, mission, task]
supported_agent_kinds: [primary, persistent, ephemeral]
activation:
  keywords: [{skill_id.replace("-", ", ")}]
requirements: {{}}
dependencies: {dependencies}
conflicts: {conflicts}
tools: {tools}
capabilities: {capabilities}
providers: []
references: [references/guide.md]
resources: []
scripts: []
context_policy:
  max_tokens: 2000
permissions: []
compatibility:
  agent_skills: partial
metadata:
  tags: [workflow]
""",
        encoding="utf-8",
    )
    return package


def test_package_install_discovery_progressive_load_and_restart(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    source = _package(tmp_path, "architecture-review")
    inspected = runtime.inspect("skills/candidates/architecture-review-1.0.0")
    assert inspected.manifest.skill_id == "architecture-review"
    installed = runtime.install(source)
    assert installed.installed
    assert runtime.list("architecture review")[0].skill_id == "architecture-review"
    metadata = runtime.load(SkillLoadRequest("architecture-review", "1.0.0", "metadata_only"))
    assert metadata.instructions == "" and metadata.loaded == ("manifest",)
    loaded = runtime.load(SkillLoadRequest("architecture-review", "1.0.0", "references"))
    assert "documented workflow" in loaded.instructions
    assert loaded.references == {"references/guide.md": "guide"}
    assert not loaded.resources and not loaded.scripts
    restarted = _runtime(tmp_path)
    assert restarted.get("architecture-review", "1.0.0").checksum == installed.checksum


def test_invalid_missing_files_unsafe_paths_duplicate_and_budget(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    package = _package(tmp_path, "safe-skill")
    runtime.install(package)
    with pytest.raises(SkillIdConflict):
        runtime.install(package)
    with pytest.raises(SkillContextBudgetExceeded):
        runtime.load(SkillLoadRequest("safe-skill", "1.0.0", context_budget=1))
    invalid = _package(tmp_path, "unsafe-skill")
    text = (invalid / "manifest.yaml").read_text(encoding="utf-8")
    (invalid / "manifest.yaml").write_text(
        text.replace("references/guide.md", "../secret.md"), encoding="utf-8"
    )
    with pytest.raises(SkillPackageInvalid):
        runtime.inspect(invalid)
    missing = tmp_path / "skills" / "candidates" / "missing"
    missing.mkdir()
    (missing / "manifest.yaml").write_text("skill_id: missing", encoding="utf-8")
    with pytest.raises(SkillPackageInvalid):
        runtime.inspect(missing)


def test_deterministic_resolve_dependencies_requirements_and_conflicts(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.install(_package(tmp_path, "base-review"))
    dependency = "[{skill_id: base-review, version_constraint: '^1.0.0'}]"
    runtime.install(
        _package(
            tmp_path,
            "python-review",
            dependencies=dependency,
            tools="[read_file]",
            capabilities="[code_review]",
        )
    )
    rejected = runtime.resolve(
        SkillResolutionRequest("review python", explicit_skill_ids=("python-review",))
    )
    assert rejected.rejected[0]["reason"] == "requirements_unavailable"
    result = runtime.resolve(
        SkillResolutionRequest(
            "review python",
            explicit_skill_ids=("python-review",),
            available_tools=("read_file",),
            capabilities=("code_review",),
        )
    )
    assert result.ordering == ("base-review", "python-review")
    runtime.install(
        _package(
            tmp_path,
            "conflicting-review",
            conflicts="[{skill_id: python-review, severity: critical}]",
        )
    )
    with pytest.raises(SkillConflict):
        runtime.resolve(
            SkillResolutionRequest(
                "review",
                explicit_skill_ids=("python-review", "conflicting-review"),
                available_tools=("read_file",),
                capabilities=("code_review",),
            )
        )


def test_dependency_cycle_is_structured(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.install(_package(tmp_path, "cycle-a", dependencies="[{skill_id: cycle-b}]"))
    runtime.install(_package(tmp_path, "cycle-b", dependencies="[{skill_id: cycle-a}]"))
    with pytest.raises(SkillDependencyCycle):
        runtime.resolve(SkillResolutionRequest("cycle", explicit_skill_ids=("cycle-a",)))


def test_assignments_precedence_context_and_uninstall_block(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.install(_package(tmp_path, "research-workflow", instructions="system version"))
    assignment = runtime.assign(
        SkillAssignment(
            agent_id="researcher",
            skill_id="research-workflow",
            version_constraint="^1.0.0",
            scope=SkillScope.PROJECT,
            assigned_by="admin",
            metadata={"project_id": "synapse"},
        )
    )
    assert runtime.load_assigned("researcher", project_id="other") == ()
    loaded = runtime.load_assigned("researcher", project_id="synapse")
    assert loaded[0].skill_id == "research-workflow"
    with pytest.raises(SkillInUse):
        runtime.uninstall("research-workflow", "1.0.0")
    runtime.unassign(assignment.assignment_id)
    runtime.uninstall("research-workflow", "1.0.0")
    assert runtime.list() == ()


def test_ephemeral_lease_never_expands_tools_and_cleanup(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    runtime.install(_package(tmp_path, "bounded-workflow", tools="[read_file, write_file]"))
    leases = runtime.grant_for_ephemeral(
        "ephemeral:1",
        ("bounded-workflow", "missing-skill"),
        mission_id="mission-1",
        task_id="task-1",
        expires_at=(datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        context_budget=1000,
        allowed_tools=("read_file",),
        correlation_id="corr-1",
    )
    assert leases[0]["tool_scope"] == ("read_file",)
    assert runtime.cleanup_leases("ephemeral:1") == 1
    assert runtime.list_leases("ephemeral:1") == ()


def test_manifest_metadata_redaction_and_script_checksum(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    package = _package(tmp_path, "scripted-skill")
    script = package / "scripts" / "check.py"
    script.parent.mkdir()
    script.write_text("print('check')", encoding="utf-8")
    checksum = hashlib.sha256(script.read_bytes()).hexdigest()
    manifest = (package / "manifest.yaml").read_text(encoding="utf-8")
    manifest = manifest.replace(
        "scripts: []",
        f"scripts: [{{script_id: check, runtime: python, entrypoint: scripts/check.py, checksum: {checksum}, required_tools: [sandbox_run]}}]",
    ).replace("metadata:\n  tags", "metadata:\n  token: secret\n  tags")
    (package / "manifest.yaml").write_text(manifest, encoding="utf-8")
    inspected = runtime.inspect(package)
    assert "token" not in inspected.manifest.metadata
    assert asdict(inspected.manifest.scripts[0])["entrypoint"] == "scripts/check.py"


def test_project_rfc_requirements_use_bounded_context_contract(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    package = _package(tmp_path, "architecture-review")
    path = package / "manifest.yaml"
    text = path.read_text(encoding="utf-8").replace(
        "metadata:\n",
        "requires_project: true\n"
        "requires_rfc_for_change_classes: [architectural]\n"
        "consumes_rfc_sections: [invariants, affected_contracts]\n"
        "produces_evidence_types: [architecture_check]\n"
        "metadata:\n",
    )
    path.write_text(text, encoding="utf-8")
    runtime.install(package)

    class Context:
        def read_project_context(self, project_id: str, *, budget: int = 8000):
            return ProjectContext(
                project_id,
                1,
                ({"rfc_id": "RFC-1", "status": "approved"},),
                (),
                (),
                (),
                (),
                ("architecture-review",),
                (),
                ({"source": "project_manifest", "revision": 1, "checksum": "abc"},),
                "internal",
            )

    runtime.project_context = Context()
    unavailable = runtime.resolve(
        SkillResolutionRequest(
            "architecture review",
            explicit_skill_ids=("architecture-review",),
            change_class="architectural",
        )
    )
    assert unavailable.unavailable == ("architecture-review",)
    selected = runtime.resolve(
        SkillResolutionRequest(
            "architecture review",
            explicit_skill_ids=("architecture-review",),
            project_id="synapse",
            rfc_id="RFC-1",
            rfc_revision=1,
            rfc_checksum="abc",
            change_class="architectural",
        )
    )
    assert selected.ordering == ("architecture-review",)
    assert selected.provenance["selection"] == "explicit"
