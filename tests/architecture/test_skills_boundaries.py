from __future__ import annotations

import ast

from .support import SOURCE_ROOT, cyclic_components
from .test_audio_speech_boundary import _runtime_context_graph, _runtime_imports

SKILLS_ROOT = SOURCE_ROOT / "skills"


def test_skills_does_not_import_domain_consumers_or_delivery() -> None:
    imports = {module for path in SKILLS_ROOT.rglob("*.py") for module in _runtime_imports(path)}
    forbidden = (
        "synapse.agents",
        "synapse.ephemeral_agents",
        "synapse.missions",
        "synapse.swarm",
        "synapse.primary_agent",
        "synapse.api",
        "synapse.commands",
    )
    assert not any(module.startswith(forbidden) for module in imports)


def test_consumers_import_only_neutral_skill_contracts() -> None:
    for context in ("agents", "ephemeral_agents", "missions", "swarm", "primary_agent", "context"):
        root = SOURCE_ROOT / context
        imports = {module for path in root.rglob("*.py") for module in _runtime_imports(path)}
        assert "synapse.skills.runtime" not in imports
        assert not any(module.startswith("synapse.skills.package") for module in imports)


def test_skills_runtime_uses_storage_and_tools_only_through_ports() -> None:
    runtime = (SKILLS_ROOT / "runtime.py").read_text(encoding="utf-8")
    assert "SkillRecordStore" in runtime
    assert "synapse.storage" not in runtime
    assert "synapse.tools" not in runtime
    adapter = (SOURCE_ROOT / "bootstrap" / "adapters" / "skills.py").read_text(encoding="utf-8")
    assert "ToolExecutionPort" in adapter
    assert "FileCollection" in adapter
    assert "subprocess" not in adapter and "os.system" not in adapter


def test_skill_packages_have_safe_explicit_loading_and_no_autoevolution() -> None:
    package = (SKILLS_ROOT / "package.py").read_text(encoding="utf-8")
    runtime = (SKILLS_ROOT / "runtime.py").read_text(encoding="utf-8")
    assert "is_absolute" in package and '".." in relative.parts' in package
    assert "rglob" not in runtime.replace('glob("*/*")', "")
    prohibited = ("auto_evolve", "candidate_version", "promote_version", "generate_skill")
    assert not any(term in (package + runtime) for term in prohibited)


