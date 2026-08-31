from synapse.project_governance.models import EvidenceRecord

from .project_governance_support import approve, initialize, plan, runtime


def test_restart_recovers_partial_execution_without_duplicate_promotion(tmp_path):
    first = runtime(tmp_path)
    initialize(first)
    rfc = approve(first)
    implementation = plan(first)
    first.start_implementation("synapse", "RFC-0001", actor_id="mission")
    first.record_evidence(
        EvidenceRecord(
            "synapse",
            "RFC-0001",
            rfc.revision,
            implementation.plan_id,
            "test_result",
            "Partial tests",
            "evidence/partial.json",
            "checksum",
            "validator",
            "valid",
        )
    )
    restarted = runtime(tmp_path)
    assert restarted.rfcs.get("synapse", "RFC-0001").status == "implementing"
    assert len(restarted.evidence.list("synapse")) == 1
    assert restarted.plans.get(implementation.plan_id).status == "validated"
