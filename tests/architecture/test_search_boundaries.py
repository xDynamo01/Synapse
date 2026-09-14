from __future__ import annotations

import ast
from pathlib import Path

import synapse.search as search

from .support import SOURCE_ROOT, context_graph, cyclic_components
from .test_audio_speech_boundary import _runtime_context_graph, _runtime_imports

SEARCH_ROOT = SOURCE_ROOT / "search"
SEARCH_ADAPTERS_ROOT = SOURCE_ROOT / "search_adapters"
SEARCH_INTEGRATIONS_ROOT = SOURCE_ROOT / "search_integrations"
SEARCH_COMPOSITION_ROOT = SOURCE_ROOT / "search_composition"


def test_search_is_pure_provider_neutral_and_non_executable() -> None:
    paths = tuple(sorted(SEARCH_ROOT.rglob("*.py")))
    imports = {module for path in paths for module in _runtime_imports(path)}
    assert not any(module.startswith("synapse.") for module in imports)
    forbidden_imports = {
        "httpx",
        "requests",
        "aiohttp",
        "urllib",
        "socket",
        "subprocess",
        "multiprocessing",
        "sqlite3",
        "pathlib",
    }
    assert forbidden_imports.isdisjoint(imports)
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "searxng" not in source.lower()
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
    assert not attribute_calls.intersection({"system", "Popen", "urlopen"})


def test_only_bootstrap_wiring_depends_on_search_outside_search_contexts() -> None:
    imports = [
        (path.relative_to(SOURCE_ROOT), module)
        for path in SOURCE_ROOT.rglob("*.py")
        if (
            SEARCH_ROOT not in path.parents
            and SEARCH_ADAPTERS_ROOT not in path.parents
            and SEARCH_INTEGRATIONS_ROOT not in path.parents
            and SEARCH_COMPOSITION_ROOT not in path.parents
        )
        for module in _runtime_imports(path)
        if module.startswith("synapse.search")
    ]
    assert set(imports) == {
        (Path("bootstrap/adapters/search.py"), "synapse.search"),
        (Path("bootstrap/adapters/search.py"), "synapse.search_adapters"),
        (Path("bootstrap/adapters/search.py"), "synapse.search_composition"),
        (Path("bootstrap/adapters/search.py"), "synapse.search_integrations"),
        (Path("bootstrap/adapters/search.py"), "synapse.search_integrations.governance"),
        (Path("bootstrap/container.py"), "synapse.search_composition"),
    }


def test_search_adapters_depend_only_on_search_and_http_is_retrieval_owned() -> None:
    paths = tuple(sorted(SEARCH_ADAPTERS_ROOT.rglob("*.py")))
    imports = {module for path in paths for module in _runtime_imports(path)}
    synapse_imports = {module for module in imports if module.startswith("synapse.")}
    assert synapse_imports == {"synapse.search"}
    assert not imports.intersection({"httpx", "requests", "aiohttp"})
    assert "urllib.request" in imports
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    tree = ast.parse(source)
    attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not attributes.intersection({"urlopen", "post", "send"})
    assert not any(
        module.startswith(
            (
                "synapse.agents",
                "synapse.tools",
                "synapse.perception",
                "synapse.desktop_automation",
                "synapse.bootstrap",
            )
        )
        for module in imports
    )


def test_http_retrieval_adapter_has_no_extraction_parser_or_durable_store() -> None:
    path = SEARCH_ADAPTERS_ROOT / "http_retrieval.py"
    imports = set(_runtime_imports(path))
    assert imports.isdisjoint(
        {
            "bs4",
            "lxml",
            "pypdf",
            "pdfplumber",
            "sqlite3",
            "pathlib",
            "tempfile",
        }
    )
    source = path.read_text(encoding="utf-8")
    assert "ExtractedContentV1" not in source
    assert "BeautifulSoup" not in source
    assert "webdriver" not in source


