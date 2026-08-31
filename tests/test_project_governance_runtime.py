from __future__ import annotations

from dataclasses import replace

import pytest

from synapse.bootstrap.adapters.project_governance import (
    FileProjectDocumentAdapter,
    GovernanceRecordStoreAdapter,
)
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.project_governance.errors import (
    EvidenceInvalid,
    ProjectConflict,
    RFCApprovalDenied,
    RFCInvalid,
)
from synapse.project_governance.models import (
    AcceptanceCriterion,
    ChangeClass,
    CriterionStatus,
    EvidenceRecord,
    ImplementationPlan,
    ProjectManifest,
    ReviewDecision,
    ReviewRole,
    RFCGateRequest,
    RFCManifest,
    RFCReview,
)
from synapse.project_governance.runtime import ProjectGovernanceRuntime
from synapse.storage.collection import FileCollection


def runtime(tmp_path) -> ProjectGovernanceRuntime:
    data_dir = DataDir(tmp_path)
    data_dir.bootstrap()
    events = EventBus(tmp_path)
    root = data_dir.resolve("project_governance")
    stores = {
        name: GovernanceRecordStoreAdapter(
            FileCollection(
                collection_id=f"test_project_governance_{name}",
                root=root / name,
                current_schema_version=1,
            )
        )
        for name in ("projects", "rfcs", "versions", "reviews", "plans", "evidence", "adrs")
    }
    return ProjectGovernanceRuntime(
        events=events,
        documents=FileProjectDocumentAdapter(data_dir.resolve("projects")),
        stores=stores,
    )


def project() -> ProjectManifest:
    return ProjectManifest(
        project_id="synapse",
        name="Synapse",
        description="Controlled backend",
        root_reference="synapse",
        owner="owner",
        default_policy_id="project-default",
        skill_scope={"allowed_skills": ["research-synthesis"]},
    )


def criterion() -> AcceptanceCriterion:
    return AcceptanceCriterion(
        "tests-green",
        "Global tests remain green",
        "quality_gate",
        "pytest evidence",
        evidence_types=("test_result",),
    )


def manifest(*, risk: str = "low") -> RFCManifest:
    return RFCManifest(
        rfc_id="RFC-0001",
        project_id="synapse",
        title="Governed change",
        authors=("author",),
        reviewers=("reviewer",),
        affected_domains=("skills",),
        affected_contracts=("SkillResolutionPort",),
        change_classification=ChangeClass.ARCHITECTURAL,
        risk_level=risk,
        acceptance_criteria=(criterion(),),
        invariants=("no new cycle",),
        out_of_scope=("frontend",),
    )


def markdown() -> str:
    sections = (
        "Title",
        "Status",
        "Context",
        "Problem",
        "Objectives",
        "Out of Scope",
        "Functional Requirements",
        "Technical Requirements",
        "Invariants",
        "Proposed Architecture",
        "Affected Contracts",
        "Data and Persistence",
        "Lifecycle",
        "Compatibility",
        "Migration",
        "Risks",
        "Rejected Alternatives",
        "Implementation Plan",
        "Required Tests",
        "Required Evals",
        "Acceptance Criteria",
        "Rollback",
        "Open Questions",
    )
    return "\n\n".join(f"## {section}\n\nDefined." for section in sections)


def approve(governance: ProjectGovernanceRuntime, *, reviewer: str = "reviewer"):
    current = governance.rfcs.get("synapse", "RFC-0001")
    return governance.reviews.approve(
        RFCReview(
            "synapse",
            "RFC-0001",
            current.revision,
            reviewer,
            "human",
            ReviewRole.TECHNICAL_REVIEWER,
            ReviewDecision.APPROVE,
            "Scope and invariants are acceptable.",
            "invariant",
            "no-new-cycle",
        )
    )


