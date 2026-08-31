from synapse.intelligence_boundary.models import ProcessingBoundary

from .intelligence_boundary_support import (
    asset,
    boundary_runtime,
    egress_request,
)


def test_egress_ledger_restart_e2e(tmp_path) -> None:
    runtime = boundary_runtime(tmp_path)
    asset(runtime, "prompt")
    authorized = runtime.authorize_egress(
        egress_request(
            ("prompt",),
            boundary=ProcessingBoundary.LOCAL_MODEL,
            provider_id="local",
        )
    )
    assert authorized.manifest
    runtime.complete_egress(authorized.manifest.manifest_id, result_reference="output-a")
    count = len(runtime.ledger_history())
    restarted = boundary_runtime(tmp_path)
    restarted.complete_egress(
        authorized.manifest.manifest_id, result_reference="output-a"
    )
    assert len(restarted.ledger_history()) == count
