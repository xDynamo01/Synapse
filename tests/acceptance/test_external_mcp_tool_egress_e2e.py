from synapse.intelligence_boundary.models import (
    ProcessingBoundary,
    ProviderTrustProfile,
    TrustProfileStatus,
)

from .intelligence_boundary_support import asset, boundary_runtime, egress_request


def test_external_mcp_tool_egress_e2e(tmp_path) -> None:
    runtime = boundary_runtime(tmp_path)
    runtime.register_trust_profile(
        ProviderTrustProfile(
            "trust-mcp", "mcp-a", ProcessingBoundary.EXTERNAL_MCP,
            status=TrustProfileStatus.ACTIVE,
        )
    )
    asset(runtime, "arguments", category="tool.input")
    result = runtime.authorize_egress(
        egress_request(
            ("arguments",),
            boundary=ProcessingBoundary.EXTERNAL_MCP,
            provider_id="mcp-a",
        )
    )
    assert result.allowed and result.manifest
    derived = runtime.register_derived_asset(
        asset_id="mcp-output",
        input_asset_ids=("arguments",),
        source_reference="mcp:mcp-a:tool",
        content_type="application/json",
        output_checksum="output",
        purpose=result.manifest.purpose,
        provider_id="mcp-a",
        manifest_id=result.manifest.manifest_id,
    )
    assert derived.provenance["manifest_id"] == result.manifest.manifest_id
