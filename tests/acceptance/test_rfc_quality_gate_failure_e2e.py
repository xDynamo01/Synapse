import pytest

from synapse.project_governance.errors import EvidenceInvalid
from synapse.project_governance.models import CriterionStatus

from .project_governance_support import approve, initialize, plan, runtime


def test_failed_quality_gate_prevents_implemented(tmp_path):
    governance = runtime(tmp_path)
    initialize(governance)
    approve(governance)
    implementation = plan(governance)
    governance.start_implementation("synapse", "RFC-0001", actor_id="mission")
    governance.update_criterion(
        implementation.plan_id,
        "acceptance",
        CriterionStatus.FAILED,
        actor_id="quality-gate",
        result_reference="evidence/failure.json",
    )
    with pytest.raises(EvidenceInvalid):
        governance.mark_implemented("synapse", "RFC-0001", actor_id="owner")