def test_project_register_update_archive_context_and_restart(tmp_path) -> None:
    first = runtime(tmp_path)
    registered = first.projects.register(project(), actor_id="owner")
    assert registered.checksum
    with pytest.raises(ProjectConflict):
        first.projects.register(project(), actor_id="owner")
    updated = first.projects.update("synapse", {"description": "Updated"}, actor_id="owner")
    assert updated.revision == 2
    restarted = runtime(tmp_path)
    assert restarted.projects.get("synapse").description == "Updated"
    assert restarted.read_project_context("synapse").project_revision == 2
    assert restarted.projects.archive("synapse", actor_id="owner").status == "archived"


def test_rfc_validation_review_revision_checksum_and_ephemeral_block(tmp_path) -> None:
    governance = runtime(tmp_path)
    governance.projects.register(project(), actor_id="owner")
    created = governance.rfcs.create(manifest(), markdown(), actor_id="author")
    assert governance.validation.validate("synapse", "RFC-0001").valid
    blocked = RFCReview(
        "synapse",
        "RFC-0001",
        created.revision,
        "temp-agent",
        "ephemeral_agent",
        ReviewRole.TECHNICAL_REVIEWER,
        ReviewDecision.APPROVE,
        "Analysis only.",
        "criterion",
        "tests-green",
    )
    with pytest.raises(RFCApprovalDenied):
        governance.reviews.approve(blocked)
    approved = approve(governance)
    revised = governance.rfcs.revise(
        "synapse",
        "RFC-0001",
        markdown() + "\n",
        actor_id="author",
        change_summary="Clarified whitespace-normalized content.",
    )
    assert revised.revision == approved.revision + 1
    assert revised.checksum != approved.checksum
    assert len(governance.versions.list("synapse", "RFC-0001")) == 2


def test_gate_plan_staleness_evidence_criteria_and_implemented(tmp_path) -> None:
    governance = runtime(tmp_path)
    governance.projects.register(project(), actor_id="owner")
    governance.rfcs.create(manifest(), markdown(), actor_id="author")
    approved = approve(governance)
    missing = governance.evaluate_gate(
        RFCGateRequest(
            "synapse",
            "architectural change",
            ("skills",),
            ("SkillResolutionPort",),
            impact={"architectural": True},
        )
    )
    assert missing.disposition == "blocked_missing_rfc"
    allowed = governance.evaluate_gate(
        RFCGateRequest(
            "synapse",
            "architectural change",
            ("skills",),
            ("SkillResolutionPort",),
            rfc_id="RFC-0001",
            rfc_revision=approved.revision,
            rfc_checksum=approved.checksum,
            impact={"architectural": True},
        )
    )
    assert allowed.allowed
    plan = governance.plans.create(
        ImplementationPlan(
            "synapse",
            "RFC-0001",
            approved.revision,
            approved.checksum,
            "Implement safely",
            ("skills",),
            ("skills",),
            ("backend/synapse/skills",),
            ("frontend",),
            ({"task_id": "task-1", "objective": "implement"},),
            {"task-1": ()},
            ("research-synthesis",),
            ("pytest",),
            (),
            (),
            (criterion(),),
            "Revert the bounded change.",
            "author",
        )
    )
    governance.start_implementation("synapse", "RFC-0001", actor_id="author")
    with pytest.raises(EvidenceInvalid):
        governance.mark_implemented("synapse", "RFC-0001", actor_id="owner")
    evidence = EvidenceRecord(
        "synapse",
        "RFC-0001",
        approved.revision,
        plan.plan_id,
        "test_result",
        "Tests passed",
        "evidence/tests.json",
        "abc123",
        "validator",
        "valid",
    )
    governance.record_evidence(evidence)
    governance.update_criterion(
        plan.plan_id,
        "tests-green",
        CriterionStatus.SATISFIED,
        actor_id="validator",
        result_reference=evidence.evidence_id,
    )
    assert (
        governance.mark_implemented("synapse", "RFC-0001", actor_id="owner").status == "implemented"
    )


