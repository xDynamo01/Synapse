from synapse.intelligence_boundary.models import ProcessingBoundary

from .intelligence_boundary_support import (
    asset,
    boundary_runtime,
    egress_request,
    trust_external,
)


def test_provider_fallback_rechecks_egress_e2e(tmp_path) -> None:
    runtime = boundary_runtime(tmp_path)
    trust_external(runtime, "external-a")
    trust_external(runtime, "external-b")
    asset(runtime, "prompt")
    first = runtime.preview_egress(
        egress_request(("prompt",), provider_id="external-a")
    )
    fallback = runtime.preview_egress(
        egress_request(("prompt",), provider_id="external-b")
    )
    assert first.manifest and fallback.manifest
    assert first.manifest.manifest_id != fallback.manifest.manifest_id
    assert fallback.manifest.boundary == ProcessingBoundary.EXTERNAL_PROVIDER
