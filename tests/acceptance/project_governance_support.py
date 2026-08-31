from pathlib import Path

from synapse.bootstrap.adapters.project_governance import (
    FileProjectDocumentAdapter,
    GovernanceRecordStoreAdapter,
)
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.project_governance.models import (
    AcceptanceCriterion,
    ChangeClass,
    ImplementationPlan,
    ProjectManifest,
    ReviewDecision,
    ReviewRole,
    RFCManifest,
    RFCReview,
)
from synapse.project_governance.runtime import ProjectGovernanceRuntime
from synapse.storage.collection import FileCollection


def runtime(root: Path) -> ProjectGovernanceRuntime:
    data_dir = DataDir(root)
    data_dir.bootstrap()
    events = EventBus(root)
    stores = {
        name: GovernanceRecordStoreAdapter(
            FileCollection(
                collection_id=f"acceptance_project_governance_{name}",
                root=root / "project_governance" / name,
                current_schema_version=1,
                events=events,
            )
        )
        for name in ("projects", "rfcs", "versions", "reviews", "plans", "evidence", "adrs")
    }
    return ProjectGovernanceRuntime(
        events=events,
        documents=FileProjectDocumentAdapter(data_dir.resolve("projects")),
        stores=stores,
    )


def criterion() -> AcceptanceCriterion:
    return AcceptanceCriterion(
        "acceptance",
        "Required behavior is verified",
        "acceptance",
        "evidence",
        evidence_types=("acceptance_result",),
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
    return "\n\n".join(f"## {item}\n\nDefined." for item in sections)


def initialize(governance: ProjectGovernanceRuntime, *, risk: str = "low"):
    project = governance.projects.register(
        ProjectManifest(
            "synapse",
            "Synapse",
            "Governed project",
            "synapse",
            "owner",
            "default",
            skill_scope={"allowed_skills": ["research-synthesis"]},
        ),
        actor_id="owner",
    )
    rfc = governance.rfcs.create(
        RFCManifest(
            "RFC-0001",
            "synapse",
            "Controlled change",
            ("author",),
            ("reviewer",),
            ("skills",),
            ("SkillResolutionPort",),
            ChangeClass.ARCHITECTURAL,
            risk_level=risk,
            acceptance_criteria=(criterion(),),
            invariants=("no cycle",),
            out_of_scope=("frontend",),
        ),
        markdown(),
        actor_id="author",
    )
    return project, rfc


def approve(governance: ProjectGovernanceRuntime, reviewer: str = "reviewer"):
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
            "Approved.",
            "invariant",
            "no-cycle",
        )
    )


def plan(governance: ProjectGovernanceRuntime):
    rfc = governance.rfcs.get("synapse", "RFC-0001")
    created = governance.plans.create(
        ImplementationPlan(
            "synapse",
            "RFC-0001",
            rfc.revision,
            rfc.checksum,
            "Implement",
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
    return governance.plans.validate(created.plan_id)
