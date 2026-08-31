from synapse.project_governance.models import (
    CriterionStatus,
    EvidenceRecord,
    RFCImplementationBinding,
)

from .project_governance_support import approve, initialize, plan, runtime


def test_rfc_plan_mission_skills_agents_evidence_flow(tmp_path):
    governance = runtime(tmp_path)
    project, _ = initialize(governance)
    rfc = approve(governance)
    implementation = plan(governance)
    binding = RFCImplementationBinding(
        project.project_id,
        rfc.rfc_id,
        rfc.revision,
        rfc.checksum,
        implementation.plan_id,
        implementation.revision,
        implementation.checksum,
    )
    assert governance.validate_binding(binding).allowed
    governance.start_implementation("synapse", "RFC-0001", actor_id="mission")
    evidence = EvidenceRecord(
        "synapse",
        "RFC-0001",
        rfc.revision,
        implementation.plan_id,
        "acceptance_result",
        "Mission, Skills and ephemeral verification completed",
        "evidence/mission.json",
        "checksum",
        "ephemeral:validator",
        "valid",
        mission_id="mission-1",
        task_id="task-1",
    )
    governance.record_evidence(evidence)
    governance.update_criterion(
        implementation.plan_id,
        "acceptance",
        CriterionStatus.SATISFIED,
        actor_id="ephemeral:validator",
        result_reference=evidence.evidence_id,
    )
    assert (
        governance.mark_implemented("synapse", "RFC-0001", actor_id="owner").status == "implemented"
    )
