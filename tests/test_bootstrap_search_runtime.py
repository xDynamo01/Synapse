from __future__ import annotations

from unittest.mock import patch

from tests.test_authorized_searxng_execution import _Handler, server

from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.tools.models import ToolExecutionRequest


def _settings(tmp_path):
    return Settings(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        host="127.0.0.1",
        port=8717,
        default_actor_id="local_owner",
    )


def test_bootstrap_search_remains_unconfigured_without_searxng_url(tmp_path) -> None:
    with patch.dict("os.environ", {"SYNAPSE_SEARXNG_URL": ""}, clear=False):
        runtime = create_runtime(_settings(tmp_path))

    result = runtime.tool_runtime.execute(
        ToolExecutionRequest(
            "web_search",
            {"query": "synapse workplace"},
            caller="local_owner",
            caller_type="user",
        )
    )

    assert result.success
    assert result.output["status"] == "unconfigured"
    assert result.output["provider_configured"] is False


def test_bootstrap_search_wires_configured_searxng_into_web_search_tool(tmp_path) -> None:
    payload = {"results": [{"url": "https://example.com/source", "title": "Source"}]}
    with server(payload=payload) as base_url:
        with patch.dict("os.environ", {"SYNAPSE_SEARXNG_URL": base_url}, clear=False):
            runtime = create_runtime(_settings(tmp_path))
        assert _Handler.requests == 0

        result = runtime.tool_runtime.execute(
            ToolExecutionRequest(
                "web_search",
                {"query": "synapse workplace", "result_limit": 3},
                caller="local_owner",
                caller_type="user",
            )
        )

    assert result.success
    assert result.output["status"] == "results"
    assert result.output["provider_reference"] == "provider:local-searxng"
    assert result.output["results"][0]["title"] == "Source"
    assert _Handler.requests == 1
    assert runtime.search.health().provider_configuration.value == "configured"
