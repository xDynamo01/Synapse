import pytest

from synapse.intelligence_boundary.errors import EgressDenied
from synapse.intelligence_boundary.models import (
    DataClassification,
    OperatingProfile,
    ProcessingBoundary,
)

from .intelligence_boundary_support import (
    asset,
    boundary_runtime,
    egress_request,
    trust_external,
)


def test_local_sovereign_blocks_external_model_e2e(tmp_path) -> None:
    runtime = boundary_runtime(tmp_path)
    trust_external(runtime)
    asset(runtime, "restricted", DataClassification.RESTRICTED)
    runtime.set_operating_profile(OperatingProfile.LOCAL_SOVEREIGN, actor_id="admin")
    with pytest.raises(EgressDenied):
        runtime.authorize_egress(egress_request(("restricted",)))
    allowed = runtime.authorize_egress(
        egress_request(
            ("restricted",),
            boundary=ProcessingBoundary.LOCAL_MODEL,
            provider_id="local",
        )
    )
    assert allowed.allowed
    assert any(item.status == "local_only" for item in runtime.ledger_history())
