from __future__ import annotations

import ast

from .support import SOURCE_ROOT, context_graph, cyclic_components, imports_for
from .test_audio_speech_boundary import _runtime_context_graph

ROOT = SOURCE_ROOT / "deployment"


def test_deployment_is_pure_provider_neutral_and_has_no_cross_context_imports() -> None:
    imports = {module for path in ROOT.rglob("*.py") for module in imports_for(path)}
    assert not any(module.startswith("synapse.") for module in imports)
    assert not imports.intersection(
        {
            "os",
            "pathlib",
            "shutil",
            "subprocess",
            "socket",
            "urllib",
            "http",
            "requests",
            "httpx",
        }
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.rglob("*.py"))
    assert not any(
        term in source
        for term in (
            "synapse.sandbox",
            "synapse.sandbox_drivers",
            "synapse.repository_runtime",
            "synapse.coding_sessions",
            "synapse.project_governance",
            "synapse.private_evals",
            "synapse.providers",
            "synapse.bootstrap",
            "boto",
            "kubernetes",
            "docker",
            "azure",
        )
    )


def test_deployment_public_surface_contains_only_abstract_execution_ports() -> None:
    exported = __import__("synapse.deployment", fromlist=["__all__"]).__all__
    forbidden_terms = ("Store", "Service", "Runtime", "Repository", "Adapter")
    assert not [
        name
        for name in exported
        if name
        not in {
            "AdapterBindingReference",
            "DeploymentAuthorityStore",
            "DeploymentJournalStore",
        }
        and any(term in name for term in forbidden_terms)
    ]
    for path in ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assert not [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"open", "exec", "eval"}
        ]


def test_deployment_operational_boundaries_are_protocols_without_implementations() -> None:
    tree = ast.parse((ROOT / "ports.py").read_text(encoding="utf-8"))
    protocols = {
        node.name: [
            child.name
            for child in node.body
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(isinstance(base, ast.Name) and base.id == "Protocol" for base in node.bases)
    }
    assert protocols == {
        "DeploymentApplyPort": ["apply"],
        "DeploymentArtifactFactsPort": ["artifact_facts"],
        "DeploymentAuthorizationPort": ["authorize"],
        "DeploymentObservationPort": ["observe"],
        "DeploymentPreparationPort": ["prepare"],
        "DeploymentRollbackApplyPort": ["apply_rollback"],
        "DeploymentRollbackObservationPort": ["observe_rollback"],
        "DeploymentRollbackPreparationPort": ["prepare_rollback"],
        "DeploymentRollbackVerificationPort": ["verify_rollback"],
        "DeploymentVerificationPort": ["verify"],
    }
    assert not [
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name.endswith(("Adapter", "Service", "Runtime", "Store"))
    ]


def test_deployment_has_only_authorized_incoming_adapter_and_integration_edges() -> None:
    bootstrap_imports = {
        module for path in (SOURCE_ROOT / "bootstrap").rglob("*.py") for module in imports_for(path)
    }
    assert not bootstrap_imports.intersection(
        {
            "synapse.deployment",
            "synapse.deployment_adapters",
            "synapse.deployment_integrations",
        }
    )
    assert "synapse.deployment_composition" in bootstrap_imports
    runtime = _runtime_context_graph()
    source = context_graph()
    assert {edge for edge in runtime if "deployment" in edge} == {
        ("deployment_adapters", "deployment"),
        ("deployment_composition", "deployment"),
        ("deployment_integrations", "deployment"),
    }
    assert {edge for edge in source if "deployment" in edge} == {
        ("deployment_adapters", "deployment"),
        ("deployment_composition", "deployment"),
        ("deployment_integrations", "deployment"),
    }
    assert {edge for edge in runtime if edge[0] == "deployment_integrations"} == {
        ("deployment_integrations", "approvals"),
        ("deployment_integrations", "decisions"),
        ("deployment_integrations", "deployment"),
        ("deployment_integrations", "sandbox"),
        ("deployment_integrations", "sandbox_drivers"),
    }
    assert {edge for edge in source if edge[0] == "deployment_integrations"} == {
        ("deployment_integrations", "approvals"),
        ("deployment_integrations", "decisions"),
        ("deployment_integrations", "deployment"),
        ("deployment_integrations", "sandbox"),
        ("deployment_integrations", "sandbox_drivers"),
    }
    assert len(runtime) == 306  # Primary MoM: api -> mom -> core.
    assert len(source) == 341  # Primary MoM adds the same two source edges.
    assert all("deployment" not in members for members, _ in cyclic_components(runtime))
    assert all("deployment" not in members for members, _ in cyclic_components(source))


def test_deployment_sqlite_adapter_points_inward_without_operational_authority() -> None:
    root = SOURCE_ROOT / "deployment_adapters"
    imports = {module for path in root.rglob("*.py") for module in imports_for(path)}
    assert any(module.startswith("synapse.deployment") for module in imports)
    assert not any(
        module.startswith(
            (
                "synapse.sandbox",
                "synapse.repository_runtime",
                "synapse.coding_sessions",
                "synapse.project_governance",
                "synapse.private_evals",
                "synapse.bootstrap",
            )
        )
        for module in imports
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
    assert not any(
        name in source
        for name in (
            "DeploymentApplyPort",
            "DeploymentAuthorizationPort",
            "DeploymentObservationPort",
            "DeploymentVerificationPort",
            "DeploymentRollbackApplyPort",
        )
    )


def test_deployment_governance_integration_is_consumer_owned_and_effect_free() -> None:
    root = SOURCE_ROOT / "deployment_integrations"
    imports = {module for path in root.rglob("*.py") for module in imports_for(path)}
    assert any(module.startswith("synapse.deployment") for module in imports)
    assert any(module.startswith("synapse.decisions") for module in imports)
    assert any(module.startswith("synapse.approvals") for module in imports)
    assert any(module.startswith("synapse.sandbox") for module in imports)
    assert not any(
        module.startswith(
            (
                "synapse.bootstrap",
                "synapse.private_evals",
                "synapse.repository_runtime",
            )
        )
        for module in imports
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
    assert not any(
        term in source
        for term in (
            "DeploymentApplyPort",
            "DeploymentRollbackApplyPort",
            "FencingReference",
            "apply_rollback(",
            ".apply(",
        )
    )