def test_text_extraction_adapter_is_local_parser_only_and_has_no_active_authority() -> None:
    path = SEARCH_ADAPTERS_ROOT / "text_extraction.py"
    imports = set(_runtime_imports(path))
    assert "html.parser" in imports
    assert imports.isdisjoint(
        {
            "urllib",
            "urllib.request",
            "httpx",
            "requests",
            "aiohttp",
            "socket",
            "subprocess",
            "bs4",
            "lxml",
            "pypdf",
            "pdfplumber",
            "playwright",
            "selenium",
            "sqlite3",
            "pathlib",
            "tempfile",
        }
    )
    source = path.read_text(encoding="utf-8")
    assert "RetrievalRequestV1" not in source
    assert "AgentSummaryReference" not in source
    assert "urlopen" not in source
    assert "BeautifulSoup" not in source


def test_search_cache_contracts_are_pure_separated_and_have_no_backend() -> None:
    path = SEARCH_ROOT / "cache.py"
    imports = set(_runtime_imports(path))
    assert imports.isdisjoint(
        {
            "sqlite3",
            "pathlib",
            "tempfile",
            "urllib",
            "urllib.request",
            "httpx",
            "requests",
            "aiohttp",
            "socket",
            "subprocess",
        }
    )
    source = path.read_text(encoding="utf-8")
    assert "class SearchCachePort(Protocol)" in source
    assert "class RetrievalCachePort(Protocol)" in source
    assert "class ExtractionCachePort(Protocol)" in source
    assert "class SQLite" not in source
    assert "def urlopen" not in source


def test_search_sqlite_persistence_is_metadata_only_and_adapter_owned() -> None:
    path = SEARCH_ADAPTERS_ROOT / "sqlite_persistence.py"
    imports = set(_runtime_imports(path))
    assert "sqlite3" in imports
    assert "pathlib" in imports
    assert {item for item in imports if item.startswith("synapse.")} == {"synapse.search"}
    assert not any(
        item.startswith(
            (
                "synapse.agents",
                "synapse.tools",
                "synapse.perception",
                "synapse.conversations",
                "synapse.desktop_automation",
                "synapse.bootstrap",
            )
        )
        for item in imports
    )
    source = path.read_text(encoding="utf-8")
    assert "BEFORE UPDATE" in source and "BEFORE DELETE" in source
    assert "raw_body" not in source
    assert "extracted_text TEXT" not in source
    assert "urlopen" not in source
    assert "requests." not in source


def test_search_adapter_edge_is_unidirectional_and_creates_no_scc() -> None:
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
    assert {
        edge for edge in runtime if edge[0].startswith("search") or edge[1] == "search"
    } == expected
    assert {
        edge for edge in source if edge[0].startswith("search") or edge[1] == "search"
    } == expected
    assert all("search_adapters" not in members for members, _ in cyclic_components(runtime))
    assert all("search_adapters" not in members for members, _ in cyclic_components(source))
    assert all("search_integrations" not in members for members, _ in cyclic_components(runtime))
    assert all("search_integrations" not in members for members, _ in cyclic_components(source))


def test_search_domain_has_no_outgoing_edges_or_scc_membership() -> None:
    runtime = _runtime_context_graph()
    source = context_graph()
    assert len(runtime) == 306  # Primary MoM: api -> mom -> core.
    assert len(source) == 341  # Primary MoM adds the same two source edges.
    assert not {edge for edge in runtime if edge[0] == "search"}
    assert not {edge for edge in source if edge[0] == "search"}
    assert all("search" not in members for members, _ in cyclic_components(runtime))
    assert all("search" not in members for members, _ in cyclic_components(source))


