from synapse.project_governance.models import (
    ReviewDecision,
    ReviewRole,
    RFCReview,
    RFCStatus,
)

from .project_governance_support import approve, initialize, markdown, runtime


def test_rfc_clarification_changes_revision_before_approval(tmp_path):
    governance = runtime(tmp_path)
    _, draft = initialize(governance)
    clarification = governance.clarification.analyze({"restart": "recover safely"})
    assert clarification.open_questions
    current = governance.rfcs.transition(
        "synapse", "RFC-0001", RFCStatus.UNDER_REVIEW, actor_id="reviewer"
    )
    governance.reviews.record(
        RFCReview(
            "synapse",
            "RFC-0001",
            current.revision,
            "reviewer",
            "human",
            ReviewRole.TECHNICAL_REVIEWER,
            ReviewDecision.REQUEST_CHANGES,
            "Clarify idempotency.",
            "requirement",
            "idempotency",
        )
    )
    revised = governance.rfcs.revise(
        "synapse",
        "RFC-0001",
        markdown() + "\nIdempotent.",
        actor_id="author",
        change_summary="Clarified idempotency",
    )
    assert revised.revision == draft.revision + 1
    assert approve(governance).status == "approved"
