from __future__ import annotations

from .support import SOURCE_ROOT, cyclic_components
from .test_audio_speech_boundary import _runtime_context_graph, _runtime_imports

ROOT = SOURCE_ROOT / "project_governance"


def test_project_governance_imports_no_concrete_consumers_or_delivery() -> None:
    imports = {module for path in ROOT.rglob("*.py") for module in _runtime_imports(path)}
    forbidden = (
        "synapse.agents",
        "synapse.ephemeral_agents",
        "synapse.missions",
        "synapse.swarm",
        "synapse.skills.runtime",
        "synapse.tools",
        "synapse.api",
        "synapse.commands",
    )
    assert not any(module.startswith(forbidden) for module in imports)


def test_consumers_import_only_project_governance_contracts_and_models() -> None:
    for context in ("context", "missions", "skills", "swarm", "primary_agent"):
        imports = {
            module
            for path in (SOURCE_ROOT / context).rglob("*.py")
            for module in _runtime_imports(path)
        }
        assert "synapse.project_governance.runtime" not in imports


def test_documents_are_human_editable_and_operational_state_uses_storage() -> None:
    adapter = (SOURCE_ROOT / "bootstrap" / "adapters" / "project_governance.py").read_text(
        encoding="utf-8"
    )
    assert '"RFC.md"' in adapter and '"manifest.yaml"' in adapter
    assert "FileCollection" in adapter and "GovernanceRecordStoreAdapter" in adapter


def test_no_shell_automatic_approval_or_private_eval_export() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.rglob("*.py"))
    assert "subprocess" not in source and "os.system" not in source and "shell=True" not in source
    assert "Ephemeral agents cannot permanently approve RFCs" in source
    assert "private_only: bool = True" in (ROOT / "models.py").read_text(encoding="utf-8")


def test_plan_freshness_and_implemented_criteria_are_enforced() -> None:
    runtime = (ROOT / "runtime.py").read_text(encoding="utf-8")
    assert "Implementation plan targets a stale RFC" in runtime
    assert "Required acceptance criteria are not satisfied" in runtime
    assert "RFC cannot be implemented without evidence" in runtime


def test_project_governance_stays_outside_global_scc() -> None:
    graph = _runtime_context_graph()
    assert len(graph) == 306  # Primary MoM: api -> mom -> core.
    components = cyclic_components(graph)
    assert components == [
        (
            frozenset(
                {
                    "agents",
                    "approvals",
                    "context",
                    "conversations",
                    "decisions",
                    "delegation",
                    "missions",
                    "models",
                    "policies",
                    "tools",
                    "voice",
                }
            ),
                31,
        ),
    ]
    assert all("project_governance" not in component for component, _ in components)