def test_rfc_revision_marks_plan_stale_and_trivial_change_has_no_bureaucracy(tmp_path) -> None:
    governance = runtime(tmp_path)
    governance.projects.register(project(), actor_id="owner")
    governance.rfcs.create(manifest(), markdown(), actor_id="author")
    approved = approve(governance)
    plan = governance.plans.create(
        ImplementationPlan(
            "synapse",
            "RFC-0001",
            approved.revision,
            approved.checksum,
            "Implement",
            ("skills",),
            ("skills",),
            (),
            (),
            ({"task_id": "one"},),
            {"one": ()},
            (),
            (),
            (),
            (),
            (criterion(),),
            "Rollback.",
            "author",
        )
    )
    governance.rfcs.revise(
        "synapse",
        "RFC-0001",
        markdown() + "\nClarified.",
        actor_id="author",
        change_summary="Clarify",
    )
    assert governance.plans.get(plan.plan_id).status == "stale"
    trivial = governance.evaluate_gate(
        RFCGateRequest("synapse", "fix typo", (), (), impact={"documentation_only": True})
    )
    assert trivial.disposition == "allowed_without_rfc"


def test_invalid_rfc_conflicts_scope_staleness_and_redaction_are_structured(tmp_path) -> None:
    governance = runtime(tmp_path)
    governance.projects.register(
        replace(project(), metadata={"token": "secret", "safe": "value"}), actor_id="owner"
    )
    assert governance.projects.get("synapse").metadata == {"safe": "value"}
    first = governance.rfcs.create(manifest(), "## Title\n\nIncomplete.", actor_id="author")
    invalid = governance.validation.validate("synapse", "RFC-0001")
    assert not invalid.valid and "rollback" in invalid.missing_sections
    second = replace(manifest(), rfc_id="RFC-0002", title="Concurrent change")
    governance.rfcs.create(second, markdown(), actor_id="other")
    assert governance.rfcs.conflicts(first) == ("RFC-0002",)
    with pytest.raises(RFCInvalid):
        governance.projects.register(
            replace(project(), project_id="unsafe", root_reference="../outside"),
            actor_id="owner",
        )


def test_critical_rfc_requires_segregated_human_approval_and_waiver_fields(tmp_path) -> None:
    governance = runtime(tmp_path)
    governance.projects.register(project(), actor_id="owner")
    governance.rfcs.create(manifest(risk="critical"), markdown(), actor_id="author")
    current = governance.rfcs.get("synapse", "RFC-0001")
    first = RFCReview(
        "synapse",
        "RFC-0001",
        current.revision,
        "primary",
        "primary_agent",
        ReviewRole.TECHNICAL_REVIEWER,
        ReviewDecision.APPROVE,
        "Technical approval.",
        "risk",
        "critical-risk",
    )
    with pytest.raises(RFCApprovalDenied, match="human approval"):
        governance.reviews.approve(first)
    assert approve(governance, reviewer="human-owner").status == "approved"
    implementation = governance.plans.create(
        ImplementationPlan(
            "synapse",
            "RFC-0001",
            current.revision,
            current.checksum,
            "Implement",
            ("skills",),
            ("skills",),
            (),
            (),
            ({"task_id": "one"},),
            {"one": ()},
            (),
            (),
            (),
            (),
            (criterion(),),
            "Rollback.",
            "author",
        )
    )
    with pytest.raises(EvidenceInvalid, match="Waiver requires"):
        governance.update_criterion(
            implementation.plan_id,
            "tests-green",
            CriterionStatus.WAIVED,
            actor_id="owner",
            waiver={"reason": "accepted"},
        )
    waived = governance.update_criterion(
        implementation.plan_id,
        "tests-green",
        CriterionStatus.WAIVED,
        actor_id="owner",
        waiver={
            "reason": "accepted risk",
            "actor": "owner",
            "policy": "critical-waiver",
            "approval": "approval-1",
        },
    )
    assert waived.status == "waived"
