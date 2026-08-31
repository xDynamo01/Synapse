from synapse.project_governance.models import RFCGateRequest

from .project_governance_support import initialize, runtime


def test_rfc_gate_blocks_unspecified_architectural_change(tmp_path):
    governance = runtime(tmp_path)
    initialize(governance)
    decision = governance.evaluate_gate(
        RFCGateRequest(
            "synapse",
            "new architecture",
            ("skills",),
            ("SkillResolutionPort",),
            impact={"architectural": True},
        )
    )
    assert not decision.allowed
    assert decision.disposition == "blocked_missing_rfc"
