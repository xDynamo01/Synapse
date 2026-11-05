from __future__ import annotations

import ast

import synapse.private_evals as private_evals

from .support import SOURCE_ROOT, cyclic_components, imports_for
from .test_audio_speech_boundary import _runtime_context_graph

ROOT = SOURCE_ROOT / "private_evals"

FORBIDDEN_IMPORT_PREFIXES = (
    "synapse.api",
    "synapse.bootstrap",
    "synapse.commands",
    "synapse.desktop_automation",
    "synapse.missions",
    "synapse.swarm",
    "synapse.workers",
    "synapse.storage",
    "synapse.providers",
    "synapse.model_providers",
    "aiohttp",
    "http.client",
    "httpx",
    "os",
    "pathlib",
    "requests",
    "sqlalchemy",
    "socket",
    "sqlite3",
    "subprocess",
    "urllib",
)


def test_private_evals_public_facade_excludes_persistence_internals() -> None:
    exports = set(private_evals.__all__)
    assert not exports.intersection(
        {
            "SCHEMA_VERSION",
            "SQLiteEvalAnalysisStore",
            "SQLiteEvalCatalogStore",
            "SQLiteEvalEvidenceStore",
            "SQLiteEvalMaterializationStore",
            "SQLiteEvalRunStore",
            "decode_record",
            "encode_record",
            "open_sqlite_private_evals_stores",
        }
    )


def test_private_evals_domain_has_only_approved_imports() -> None:
    persistence_paths = {
        ROOT / "sqlite_stores.py",
        ROOT / "sqlite_serialization.py",
    }
    domain_imports = {
        module
        for path in ROOT.rglob("*.py")
        if path not in persistence_paths and path.name != "__init__.py"
        for module in imports_for(path)
    }
    assert not any(module.startswith(FORBIDDEN_IMPORT_PREFIXES) for module in domain_imports)
    imports = {module for path in ROOT.rglob("*.py") for module in imports_for(path)}
    cross_context = {
        module
        for module in imports
        if module.startswith("synapse.") and not module.startswith("synapse.private_evals")
    }
    assert cross_context == {
        "synapse.intelligence_boundary.contracts",
        "synapse.intelligence_boundary.models",
        "synapse.project_governance.contracts",
        "synapse.project_governance.models",
    }


