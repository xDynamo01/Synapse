from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path

import synapse.search as search
import synapse.search_adapters as adapters
import synapse.search_composition as composition
import synapse.search_integrations as integrations
from synapse.search import (
    CacheNamespace,
    ExtractedContentV1,
    ExtractionCapability,
    NormalizedSearchResultV1,
    RetrievalRequestV1,
    RetrievedArtifactV1,
    SearchRequestV1,
)

from .support import SOURCE_ROOT, context_graph, cyclic_components
from .test_audio_speech_boundary import _runtime_context_graph, _runtime_imports

SEARCH_ROOT = SOURCE_ROOT / "search"
ADAPTERS_ROOT = SOURCE_ROOT / "search_adapters"
INTEGRATIONS_ROOT = SOURCE_ROOT / "search_integrations"
COMPOSITION_ROOT = SOURCE_ROOT / "search_composition"


def _modules(root: Path) -> tuple[str, ...]:
    return tuple(path.name for path in sorted(root.glob("*.py")))


def _source(root: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(root.glob("*.py")))


def test_frozen_packages_modules_and_public_exports_are_exact() -> None:
    assert _modules(SEARCH_ROOT) == (
        "__init__.py",
        "cache.py",
        "canonical.py",
        "errors.py",
        "identities.py",
        "models.py",
        "normalization.py",
        "persistence.py",
        "provider.py",
        "results.py",
        "retrieval.py",
    )
    assert _modules(ADAPTERS_ROOT) == (
        "__init__.py",
        "config.py",
        "http_retrieval.py",
        "searxng.py",
        "searxng_transport.py",
        "sqlite_persistence.py",
        "text_extraction.py",
    )
    assert _modules(INTEGRATIONS_ROOT) == (
        "__init__.py",
        "consumer.py",
        "evidence.py",
        "execution.py",
        "governance.py",
        "retrieval_execution.py",
    )
    assert _modules(COMPOSITION_ROOT) == ("__init__.py", "runtime.py")
    surfaces = ((search, 179), (adapters, 34), (integrations, 25), (composition, 12))
    for module, count in surfaces:
        assert len(module.__all__) == len(set(module.__all__)) == count


def test_v1_contracts_taxonomies_and_stage_separation_are_frozen() -> None:
    required = {
        "SearchRequestV1",
        "NormalizedSearchResultV1",
        "SearchResultSetV1",
        "SearchProviderInvocationV1",
        "SearchProviderResultV1",
        "RetrievalRequestV1",
        "RetrievedArtifactV1",
        "ExtractionRequestV1",
        "ExtractedContentV1",
        "SearchCachePort",
        "RetrievalCachePort",
        "ExtractionCachePort",
        "SearchMetadataStorePort",
    }
    assert required.issubset(search.__all__)
    assert {item.value for item in CacheNamespace} == {"search", "retrieval", "extraction"}
    assert ExtractionCapability.PDF_TO_TEXT_FUTURE.value == "pdf_to_text_future"
    result_fields = {item.name for item in fields(NormalizedSearchResultV1)}
    artifact_fields = {item.name for item in fields(RetrievedArtifactV1)}
    extracted_fields = {item.name for item in fields(ExtractedContentV1)}
    assert "retrieval_request_id" not in result_fields
    assert "extraction_request_id" not in artifact_fields
    assert "agent_summary" not in extracted_fields
    assert {item.name for item in fields(RetrievalRequestV1)}.isdisjoint(
        {"authorization", "search_authorization", "execute"}
    )


