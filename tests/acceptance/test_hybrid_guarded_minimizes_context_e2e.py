from synapse.intelligence_boundary.models import DataClassification

from .intelligence_boundary_support import (
    asset,
    boundary_runtime,
    egress_request,
    trust_external,
)


def test_hybrid_guarded_minimizes_context_e2e(tmp_path) -> None:
    runtime = boundary_runtime(tmp_path)
    trust_external(runtime)
    asset(runtime, "memory", relevant=False)
    asset(runtime, "rfc", DataClassification.CONFIDENTIAL, category="project.rfc")
    preview = runtime.preview_egress(egress_request(("memory", "rfc")))
    assert preview.decision.minimization_plan.omitted_assets == ("memory",)
    assert preview.decision.redaction_plan is not None
    assert preview.manifest and preview.manifest.checksum