def test_private_evals_inbound_boundary_is_typed_minimized_and_uncomposed() -> None:
    paths = (
        ROOT / "command_contracts.py",
        ROOT / "command_errors.py",
        ROOT / "command_error_mapping.py",
        ROOT / "command_handlers.py",
        ROOT / "command_models.py",
        ROOT / "query_handler.py",
        ROOT / "query_models.py",
    )
    imports = {module for path in paths for module in imports_for(path)}
    assert not any(
        module.startswith(
            (
                "synapse.api",
                "synapse.bootstrap",
                "synapse.commands",
                "synapse.storage",
                "synapse.providers",
                "synapse.model_providers",
                "synapse.missions",
                "synapse.workers",
                "synapse.swarm",
                "fastapi",
                "pydantic",
            )
        )
        for module in imports
    )
    contracts_tree = ast.parse((ROOT / "command_contracts.py").read_text(encoding="utf-8"))
    protocols = [
        node.name
        for node in contracts_tree.body
        if isinstance(node, ast.ClassDef)
        and any(isinstance(base, ast.Name) and base.id == "Protocol" for base in node.bases)
    ]
    assert protocols == [
        "RunManifestResolver",
        "MaterializationRecordResolver",
        "EvaluationRecordResolver",
        "ScoringRecordResolver",
        "FinalizationRecordResolver",
        "EvidenceRecordResolver",
    ]
    forbidden_resolver_returns = {
        "MaterializationInput",
        "EvalResultCreationInput",
        "RunScoringInput",
        "RunFinalizationInput",
        "EvalEvidencePlanningInput",
    }
    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and isinstance(node.returns, ast.Name)
        and node.returns.id in forbidden_resolver_returns
        for node in ast.walk(contracts_tree)
    )
    handlers = (ROOT / "command_handlers.py").read_text(encoding="utf-8")
    assert "PrivateEvalsCommandHandlers" in handlers
    assert all(
        capability in handlers
        for capability in (
            "create_run",
            "start_run",
            "record_materialized_output",
            "create_eval_result",
            "create_scoring_decision",
            "finalize_run",
            "recover_finalization",
            "submit_evidence",
        )
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    forbidden_behavior = (
        "FastAPI(",
        "APIRouter(",
        "CommandRegistry(",
        "is_admin",
        "access_token",
        "refresh_token",
        "api_key",
        "raw_prompt",
        "raw_output",
        "provider_response",
        "run_everything",
        "execute_pipeline",
        "approve(",
        "promote_baseline",
        "ComparisonEngine",
        "RegressionDetector",
    )
    assert not any(term in source for term in forbidden_behavior)
    handler_tree = ast.parse(
        (ROOT / "command_handlers.py").read_text(encoding="utf-8")
    )
    assert not any(
        isinstance(node, ast.ExceptHandler)
        and isinstance(node.type, ast.Name)
        and node.type.id == "Exception"
        for node in ast.walk(handler_tree)
    )


def test_private_evals_domain_io_is_confined_to_concrete_sqlite_stores() -> None:
    forbidden_files = {
        "adapters.py",
        "manager.py",
        "repositories.py",
        "repository.py",
        "runtime.py",
        "services.py",
        "storage.py",
    }
    assert not {path.name for path in ROOT.rglob("*.py")} & forbidden_files

    forbidden_calls: list[tuple[str, str]] = []
    forbidden_classes: list[tuple[str, str]] = []
    for path in ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                forbidden_suffix = node.name.endswith(
                    ("Adapter", "Manager", "Registry", "Repository", "Runtime", "Service")
                )
                approved_runtime = (path.name, node.name) in {
                    ("catalog_runtime.py", "EvalCatalogRuntime"),
                    ("run_runtime.py", "EvalRunRuntime"),
                    ("security_service.py", "EvalSecurityService"),
                    ("result_materialization.py", "MaterializedOutputService"),
                    ("case_evaluation.py", "EvalResultService"),
                    ("run_scoring_service.py", "RunScoringService"),
                    ("run_finalization_service.py", "EvalRunFinalizationService"),
                    ("evidence_submission_service.py", "EvalEvidenceSubmissionService"),
                }
                concrete_boundary_adapter = (
                    "adapters" in path.parts and node.name.endswith("Adapter")
                )
                if forbidden_suffix and not approved_runtime and not concrete_boundary_adapter:
                    forbidden_classes.append((path.name, node.name))
                if node.name.endswith("Store"):
                    bases = {base.id for base in node.bases if isinstance(base, ast.Name)}
                    concrete_sqlite_store = (
                        path.name == "sqlite_stores.py"
                        and node.name.startswith("SQLiteEval")
                    )
                    if (
                        (path.name != "contracts.py" or "Protocol" not in bases)
                        and not concrete_sqlite_store
                    ):
                        forbidden_classes.append((path.name, node.name))
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id in {"open", "exec", "eval"}:
                forbidden_calls.append((path.name, node.func.id))
            if isinstance(node.func, ast.Attribute) and node.func.attr in {
                "read_text",
                "read_bytes",
                "write_text",
                "write_bytes",
                "system",
                "popen",
            }:
                forbidden_calls.append((path.name, node.func.attr))
    assert not forbidden_calls
    assert not forbidden_classes


def test_sqlite_persistence_does_not_leak_into_domain_or_delivery() -> None:
    persistence_modules = {
        "sqlite3",
        "synapse.private_evals.sqlite_stores",
        "synapse.private_evals.sqlite_serialization",
    }
    protected_paths = (
        ROOT / "contracts.py",
        ROOT / "catalog_runtime.py",
        ROOT / "run_runtime.py",
        ROOT / "command_contracts.py",
        ROOT / "command_handlers.py",
        ROOT / "query_handler.py",
    )
    for path in protected_paths:
        assert not (set(imports_for(path)) & persistence_modules)

    concrete_importers = []
    for root_name in ("bootstrap", "commands", "api"):
        root = SOURCE_ROOT / root_name
        for path in root.rglob("*.py"):
            imports = imports_for(path)
            if any(module.startswith("synapse.private_evals.sqlite_") for module in imports):
                concrete_importers.append(path)
    assert not concrete_importers


def test_sqlite_store_has_no_network_provider_or_cross_context_runtime_imports() -> None:
    paths = (ROOT / "sqlite_stores.py", ROOT / "sqlite_serialization.py")
    imports = {module for path in paths for module in imports_for(path)}
    forbidden_prefixes = (
        "synapse.agents",
        "synapse.missions",
        "synapse.workers",
        "synapse.swarm",
        "synapse.providers",
        "synapse.model_providers",
        "synapse.project_governance.runtime",
        "synapse.intelligence_boundary.runtime",
        "fastapi",
        "requests",
        "httpx",
        "socket",
    )
    assert not any(module.startswith(forbidden_prefixes) for module in imports)


def test_private_evals_external_adapters_are_isolated_and_use_only_approved_edges() -> None:
    adapter_root = ROOT / "adapters"
    assert {path.name for path in adapter_root.glob("*.py")} == {
        "__init__.py",
        "boundaries.py",
        "errors.py",
        "queries.py",
        "resolvers.py",
    }
    adapter_paths = tuple(adapter_root.glob("*.py"))
    imports = {module for path in adapter_paths for module in imports_for(path)}
    forbidden_prefixes = (
        "synapse.api",
        "synapse.bootstrap",
        "synapse.approvals",
        "synapse.agents",
        "synapse.missions",
        "synapse.workers",
        "synapse.swarm",
        "synapse.providers",
        "synapse.model_providers",
        "synapse.intelligence_boundary.runtime",
        "synapse.project_governance.runtime",
        "fastapi",
        "requests",
        "urllib",
        "subprocess",
        "socket",
    )
    assert not any(module.startswith(forbidden_prefixes) for module in imports)
    cross_context = {
        module
        for module in imports
        if module.startswith("synapse.")
        and not module.startswith("synapse.private_evals")
    }
    assert cross_context == {
        "synapse.project_governance.contracts",
        "synapse.project_governance.models",
    }
    source = "\n".join(path.read_text(encoding="utf-8") for path in adapter_paths)
    assert not any(
        term in source
        for term in (
            "ProjectGovernanceRuntime",
            "ApprovalRuntime",
            "IntelligenceBoundaryRuntime",
            "FastAPI(",
            "requests.",
            "urllib.",
            "subprocess.",
            "open(",
            "Path(",
            "os.environ",
            "time.sleep",
        )
    )
    for path in ROOT.glob("*.py"):
        assert not any(
            module.startswith("synapse.private_evals.adapters")
            for module in imports_for(path)
        )


def test_partial_harness_and_test_doubles_are_absent_from_production_surface() -> None:
    production_source = "\n".join(
        path.read_text(encoding="utf-8") for path in ROOT.rglob("*.py")
    )
    public_adapter_source = (ROOT / "adapters" / "__init__.py").read_text(
        encoding="utf-8"
    )
    assert "test_partial_boundary_harness" not in production_source
    assert "PartialBoundaryHarness" not in production_source
    assert "run_all" not in production_source
    assert not any(
        test_double in public_adapter_source
        for test_double in ("Fake", "Spy", "FailureInjection", "Mock")
    )


def test_adapters_have_no_transport_dynamic_import_or_governance_read_surface() -> None:
    adapter_root = ROOT / "adapters"
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in adapter_root.glob("*.py")
    )
    forbidden_transport = (
        "requests.",
        "httpx.",
        "urllib.",
        "socket.",
        "aiohttp.",
        "grpc.",
        "websockets.",
        "boto.",
        "subprocess.",
        "importlib.",
        "__import__",
    )
    assert not any(term in source for term in forbidden_transport)
    assert "Approval" not in source
    boundaries_tree = ast.parse(
        (adapter_root / "boundaries.py").read_text(encoding="utf-8")
    )
    governance = next(
        node
        for node in boundaries_tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "GovernanceEvidenceWriteAdapter"
    )
    assert {
        node.name
        for node in governance.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    } == {"record_evidence"}