def test_search_domain_is_pure_provider_neutral_and_has_no_reasoning_authority() -> None:
    imports = {
        module
        for path in SEARCH_ROOT.glob("*.py")
        for module in _runtime_imports(path)
    }
    assert not any(module.startswith("synapse.") for module in imports)
    assert imports.isdisjoint(
        {"urllib", "urllib.request", "httpx", "requests", "socket", "subprocess", "sqlite3"}
    )
    source = _source(SEARCH_ROOT)
    assert "searxng" not in source.lower()
    request_fields = {item.name for item in fields(SearchRequestV1)}
    assert request_fields.isdisjoint(
        {"base_url", "endpoint_path", "engine", "engines", "http_headers", "credentials"}
    )
    class_names = {
        node.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ClassDef)
    }
    assert not any(
        token in name.lower()
        for name in class_names
        for token in ("planner", "synthes", "reasoner", "researchloop", "citationrenderer")
    )


def test_ranking_freshness_snippet_and_evidence_semantics_are_separate() -> None:
    result_fields = {item.name for item in fields(NormalizedSearchResultV1)}
    assert {
        "provider_position",
        "normalized_rank",
        "provider_snippet",
        "publication_date",
        "provider_reported_date",
        "search_occurrence",
        "freshness",
    }.issubset(result_fields)
    assert result_fields.isdisjoint(
        {"agent_relevance", "truth_score", "trust_score", "evidence_conclusion", "citation_text"}
    )
    normalization = (SEARCH_ROOT / "normalization.py").read_text(encoding="utf-8")
    assert "SAME_DOMAIN_ONLY" in normalization
    assert "RepresentativeSelectionRule" in normalization
    evidence = (INTEGRATIONS_ROOT / "evidence.py").read_text(encoding="utf-8")
    assert "ExternalContentTrust.UNTRUSTED" in evidence
    assert "truth_score" not in evidence and "citation_text" not in evidence


def test_network_and_retrieval_authority_require_distinct_authorized_executors() -> None:
    assert "AuthorizedSearXNGExecutor" in integrations.__all__
    assert "AuthorizedHttpRetrievalExecutor" in integrations.__all__
    search_execution = (INTEGRATIONS_ROOT / "execution.py").read_text(encoding="utf-8")
    retrieval_execution = (INTEGRATIONS_ROOT / "retrieval_execution.py").read_text(
        encoding="utf-8"
    )
    assert "AuthorizationEvidenceState.VALID" in search_execution
    assert "AuthorizationEvidenceState.VALID" in retrieval_execution
    assert "SOURCE_RETRIEVAL" in retrieval_execution
    assert "SEARCH_PROVIDER_INVOCATION" in search_execution
    runtime = (COMPOSITION_ROOT / "runtime.py").read_text(encoding="utf-8")
    assert "AuthorizedHttpRetrievalExecutor(retrieval, governance)" in runtime
    assert "if retrieval is not None and governance is not None" in runtime


def test_persistence_schema_append_only_replay_cache_and_privacy_are_frozen() -> None:
    assert search.SEARCH_PERSISTENCE_SCHEMA_VERSION_V1 == 1
    assert adapters.SEARCH_SQLITE_MIGRATION_ID_V1 == "search-metadata-persistence-v1"
    assert adapters.SEARCH_SQLITE_MIGRATION_CHECKSUM_V1 == (
        "922d895d5bad66e5cf2672b198f920258d0d50e971f1ad40c7ed7d39d4b2b9a7"
    )
    sqlite_source = (ADAPTERS_ROOT / "sqlite_persistence.py").read_text(encoding="utf-8")
    assert "BEFORE UPDATE" in sqlite_source and "BEFORE DELETE" in sqlite_source
    assert "raw_body" not in sqlite_source
    assert "extracted_text TEXT" not in sqlite_source
    assert "Authorization" not in sqlite_source
    assert "cookies" not in sqlite_source
    persistence_source = (SEARCH_ROOT / "persistence.py").read_text(encoding="utf-8")
    assert "reconciliation_required" in persistence_source
    assert "PersistedPayloadAvailability" in persistence_source
    cache_source = (SEARCH_ROOT / "cache.py").read_text(encoding="utf-8")
    assert all(name in cache_source for name in ("SearchCachePort", "RetrievalCachePort", "ExtractionCachePort"))


