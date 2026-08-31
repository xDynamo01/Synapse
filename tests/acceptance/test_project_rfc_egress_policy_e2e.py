import pytest

from synapse.intelligence_boundary.errors import EgressDenied
from synapse.intelligence_boundary.models import DataClassification

from .intelligence_boundary_support import (
    asset,
    boundary_runtime,
    egress_request,
    trust_external,
)


def test_project_rfc_egress_policy_e2e(tmp_path) -> None:
    runtime = boundary_runtime(tmp_path)
    trust_external(runtime)
    asset(
        runtime,
        "rfc",
        DataClassification.CONFIDENTIAL,
        category="project.rfc",
        external_policy="denied",
    )
    with pytest.raises(EgressDenied):
        runtime.authorize_egress(egress_request(("rfc",)))
    assert runtime.ledger_history()[-1].status == "denied"