def test_sqlite_persistence_exposes_only_approved_stores_and_no_mutating_upsert() -> None:
    source = (ROOT / "sqlite_stores.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    concrete_stores = {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name.startswith("SQLiteEval")
    }
    assert concrete_stores == {
        "SQLiteEvalCatalogStore",
        "SQLiteEvalRunStore",
        "SQLiteEvalAnalysisStore",
        "SQLiteEvalMaterializationStore",
        "SQLiteEvalEvidenceStore",
    }
    assert not any(
        term in source
        for term in (
            "INSERT OR REPLACE",
            "INSERT OR IGNORE",
            "ON CONFLICT",
            " UPSERT ",
            "class Repository",
            "def execute_sql(",
            "def search(",
            "def delete(",
        )
    )


def test_only_approved_private_evals_runtimes_exist() -> None:
    runtime_files = {path.name for path in ROOT.glob("*runtime*.py")}
    assert runtime_files == {"catalog_runtime.py", "run_runtime.py"}
    for runtime_file in runtime_files:
        imports = imports_for(ROOT / runtime_file)
        assert all(
            not module.startswith("synapse.") or module.startswith("synapse.private_evals")
            for module in imports
        )


def test_scoring_is_pure_stateless_and_independent_from_runtimes_and_stores() -> None:
    scoring_paths = (ROOT / "scoring.py", ROOT / "scoring_errors.py")
    imports = {module for path in scoring_paths for module in imports_for(path)}
    forbidden_imports = {
        "synapse.private_evals.analysis",
        "synapse.private_evals.catalog_runtime",
        "synapse.private_evals.contracts",
        "synapse.private_evals.run_runtime",
        "synapse.private_evals.store_errors",
        "synapse.private_evals.store_models",
    }
    assert not imports & forbidden_imports
    source = "\n".join(path.read_text(encoding="utf-8") for path in scoring_paths)
    forbidden_behavior = (
        "EvalAnalysisStore",
        "EvalCatalogStore",
        "EvalRunStore",
        "EvalResult(",
        "EvalRun(",
        "EvalBaseline",
        "EvalComparison",
        "RegressionReport",
        "open(",
        "subprocess",
    )
    assert not any(term in source for term in forbidden_behavior)