def test_consumer_migration_has_one_path_and_permission_is_not_egress() -> None:
    tool = (SOURCE_ROOT / "tools" / "builtin.py").read_text(encoding="utf-8")
    command = (SOURCE_ROOT / "commands" / "handlers" / "core_operations.py").read_text(
        encoding="utf-8"
    )
    assert tool.count("self._consumer.search") == 1
    assert '"status": "unconfigured"' not in tool
    assert "SearXNG" not in tool and "HttpRetrieval" not in tool and "urllib" not in tool
    assert command.count('self.tools.execute("web_search"') == 1
    assert "SearXNG" not in command and "HttpRetrieval" not in command
    permissions = (SOURCE_ROOT.parents[1] / "data" / "config" / "permissions.yaml").read_text(
        encoding="utf-8"
    )
    assert permissions.count('"web.search"') == 3
    governance = (INTEGRATIONS_ROOT / "governance.py").read_text(encoding="utf-8")
    assert "EXTERNAL_SEARCH" in governance and "EXTERNAL_RETRIEVAL" in governance


def test_composition_is_local_opt_in_build_only_and_bootstrapped_only_by_adapter() -> None:
    runtime = (COMPOSITION_ROOT / "runtime.py").read_text(encoding="utf-8")
    assert "def build_search_runtime(" in runtime
    assert "def initialize_persistence(" in runtime
    build = runtime.split("def build_search_runtime(", 1)[1].split("def _build_persistence", 1)[0]
    assert ".migrate(" not in build
    assert ".execute(" not in build
    assert ".retrieve(" not in build
    assert ".extract(" not in build
    assert ".assess(" not in build
    bootstrap_imports = {
        (path.relative_to(SOURCE_ROOT), module)
        for path in (SOURCE_ROOT / "bootstrap").rglob("*.py")
        for module in _runtime_imports(path)
        if module.startswith("synapse.search_composition")
    }
    assert bootstrap_imports == {
        (Path("bootstrap/adapters/search.py"), "synapse.search_composition"),
        (Path("bootstrap/container.py"), "synapse.search_composition"),
    }


def test_search_dependency_directions_graph_and_scc_baseline_are_frozen() -> None:
    runtime = _runtime_context_graph()
    source = context_graph()
    assert len(runtime) == 306  # Primary MoM: api -> mom -> core.
    assert len(source) == 341  # Primary MoM adds the same two source edges.
    expected = {
        ("search_adapters", "search"),
        ("search_integrations", "intelligence_boundary"),
        ("search_integrations", "search"),
        ("search_integrations", "search_adapters"),
        ("search_composition", "search"),
        ("search_composition", "search_adapters"),
        ("search_composition", "search_integrations"),
    }
    assert {edge for edge in runtime if edge[0].startswith("search") or edge[1] == "search"} == expected
    assert {edge for edge in source if edge[0].startswith("search") or edge[1] == "search"} == expected
    for graph in (runtime, source):
        assert all(not any(name.startswith("search") for name in members) for members, _ in cyclic_components(graph))


def test_no_reverse_dependency_or_global_bootstrap_activation_exists() -> None:
    reverse = [
        (path.relative_to(SOURCE_ROOT), module)
        for root in (SEARCH_ROOT, ADAPTERS_ROOT, INTEGRATIONS_ROOT)
        for path in root.glob("*.py")
        for module in _runtime_imports(path)
        if module.startswith("synapse.search_composition")
    ]
    assert reverse == []
    agent_tool_imports = {
        module
        for root in (SOURCE_ROOT / "agents", SOURCE_ROOT / "tools")
        for path in root.rglob("*.py")
        for module in _runtime_imports(path)
    }
    assert not any(
        module.startswith(("synapse.search_adapters", "synapse.search_composition"))
        for module in agent_tool_imports
    )