def test_skills_stays_outside_global_scc() -> None:
    graph = _runtime_context_graph()
    assert len(graph) == 306  # Primary MoM: api -> mom -> core.
    assert cyclic_components(graph) == [
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
    assert all("skills" not in component for component, _ in cyclic_components(graph))


def test_phase2_domain_models_are_pure_and_non_executable() -> None:
    paths = (
        SKILLS_ROOT / "phase2_values.py",
        SKILLS_ROOT / "phase2_serialization.py",
        SKILLS_ROOT / "phase2_models.py",
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    imports = {module for path in paths for module in _runtime_imports(path)}
    forbidden_imports = (
        "synapse.skills.runtime",
        "synapse.storage",
        "synapse.bootstrap",
        "synapse.api",
        "synapse.tools",
        "synapse.sandbox",
        "synapse.project_governance",
        "synapse.private_evals",
        "pathlib",
        "os",
        "socket",
        "subprocess",
        "importlib",
    )
    assert not any(module.startswith(forbidden_imports) for module in imports)
    tree = ast.parse(source)
    direct_calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    attribute_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not direct_calls.intersection({"eval", "exec", "compile", "open"})
    assert not attribute_calls.intersection({"system", "Popen"})


def test_phase2_manifest_has_no_lifecycle_or_mutable_field_annotations() -> None:
    source = (SKILLS_ROOT / "phase2_models.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    manifest = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PublishedSkillManifest"
    )
    annotations = {
        node.target.id: ast.unparse(node.annotation)
        for node in manifest.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    forbidden = {
        "status",
        "active",
        "disabled",
        "deprecated",
        "installed",
        "trusted",
        "approved",
        "evaluated",
        "promoted",
        "revoked",
        "local_path",
        "metadata",
    }
    assert forbidden.isdisjoint(annotations)
    assert not any(
        "dict[" in value or "list[" in value or "Any" in value for value in annotations.values()
    )


def test_phase3_store_contracts_are_persistence_agnostic_and_non_executable() -> None:
    paths = (
        SKILLS_ROOT / "phase3_values.py",
        SKILLS_ROOT / "phase3_records.py",
        SKILLS_ROOT / "phase3_contracts.py",
        SKILLS_ROOT / "phase3_errors.py",
    )
    imports = {module for path in paths for module in _runtime_imports(path)}
    forbidden_imports = (
        "synapse.skills.runtime",
        "synapse.storage",
        "synapse.bootstrap",
        "synapse.api",
        "synapse.tools",
        "synapse.sandbox",
        "synapse.project_governance",
        "synapse.private_evals",
        "pathlib",
        "os",
        "sqlite3",
        "socket",
        "subprocess",
        "importlib",
    )
    assert not any(module.startswith(forbidden_imports) for module in imports)
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    tree = ast.parse(source)
    direct_calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not direct_calls.intersection({"eval", "exec", "compile", "open"})
    assert "sqlite" not in source.lower()


def test_phase3_protocols_are_narrow_append_only_and_have_no_concrete_store() -> None:
    path = SKILLS_ROOT / "phase3_contracts.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    protocols = tuple(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(ast.unparse(base) == "Protocol" for base in node.bases)
    )
    assert {node.name for node in protocols} == {
        "SkillAssignmentStore",
        "SkillBindingStore",
        "SkillCatalogStore",
        "SkillInstallationStore",
        "SkillLeaseStore",
        "SkillLifecycleStore",
    }
    method_names = {
        child.name
        for node in protocols
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert not method_names.intersection(
        {"delete", "remove", "overwrite", "replace", "upsert", "resolve", "latest"}
    )
    assert "dict[" not in source
    assert "list[" not in source
    assert "Any" not in source


def test_phase3_records_are_frozen_and_contain_no_mutable_or_payload_fields() -> None:
    path = SKILLS_ROOT / "phase3_records.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    records = tuple(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Name)
            and decorator.func.id == "dataclass"
            for decorator in node.decorator_list
        )
    )
    assert records
    assert all(
        any(
            isinstance(keyword.value, ast.Constant)
            and keyword.arg == "frozen"
            and keyword.value.value is True
            for decorator in node.decorator_list
            if isinstance(decorator, ast.Call)
            for keyword in decorator.keywords
        )
        for node in records
    )
    forbidden_fields = {
        "payload",
        "metadata",
        "path",
        "database",
        "sql",
        "approval",
        "trusted",
        "permission",
    }
    annotations = {
        child.target.id: ast.unparse(child.annotation)
        for node in records
        for child in node.body
        if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name)
    }
    assert forbidden_fields.isdisjoint(annotations)
    assert not any(
        "dict[" in annotation or "list[" in annotation or "Any" in annotation
        for annotation in annotations.values()
    )


def test_phase4_parser_and_verifier_are_safe_and_context_local() -> None:
    paths = (
        SKILLS_ROOT / "phase4_errors.py",
        SKILLS_ROOT / "phase4_models.py",
        SKILLS_ROOT / "phase4_parser.py",
        SKILLS_ROOT / "phase4_verification.py",
    )
    imports = {module for path in paths for module in _runtime_imports(path)}
    forbidden_imports = (
        "synapse.skills.runtime",
        "synapse.skills.phase3_contracts",
        "synapse.storage",
        "synapse.bootstrap",
        "synapse.api",
        "synapse.tools",
        "synapse.sandbox",
        "synapse.project_governance",
        "synapse.private_evals",
        "socket",
        "subprocess",
        "importlib",
        "requests",
        "http",
    )
    assert not any(module.startswith(forbidden_imports) for module in imports)
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    tree = ast.parse(source)
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not calls.intersection({"eval", "exec", "compile"})
    assert "yaml.load" not in source
    assert "FullLoader" not in source
    assert "UnsafeLoader" not in source