def test_search_initial_module_and_public_surface_are_deliberate() -> None:
    assert tuple(path.name for path in sorted(SEARCH_ROOT.glob("*.py"))) == (
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
    assert len(search.__all__) == 179
    assert "search" not in search.__all__
    assert "SearchProviderPort" in search.__all__
    assert "SearXNGAdapter" not in search.__all__


def test_operational_searxng_transport_has_no_authority_or_domain_parsing() -> None:
    transport = SEARCH_ADAPTERS_ROOT / "searxng_transport.py"
    imports = set(_runtime_imports(transport))
    assert "urllib.request" in imports
    assert {item for item in imports if item.startswith("synapse.")} == {"synapse.search"}
    assert not any(
        item.startswith(
            (
                "synapse.intelligence_boundary",
                "synapse.agents",
                "synapse.tools",
                "synapse.bootstrap",
            )
        )
        for item in imports
    )
    source = transport.read_text(encoding="utf-8")
    assert "NormalizedSearchResultV1" not in source
    assert "provider_snippet" not in source
    assert "Authorization" not in source


def test_search_execution_authority_is_consumer_owned_and_not_bootstrapped() -> None:
    execution = SEARCH_INTEGRATIONS_ROOT / "execution.py"
    imports = set(_runtime_imports(execution))
    assert {item for item in imports if item.startswith("synapse.")} == {
        "synapse.search",
        "synapse.search_adapters",
        "synapse.search_adapters.searxng_transport",
    }
    assert not any(item.startswith(("synapse.agents", "synapse.tools", "synapse.bootstrap")) for item in imports)


def test_search_tool_consumer_does_not_bypass_integration_or_add_agent_provider_edge() -> None:
    tool_paths = (SOURCE_ROOT / "tools" / "search.py", SOURCE_ROOT / "tools" / "builtin.py")
    tool_imports = {module for path in tool_paths for module in _runtime_imports(path)}
    assert not any(
        module.startswith(
            (
                "synapse.search_adapters",
                "synapse.intelligence_boundary",
                "urllib",
                "httpx",
                "requests",
            )
        )
        for module in tool_imports
    )
    agent_imports = {
        module
        for path in (SOURCE_ROOT / "agents").rglob("*.py")
        for module in _runtime_imports(path)
    }
    assert not any(
        module.startswith(("synapse.search_adapters", "synapse.search_integrations"))
        for module in agent_imports
    )
    source = (SOURCE_ROOT / "tools" / "builtin.py").read_text(encoding="utf-8")
    assert '"status": "unconfigured"' not in source
    assert "SearXNG" not in source


def test_search_evidence_projection_is_consumer_owned_reference_only_and_non_executable() -> None:
    path = SEARCH_INTEGRATIONS_ROOT / "evidence.py"
    imports = set(_runtime_imports(path))
    assert {item for item in imports if item.startswith("synapse.")} == {"synapse.search"}
    assert imports.isdisjoint(
        {
            "urllib",
            "urllib.request",
            "httpx",
            "requests",
            "aiohttp",
            "socket",
            "subprocess",
        }
    )
    source = path.read_text(encoding="utf-8")
    assert "class SearchResultRetrievalHandoffV1" in source
    assert "class SearchSourceEvidenceV1" in source
    assert "urlopen" not in source
    assert "citation_text" not in source
    assert "truth_score" not in source
    assert "agent_summary" not in source
    assert "synapse.project_governance" not in source
    assert "synapse.private_evals" not in source


def test_search_composition_is_opt_in_unidirectional_and_bootstrapped_only_by_adapter() -> None:
    imports = {
        module
        for path in SEARCH_COMPOSITION_ROOT.rglob("*.py")
        for module in _runtime_imports(path)
    }
    assert {item for item in imports if item.startswith("synapse.")} == {
        "synapse.search",
        "synapse.search_adapters",
        "synapse.search_integrations",
        "synapse.search_integrations.governance",
    }
    reverse = [
        (path.relative_to(SOURCE_ROOT), module)
        for root in (SEARCH_ROOT, SEARCH_ADAPTERS_ROOT, SEARCH_INTEGRATIONS_ROOT)
        for path in root.rglob("*.py")
        for module in _runtime_imports(path)
        if module.startswith("synapse.search_composition")
    ]
    assert reverse == []
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