def test_analysis_is_pure_and_independent_from_runtimes_stores_and_approval() -> None:
    analysis_paths = (ROOT / "analysis.py", ROOT / "evaluation.py")
    imports = {module for path in analysis_paths for module in imports_for(path)}
    forbidden_imports = {
        "synapse.private_evals.catalog_runtime",
        "synapse.private_evals.contracts",
        "synapse.private_evals.run_runtime",
        "synapse.private_evals.store_errors",
        "synapse.private_evals.store_models",
        "synapse.storage",
        "synapse.project_governance",
    }
    assert not imports & forbidden_imports
    source = "\n".join(path.read_text(encoding="utf-8") for path in analysis_paths)
    forbidden_behavior = (
        "EvalAnalysisStore",
        "EvalCatalogStore",
        "EvalRunStore",
        "activate_baseline",
        "approve_baseline",
        "open(",
        "subprocess",
        "socket",
        "exec(",
        "eval(",
    )
    assert not any(term in source for term in forbidden_behavior)


def test_security_service_reuses_frozen_egress_and_has_one_projection_port() -> None:
    paths = (
        ROOT / "security.py",
        ROOT / "security_contracts.py",
        ROOT / "security_errors.py",
        ROOT / "security_service.py",
    )
    imports = {module for path in paths for module in imports_for(path)}
    forbidden_imports = {
        "synapse.intelligence_boundary.runtime",
        "synapse.private_evals.catalog_runtime",
        "synapse.private_evals.contracts",
        "synapse.private_evals.run_runtime",
        "synapse.project_governance",
        "synapse.storage",
    }
    assert not imports & forbidden_imports
    assert {
        "security_contracts",
        "synapse.intelligence_boundary.contracts",
        "synapse.intelligence_boundary.models",
    } <= imports
    contracts_tree = ast.parse((ROOT / "security_contracts.py").read_text(encoding="utf-8"))
    protocol_classes = [
        node
        for node in contracts_tree.body
        if isinstance(node, ast.ClassDef)
        and any(isinstance(base, ast.Name) and base.id == "Protocol" for base in node.bases)
    ]
    assert [node.name for node in protocol_classes] == ["SecuritySnapshotReadPort"]
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    forbidden_behavior = (
        "GovernedAssetReference",
        "ProviderTrustReference",
        "EvalEgressPolicyDecision",
        "AuthorizedEgressManifest",
        "TransformationPlanReference",
        "CLASSIFICATION_ORDER",
        "_TRAINING_RESTRICTIVENESS",
        "EvalRun(",
        "EvalResult(",
        "GovernanceEvidence",
        "provider_response",
        "open(",
        "subprocess",
        "socket",
        "requests",
        "httpx",
    )
    assert not any(term in source for term in forbidden_behavior)