def test_phase5_publication_is_application_level_and_non_progressing() -> None:
    paths = (
        SKILLS_ROOT / "phase5_errors.py",
        SKILLS_ROOT / "phase5_models.py",
        SKILLS_ROOT / "phase5_publication.py",
    )
    imports = {module for path in paths for module in _runtime_imports(path)}
    forbidden_imports = (
        "synapse.skills.runtime",
        "synapse.skills.phase4_parser",
        "synapse.skills.phase4_verification",
        "synapse.storage",
        "synapse.bootstrap",
        "synapse.api",
        "synapse.tools",
        "synapse.sandbox",
        "synapse.project_governance",
        "synapse.private_evals",
        "pathlib",
        "os",
        "yaml",
        "socket",
        "subprocess",
        "importlib",
    )
    assert not any(module.startswith(forbidden_imports) for module in imports)
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    tree = ast.parse(source)
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not calls.intersection({"eval", "exec", "compile", "open"})
    forbidden_progression = (
        "install",
        "activate",
        "revoke",
        "evaluate",
        "approve",
        "execute",
        "publish_event",
    )
    service = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "SkillPublicationService"
    )
    methods = {
        node.name
        for node in service.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert not methods.intersection(forbidden_progression)


def test_phase6_lifecycle_is_application_level_and_boundary_clean() -> None:
    paths = (
        SKILLS_ROOT / "phase6_errors.py",
        SKILLS_ROOT / "phase6_models.py",
        SKILLS_ROOT / "phase6_lifecycle.py",
    )
    imports = {module for path in paths for module in _runtime_imports(path)}
    forbidden_imports = (
        "synapse.skills.runtime",
        "synapse.skills.phase4_parser",
        "synapse.skills.phase4_verification",
        "synapse.storage",
        "synapse.bootstrap",
        "synapse.api",
        "synapse.commands",
        "synapse.tools",
        "synapse.sandbox",
        "synapse.project_governance",
        "synapse.intelligence_boundary",
        "synapse.private_evals",
        "pathlib",
        "os",
        "sqlite3",
        "yaml",
        "socket",
        "subprocess",
        "importlib",
    )
    assert not any(module.startswith(forbidden_imports) for module in imports)
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    tree = ast.parse(source)
    direct_calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not direct_calls.intersection({"eval", "exec", "compile", "open"})
    assert "datetime.now" not in source
    assert "uuid" not in source.lower()
    assert "random" not in source.lower()
    assert "InMemory" not in source
    assert "locally_available" not in source
    assert "installation_ref" not in source


def test_phase7_installation_and_activation_are_reference_only_and_boundary_clean() -> None:
    paths = (
        SKILLS_ROOT / "phase7_errors.py",
        SKILLS_ROOT / "phase7_models.py",
        SKILLS_ROOT / "phase7_installation.py",
    )
    imports = {module for path in paths for module in _runtime_imports(path)}
    forbidden_imports = (
        "synapse.skills.runtime",
        "synapse.skills.phase4_parser",
        "synapse.skills.phase4_verification",
        "synapse.storage",
        "synapse.bootstrap",
        "synapse.api",
        "synapse.commands",
        "synapse.tools",
        "synapse.sandbox",
        "synapse.project_governance",
        "synapse.intelligence_boundary",
        "synapse.private_evals",
        "pathlib",
        "os",
        "shutil",
        "sqlite3",
        "yaml",
        "socket",
        "subprocess",
        "importlib",
    )
    assert not any(module.startswith(forbidden_imports) for module in imports)
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    tree = ast.parse(source)
    direct_calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    attribute_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not direct_calls.intersection({"eval", "exec", "compile", "open"})
    assert not attribute_calls.intersection(
        {"copy", "copy2", "copyfile", "copytree", "download", "clone", "unlink"}
    )
    assert "datetime.now" not in source
    assert "uuid" not in source.lower()
    assert "random" not in source.lower()
    assert "InMemory" not in source


def test_phase8_dependency_analysis_is_read_only_and_boundary_clean() -> None:
    paths = (
        SKILLS_ROOT / "phase8_errors.py",
        SKILLS_ROOT / "phase8_contracts.py",
        SKILLS_ROOT / "phase8_models.py",
        SKILLS_ROOT / "phase8_matching.py",
        SKILLS_ROOT / "phase8_compatibility.py",
        SKILLS_ROOT / "phase8_graph.py",
        SKILLS_ROOT / "phase8_analysis.py",
    )
    imports = {module for path in paths for module in _runtime_imports(path)}
    forbidden_imports = (
        "synapse.skills.runtime",
        "synapse.skills.phase4_parser",
        "synapse.skills.phase4_verification",
        "synapse.skills.phase7_installation",
        "synapse.storage",
        "synapse.bootstrap",
        "synapse.api",
        "synapse.commands",
        "synapse.tools",
        "synapse.sandbox",
        "synapse.project_governance",
        "synapse.intelligence_boundary",
        "synapse.private_evals",
        "pathlib",
        "os",
        "shutil",
        "sqlite3",
        "yaml",
        "socket",
        "subprocess",
        "importlib",
    )
    assert not any(module.startswith(forbidden_imports) for module in imports)
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    tree = ast.parse(source)
    direct_calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    attribute_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not direct_calls.intersection({"eval", "exec", "compile", "open"})
    assert not attribute_calls.intersection(
        {
            "save_version",
            "append_lifecycle",
            "append_activation",
            "append_installation",
            "append_termination",
            "delete",
            "download",
            "clone",
            "execute",
        }
    )
    forbidden_terms = (
        "latest",
        "highest",
        "preferred",
        "fallback",
        "wildcard",
        "datetime.now",
        "uuid",
        "background",
    )
    assert not any(term in source.lower() for term in forbidden_terms)


def test_phase9_resolution_is_pure_bounded_and_boundary_clean() -> None:
    paths = (
        SKILLS_ROOT / "phase9_errors.py",
        SKILLS_ROOT / "phase9_policy.py",
        SKILLS_ROOT / "phase9_constraints.py",
        SKILLS_ROOT / "phase9_models.py",
        SKILLS_ROOT / "phase9_selection.py",
        SKILLS_ROOT / "phase9_groups.py",
        SKILLS_ROOT / "phase9_resolution.py",
    )
    imports = {module for path in paths for module in _runtime_imports(path)}
    forbidden_imports = (
        "synapse.skills.runtime",
        "synapse.skills.phase5_publication",
        "synapse.skills.phase6_lifecycle",
        "synapse.skills.phase7_installation",
        "synapse.storage",
        "synapse.bootstrap",
        "synapse.api",
        "synapse.commands",
        "synapse.tools",
        "synapse.sandbox",
        "synapse.project_governance",
        "synapse.intelligence_boundary",
        "synapse.private_evals",
        "pathlib",
        "os",
        "shutil",
        "sqlite3",
        "yaml",
        "socket",
        "subprocess",
        "importlib",
    )
    assert not any(module.startswith(forbidden_imports) for module in imports)
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    tree = ast.parse(source)
    direct_calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    attribute_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not direct_calls.intersection({"eval", "exec", "compile", "open"})
    assert not attribute_calls.intersection(
        {
            "save_version",
            "append_lifecycle",
            "append_activation",
            "append_installation",
            "append_termination",
            "delete",
            "download",
            "clone",
            "execute",
        }
    )
    forbidden_terms = (
        "latest",
        "implicit default",
        "first candidate",
        "arbitrary sort",
        "datetime.now",
        "uuid",
        "background",
    )
    assert not any(term in source.lower() for term in forbidden_terms)


def test_phase10_external_bindings_are_neutral_and_boundary_clean() -> None:
    paths = (
        SKILLS_ROOT / "phase10_errors.py",
        SKILLS_ROOT / "phase10_refs.py",
        SKILLS_ROOT / "phase10_models.py",
        SKILLS_ROOT / "phase10_identity.py",
        SKILLS_ROOT / "phase10_contracts.py",
        SKILLS_ROOT / "phase10_projection.py",
        SKILLS_ROOT / "phase10_governance.py",
        SKILLS_ROOT / "phase10_intelligence.py",
    )
    imports = {module for path in paths for module in _runtime_imports(path)}
    forbidden_imports = (
        "synapse.project_governance",
        "synapse.intelligence_boundary",
        "synapse.private_evals",
        "synapse.skills.runtime",
        "synapse.skills.phase6_lifecycle",
        "synapse.skills.phase7_installation",
        "synapse.storage",
        "synapse.bootstrap",
        "synapse.api",
        "synapse.commands",
        "synapse.tools",
        "synapse.sandbox",
        "pathlib",
        "os",
        "shutil",
        "sqlite3",
        "socket",
        "subprocess",
        "importlib",
        "requests",
        "httpx",
    )
    assert not any(module.startswith(forbidden_imports) for module in imports)
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    tree = ast.parse(source)
    forbidden_calls = {
        "open",
        "eval",
        "exec",
        "install",
        "activate",
        "execute",
        "revoke",
        "promote",
        "append_evaluation",
    }
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    } | {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert calls.isdisjoint(forbidden_calls)
    earlier_paths = tuple(
        path
        for pattern in (
            "phase2_*.py",
            "phase3_*.py",
            "phase4_*.py",
            "phase5_*.py",
            "phase6_*.py",
            "phase7_*.py",
            "phase8_*.py",
            "phase9_*.py",
        )
        for path in SKILLS_ROOT.glob(pattern)
    )
    earlier_imports = {module for path in earlier_paths for module in _runtime_imports(path)}
    assert not any(module.startswith("synapse.skills.phase10") for module in earlier_imports)
    graph = _runtime_context_graph()
    assert len(graph) == 306  # Primary MoM: api -> mom -> core.
    assert all("skills" not in members for members, _ in cyclic_components(graph))


def test_phase11_private_eval_bindings_are_reference_only_and_boundary_clean() -> None:
    paths = (
        SKILLS_ROOT / "phase11_errors.py",
        SKILLS_ROOT / "phase11_refs.py",
        SKILLS_ROOT / "phase11_models.py",
        SKILLS_ROOT / "phase11_identity.py",
        SKILLS_ROOT / "phase11_contracts.py",
        SKILLS_ROOT / "phase11_projection.py",
        SKILLS_ROOT / "phase11_bindings.py",
    )
    imports = {module for path in paths for module in _runtime_imports(path)}
    forbidden_imports = (
        "synapse.private_evals",
        "synapse.project_governance",
        "synapse.intelligence_boundary",
        "synapse.skills.runtime",
        "synapse.skills.phase6_lifecycle",
        "synapse.skills.phase7_installation",
        "synapse.skills.phase9_resolution",
        "synapse.storage",
        "synapse.bootstrap",
        "synapse.api",
        "synapse.commands",
        "synapse.tools",
        "synapse.sandbox",
        "pathlib",
        "os",
        "shutil",
        "sqlite3",
        "socket",
        "subprocess",
        "importlib",
        "requests",
        "httpx",
    )
    assert not any(module.startswith(forbidden_imports) for module in imports)
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    tree = ast.parse(source)
    forbidden_calls = {
        "open",
        "eval",
        "exec",
        "install",
        "activate",
        "execute",
        "revoke",
        "promote",
        "rollback",
        "append_evaluation",
    }
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    } | {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert calls.isdisjoint(forbidden_calls)
    earlier_paths = tuple(
        path
        for pattern in (
            "phase2_*.py",
            "phase3_*.py",
            "phase4_*.py",
            "phase5_*.py",
            "phase6_*.py",
            "phase7_*.py",
            "phase8_*.py",
            "phase9_*.py",
            "phase10_*.py",
        )
        for path in SKILLS_ROOT.glob(pattern)
    )
    earlier_imports = {module for path in earlier_paths for module in _runtime_imports(path)}
    assert not any(module.startswith("synapse.skills.phase11") for module in earlier_imports)
    graph = _runtime_context_graph()
    assert len(graph) == 306  # Primary MoM: api -> mom -> core.
    assert all("skills" not in members for members, _ in cyclic_components(graph))


def test_phase12_handoff_is_structural_pure_and_boundary_clean() -> None:
    paths = tuple(SKILLS_ROOT.glob("phase12_*.py"))
    assert {path.name for path in paths} == {
        "phase12_errors.py",
        "phase12_handoff.py",
        "phase12_identity.py",
        "phase12_models.py",
        "phase12_policy.py",
        "phase12_refs.py",
    }
    imports = {module for path in paths for module in _runtime_imports(path)}
    forbidden_imports = (
        "synapse.sandbox",
        "synapse.execution_router",
        "synapse.delegation_execution",
        "synapse.project_governance",
        "synapse.intelligence_boundary",
        "synapse.private_evals",
        "synapse.skills.runtime",
        "synapse.skills.phase6_lifecycle",
        "synapse.skills.phase7_installation",
        "synapse.skills.phase9_resolution",
        "synapse.storage",
        "synapse.bootstrap",
        "synapse.api",
        "synapse.commands",
        "synapse.tools",
        "pathlib",
        "os",
        "shutil",
        "sqlite3",
        "socket",
        "subprocess",
        "importlib",
        "requests",
        "httpx",
    )
    assert not any(module.startswith(forbidden_imports) for module in imports)
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    tree = ast.parse(source)
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    } | {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert calls.isdisjoint(
        {
            "open",
            "eval",
            "exec",
            "compile",
            "install",
            "activate",
            "execute",
            "append",
            "save",
            "write",
            "read_text",
            "read_bytes",
            "Popen",
            "system",
        }
    )
    earlier_paths = tuple(
        path
        for number in range(2, 12)
        for path in SKILLS_ROOT.glob(f"phase{number}_*.py")
    )
    earlier_imports = {module for path in earlier_paths for module in _runtime_imports(path)}
    assert not any(module.startswith("synapse.skills.phase12") for module in earlier_imports)
    graph = _runtime_context_graph()
    assert len(graph) == 306  # Primary MoM: api -> mom -> core.
    assert all("skills" not in members for members, _ in cyclic_components(graph))


def test_phase13_application_boundary_is_explicit_and_transport_free() -> None:
    application_root = SKILLS_ROOT / "application"
    paths = tuple(application_root.glob("*.py"))
    assert {path.name for path in paths} == {
        "__init__.py",
        "command_handlers.py",
        "commands.py",
        "errors.py",
        "queries.py",
        "query_handlers.py",
        "results.py",
    }
    imports = {module for path in paths for module in _runtime_imports(path)}
    forbidden_imports = (
        "synapse.api",
        "synapse.bootstrap",
        "synapse.commands",
        "synapse.execution_router",
        "synapse.private_evals",
        "synapse.project_governance",
        "synapse.sandbox",
        "synapse.storage",
        "pathlib",
        "sqlite3",
        "socket",
        "subprocess",
        "fastapi",
        "flask",
        "requests",
        "httpx",
    )
    assert not any(module.startswith(forbidden_imports) for module in imports)
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "Dispatcher" not in source
    assert "CommandBus" not in source
    assert "QueryBus" not in source
    earlier_paths = tuple(
        path
        for number in range(2, 13)
        for path in SKILLS_ROOT.glob(f"phase{number}_*.py")
    )
    earlier_imports = {module for path in earlier_paths for module in _runtime_imports(path)}
    assert not any(
        module.startswith("synapse.skills.application") for module in earlier_imports
    )


def test_phase14_persistence_is_local_concrete_and_inward_only() -> None:
    persistence_root = SKILLS_ROOT / "persistence"
    paths = tuple(persistence_root.glob("*.py"))
    assert {path.name for path in paths} == {
        "__init__.py",
        "codec.py",
        "connection.py",
        "errors.py",
        "integrity.py",
        "migrations.py",
        "stores.py",
    }
    imports = {module for path in paths for module in _runtime_imports(path)}
    forbidden = (
        "synapse.api",
        "synapse.bootstrap",
        "synapse.commands",
        "synapse.private_evals",
        "synapse.project_governance",
        "synapse.intelligence_boundary",
        "synapse.execution_router",
        "synapse.sandbox",
        "fastapi",
        "flask",
        "requests",
        "httpx",
        "subprocess",
        "importlib",
    )
    assert not any(module.startswith(forbidden) for module in imports)
    earlier_paths = tuple(
        path
        for number in range(2, 13)
        for path in SKILLS_ROOT.glob(f"phase{number}_*.py")
    )
    application_paths = tuple((SKILLS_ROOT / "application").glob("*.py"))
    inward_imports = {
        module
        for path in earlier_paths + application_paths
        for module in _runtime_imports(path)
    }
    assert not any(
        module.startswith("synapse.skills.persistence") for module in inward_imports
    )
    root_source = (SKILLS_ROOT / "__init__.py").read_text(encoding="utf-8")
    assert "synapse.skills.persistence" not in root_source


def test_phase15_compatibility_is_opt_in_pure_and_inward_only() -> None:
    compatibility_root = SKILLS_ROOT / "compatibility"
    paths = tuple(compatibility_root.glob("*.py"))
    assert {path.name for path in paths} == {
        "__init__.py",
        "catalog.py",
        "errors.py",
        "lifecycle.py",
        "models.py",
    }
    imports = {module for path in paths for module in _runtime_imports(path)}
    forbidden = (
        "synapse.api",
        "synapse.bootstrap",
        "synapse.commands",
        "synapse.private_evals",
        "synapse.project_governance",
        "synapse.intelligence_boundary",
        "synapse.execution_router",
        "synapse.sandbox",
        "synapse.skills.persistence",
        "synapse.skills.runtime",
        "synapse.skills.package",
        "pathlib",
        "sqlite3",
        "socket",
        "subprocess",
        "importlib",
        "fastapi",
        "flask",
        "requests",
        "httpx",
    )
    assert not any(module.startswith(forbidden) for module in imports)
    inward_paths = tuple(SKILLS_ROOT.glob("*.py"))
    inward_paths += tuple((SKILLS_ROOT / "application").glob("*.py"))
    inward_paths += tuple((SKILLS_ROOT / "persistence").glob("*.py"))
    inward_imports = {
        module for path in inward_paths for module in _runtime_imports(path)
    }
    assert not any(
        module.startswith("synapse.skills.compatibility") for module in inward_imports
    )
    root_source = (SKILLS_ROOT / "__init__.py").read_text(encoding="utf-8")
    assert "synapse.skills.compatibility" not in root_source


def test_phase16_composition_is_local_explicit_and_not_activated() -> None:
    composition_root = SKILLS_ROOT / "composition"
    paths = tuple(composition_root.glob("*.py"))
    assert {path.name for path in paths} == {
        "__init__.py",
        "errors.py",
        "gateway.py",
        "models.py",
        "runtime.py",
    }
    imports = {module for path in paths for module in _runtime_imports(path)}
    forbidden = (
        "synapse.api",
        "synapse.bootstrap",
        "synapse.commands",
        "synapse.private_evals",
        "synapse.project_governance",
        "synapse.intelligence_boundary",
        "synapse.execution_router",
        "synapse.sandbox",
        "synapse.skills.runtime",
        "synapse.skills.package",
        "fastapi",
        "flask",
        "argparse",
        "click",
        "typer",
        "subprocess",
        "importlib",
    )
    assert not any(module.startswith(forbidden) for module in imports)
    inward_paths = tuple(SKILLS_ROOT.glob("*.py"))
    inward_paths += tuple((SKILLS_ROOT / "application").glob("*.py"))
    inward_paths += tuple((SKILLS_ROOT / "persistence").glob("*.py"))
    inward_paths += tuple((SKILLS_ROOT / "compatibility").glob("*.py"))
    inward_imports = {
        module for path in inward_paths for module in _runtime_imports(path)
    }
    assert not any(
        module.startswith("synapse.skills.composition") for module in inward_imports
    )
    root_source = (SKILLS_ROOT / "__init__.py").read_text(encoding="utf-8")
    assert "synapse.skills.composition" not in root_source


def test_phase17_recovery_is_operational_local_and_inward_only() -> None:
    recovery_root = SKILLS_ROOT / "recovery"
    paths = tuple(recovery_root.glob("*.py"))
    assert {path.name for path in paths} == {
        "__init__.py",
        "coordinator.py",
        "errors.py",
        "models.py",
    }
    imports = {module for path in paths for module in _runtime_imports(path)}
    forbidden = (
        "synapse.api",
        "synapse.bootstrap",
        "synapse.commands",
        "synapse.private_evals",
        "synapse.project_governance",
        "synapse.intelligence_boundary",
        "synapse.execution_router",
        "synapse.sandbox",
        "synapse.skills.runtime",
        "synapse.skills.package",
        "fastapi",
        "flask",
        "argparse",
        "click",
        "typer",
        "subprocess",
        "importlib",
    )
    assert not any(module.startswith(forbidden) for module in imports)
    inward_paths = tuple(SKILLS_ROOT.glob("*.py"))
    for name in ("application", "persistence", "compatibility", "composition"):
        inward_paths += tuple((SKILLS_ROOT / name).glob("*.py"))
    inward_imports = {
        module for path in inward_paths for module in _runtime_imports(path)
    }
    assert not any(
        module.startswith("synapse.skills.recovery") for module in inward_imports
    )
    root_source = (SKILLS_ROOT / "__init__.py").read_text(encoding="utf-8")
    assert "synapse.skills.recovery" not in root_source
