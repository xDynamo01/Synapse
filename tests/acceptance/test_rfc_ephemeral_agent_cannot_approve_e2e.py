import pytest

from synapse.project_governance.errors import RFCApprovalDenied
from synapse.project_governance.models import ReviewDecision, ReviewRole, RFCReview

from .project_governance_support import initialize, runtime


def test_ephemeral_agent_can_review_but_cannot_approve(tmp_path):
    governance = runtime(tmp_path)
    _, rfc = initialize(governance)
    review = RFCReview(
        "synapse",
        "RFC-0001",
        rfc.revision,
        "ephemeral:reviewer",
        "ephemeral_agent",
        ReviewRole.TECHNICAL_REVIEWER,
        ReviewDecision.COMMENT,
        "Analysis.",
        "risk",
        "risk-1",
    )
    assert governance.reviews.record(review).decision == "comment"
    with pytest.raises(RFCApprovalDenied):
        governance.reviews.approve(
            RFCReview(
                "synapse",
                "RFC-0001",
                rfc.revision,
                "ephemeral:reviewer",
                "ephemeral_agent",
                ReviewRole.TECHNICAL_REVIEWER,
                ReviewDecision.APPROVE,
                "Approve.",
                "risk",
                "risk-1",
            )
        )