def test_evidence_projection_reuses_frozen_governance_port_and_has_no_runtime() -> None:
    paths = (
        ROOT / "evidence.py",
        ROOT / "evidence_errors.py",
        ROOT / "evidence_projection.py",
    )
    imports = {module for path in paths for module in imports_for(path)}
    assert not (ROOT / "evidence_contracts.py").exists()
    assert "synapse.project_governance.contracts" in imports
    assert "synapse.project_governance.models" in imports
    assert not any(
        module.startswith(
            (
                "synapse.project_governance.runtime",
                "synapse.storage",
                "synapse.api",
                "synapse.commands",
                "synapse.bootstrap",
            )
        )
        for module in imports
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "RFCEvidenceWritePort" in source
    forbidden_behavior = (
        "ProjectGovernanceRuntime",
        "EvidenceRegistry",
        "EvalEvidenceSubmissionPort",
        "EvidenceSubmissionStatus",
        "evaluate_gate",
        "execute_quality_gate",
        "EvalRun(",
        "EvalResult(",
        "open(",
        "subprocess",
        "socket",
        "requests",
        "httpx",
    )
    assert not any(term in source for term in forbidden_behavior)


def test_evidence_submission_uses_governance_port_directly_and_only_local_coordination() -> None:
    paths = (
        ROOT / "evidence_submission.py",
        ROOT / "evidence_submission_models.py",
        ROOT / "evidence_submission_errors.py",
        ROOT / "evidence_submission_service.py",
    )
    imports = {module for path in paths for module in imports_for(path)}
    assert "synapse.project_governance.contracts" in imports
    assert "synapse.project_governance.models" in imports
    assert not any(
        module.startswith(
            (
                "synapse.project_governance.runtime",
                "synapse.storage",
                "synapse.api",
                "synapse.commands",
                "synapse.bootstrap",
                "synapse.providers",
                "synapse.missions",
                "synapse.workers",
                "synapse.swarm",
            )
        )
        for module in imports
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "RFCEvidenceWritePort" in source
    assert "EvalEvidenceProjectionFactory" in source
    assert "EvidenceSubmissionRecordStatus" not in source
    assert 'GOVERNANCE_WRITE_STARTED = "governance_write_started"' in source
    forbidden_behavior = (
        "EvalEvidenceSubmissionPort",
        "ProjectGovernanceRuntime",
        "evaluate_gate",
        "approval_status",
        "approve(",
        "promote_baseline",
        "ComparisonEngine",
        "RegressionDetector",
        "EvalCaseEvaluatorPort",
        "EvalCaseExecutionPort",
        "update_run",
        "apply_finalization",
        "open(",
        "subprocess",
        "socket",
        "requests",
        "httpx",
    )
    assert not any(term in source for term in forbidden_behavior)


def test_case_execution_has_one_consumer_port_and_no_concrete_execution() -> None:
    paths = (
        ROOT / "execution.py",
        ROOT / "execution_contracts.py",
        ROOT / "execution_errors.py",
        ROOT / "execution_policy.py",
        ROOT / "execution_records.py",
    )
    imports = {module for path in paths for module in imports_for(path)}
    forbidden_prefixes = (
        "synapse.missions",
        "synapse.workers",
        "synapse.swarm",
        "synapse.sandbox",
        "synapse.providers",
        "synapse.model_providers",
        "synapse.storage",
        "synapse.api",
        "synapse.commands",
        "synapse.bootstrap",
    )
    assert not any(module.startswith(forbidden_prefixes) for module in imports)
    contracts_tree = ast.parse((ROOT / "execution_contracts.py").read_text(encoding="utf-8"))
    protocol_classes = [
        node
        for node in contracts_tree.body
        if isinstance(node, ast.ClassDef)
        and any(isinstance(base, ast.Name) and base.id == "Protocol" for base in node.bases)
    ]
    assert [node.name for node in protocol_classes] == ["EvalCaseExecutionPort"]
    methods = [
        node.name
        for node in protocol_classes[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    assert methods == ["execute_case"]
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    forbidden_behavior = (
        "EvalRunStore",
        "EvalRun(",
        "EvalResult(",
        "ScoringEngine",
        "EvalEvidence",
        "subprocess",
        "socket",
        "requests",
        "httpx",
        "open(",
        "exec(",
        "eval(",
        "callback",
        "callable",
        "recover(",
        "cancel(",
    )
    assert not any(term in source for term in forbidden_behavior)


def test_result_materialization_uses_only_output_store_and_has_no_future_behavior() -> None:
    paths = (
        ROOT / "result_errors.py",
        ROOT / "result_models.py",
        ROOT / "result_materialization.py",
    )
    imports = {module for path in paths for module in imports_for(path)}
    assert "contracts" in imports
    assert not any(
        module.startswith(
            (
                "synapse.missions",
                "synapse.workers",
                "synapse.swarm",
                "synapse.sandbox",
                "synapse.providers",
                "synapse.model_providers",
                "synapse.storage",
                "synapse.api",
                "synapse.commands",
                "synapse.bootstrap",
            )
        )
        for module in imports
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "EvalMaterializationStore" in source
    allowed_store_methods = {
        "materialized_output_exists",
        "get_materialized_output_for_execution",
        "save_materialized_output",
    }
    tree = ast.parse((ROOT / "result_materialization.py").read_text(encoding="utf-8"))
    store_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "store"
    }
    assert store_calls == allowed_store_methods
    forbidden_behavior = (
        "update_run",
        "complete_run",
        "Finalization",
        "ScoringEngine",
        ".score(",
        "EvalEvidence",
        "EvidenceRecord",
        "subprocess",
        "socket",
        "requests",
        "httpx",
        "open(",
        "exec(",
        "eval(",
    )
    assert not any(term in source for term in forbidden_behavior)


def test_case_evaluation_has_one_consumer_port_and_no_concrete_evaluator() -> None:
    paths = (
        ROOT / "case_evaluation.py",
        ROOT / "case_evaluation_contracts.py",
        ROOT / "case_evaluation_errors.py",
    )
    imports = {module for path in paths for module in imports_for(path)}
    forbidden_prefixes = (
        "synapse.missions",
        "synapse.workers",
        "synapse.swarm",
        "synapse.sandbox",
        "synapse.providers",
        "synapse.model_providers",
        "synapse.storage",
        "synapse.api",
        "synapse.commands",
        "synapse.bootstrap",
    )
    assert not any(module.startswith(forbidden_prefixes) for module in imports)
    contracts_tree = ast.parse((ROOT / "case_evaluation_contracts.py").read_text(encoding="utf-8"))
    protocol_classes = [
        node
        for node in contracts_tree.body
        if isinstance(node, ast.ClassDef)
        and any(isinstance(base, ast.Name) and base.id == "Protocol" for base in node.bases)
    ]
    assert [node.name for node in protocol_classes] == ["EvalCaseEvaluatorPort"]
    methods = [
        node.name
        for node in protocol_classes[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    assert methods == ["evaluate"]
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    forbidden_behavior = (
        "ScoringEngine",
        ".score(",
        "update_run",
        "complete_run",
        "Finalization",
        "EvalEvidence",
        "EvidenceRecord",
        "subprocess",
        "socket",
        "requests",
        "httpx",
        "open(",
        "exec(",
        "eval(",
        "callback",
        "recover(",
        "cancel(",
    )
    assert not any(term in source for term in forbidden_behavior)


def test_private_evals_contracts_have_no_generic_or_concrete_persistence() -> None:
    contracts = (ROOT / "contracts.py").read_text(encoding="utf-8")
    forbidden = (
        "FileCollection",
        "RepositoryBase",
        "Session",
        "UnitOfWork",
        "connection_string",
        "cursor.execute",
        "delete(",
        "def put(",
    )
    assert not any(term in contracts for term in forbidden)


def test_run_scoring_is_the_only_scoring_engine_invocation_boundary() -> None:
    invocation_modules = []
    for path in ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        if ".engine.score(" in source:
            invocation_modules.append(path.name)
    assert invocation_modules == ["run_scoring.py"]
    scoring_source = (ROOT / "scoring.py").read_text(encoding="utf-8")
    assert not any(
        term in scoring_source for term in ("EvalAnalysisStore", "save_", "update_run", "finalize")
    )


def test_run_scoring_has_no_execution_finalization_or_external_side_effects() -> None:
    paths = (
        ROOT / "run_scoring.py",
        ROOT / "run_scoring_errors.py",
        ROOT / "run_scoring_service.py",
    )
    imports = {module for path in paths for module in imports_for(path)}
    forbidden_prefixes = (
        "synapse.missions",
        "synapse.workers",
        "synapse.swarm",
        "synapse.sandbox",
        "synapse.providers",
        "synapse.model_providers",
        "synapse.storage",
        "synapse.api",
        "synapse.commands",
        "synapse.bootstrap",
    )
    assert not any(module.startswith(forbidden_prefixes) for module in imports)
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    forbidden_behavior = (
        "EvalCaseEvaluatorPort",
        "update_run",
        "complete_run",
        "finalize",
        "Finalization",
        "EvalEvidence",
        "EvidenceRecord",
        "Baseline",
        "Comparison",
        "Regression",
        "subprocess",
        "socket",
        "requests",
        "httpx",
        "open(",
        "exec(",
        "eval(",
    )
    assert not any(term in source for term in forbidden_behavior)


def test_run_finalization_has_no_future_or_external_behavior() -> None:
    paths = (
        ROOT / "evaluation_records.py",
        ROOT / "run_finalization.py",
        ROOT / "run_finalization_errors.py",
        ROOT / "run_finalization_models.py",
        ROOT / "run_finalization_policy.py",
        ROOT / "run_finalization_service.py",
    )
    imports = {module for path in paths for module in imports_for(path)}
    forbidden_prefixes = (
        "synapse.project_governance",
        "synapse.missions",
        "synapse.workers",
        "synapse.swarm",
        "synapse.sandbox",
        "synapse.providers",
        "synapse.model_providers",
        "synapse.storage",
        "synapse.api",
        "synapse.commands",
        "synapse.bootstrap",
    )
    assert not any(module.startswith(forbidden_prefixes) for module in imports)
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    forbidden_behavior = (
        "ProjectGovernanceRuntime",
        "EvalEvidenceEmitter",
        "RFCEvidenceWritePort",
        "BaselineFactory",
        "ComparisonEngine",
        "RegressionDetector",
        "EvalCaseEvaluatorPort",
        "EvalCaseExecutionPort",
        "ScoringEngine",
        ".score(",
        ".evaluate(",
        ".execute_case(",
        "subprocess",
        "socket",
        "requests",
        "httpx",
        "open(",
        "exec(",
        "eval(",
    )
    assert not any(term in source for term in forbidden_behavior)
    service_tree = ast.parse((ROOT / "run_finalization_service.py").read_text(encoding="utf-8"))
    transition_calls = {
        node.func.attr
        for node in ast.walk(service_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"apply_finalization", "update_run"}
    }
    assert transition_calls == {"apply_finalization"}


def test_private_evals_introduces_no_bounded_context_cycle() -> None:
    graph = _runtime_context_graph()
    assert len(graph) == 313  # Includes the acyclic JEV decision -> core dependency.
    components = cyclic_components(graph)
    assert all("private_evals" not in members for members, _ in components)
