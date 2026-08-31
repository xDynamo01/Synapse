from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, replace
from typing import Any

from synapse.project_governance.contracts import (
    GovernanceRecordStore,
    ProjectDocumentPort,
    QualityGateExecutionPort,
)
from synapse.project_governance.errors import (
    EvidenceInvalid,
    ImplementationPlanInvalid,
    ProjectConflict,
    ProjectNotFound,
    RFCApprovalDenied,
    RFCInvalid,
    RFCNotFound,
    RFCRevisionConflict,
    RFCTransitionInvalid,
)
from synapse.project_governance.models import (
    AcceptanceCriterion,
    ADRRecord,
    ChangeClass,
    ChangeClassificationResult,
    ClarificationResult,
    CriterionStatus,
    EvalReference,
    EvidenceRecord,
    ImplementationPlan,
    ImplementationPlanStatus,
    ProjectContext,
    ProjectManifest,
    ProjectStatus,
    QualityGateDescriptor,
    ReviewDecision,
    ReviewRole,
    RFCGateRequest,
    RFCGateResult,
    RFCImplementationBinding,
    RFCManifest,
    RFCReview,
    RFCRevision,
    RFCStatus,
    RFCValidationResult,
    now_iso,
)

_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")
_REQUIRED_SECTIONS = (
    "title",
    "status",
    "context",
    "problem",
    "objectives",
    "out of scope",
    "functional requirements",
    "technical requirements",
    "invariants",
    "proposed architecture",
    "affected contracts",
    "data and persistence",
    "lifecycle",
    "compatibility",
    "migration",
    "risks",
    "rejected alternatives",
    "implementation plan",
    "required tests",
    "required evals",
    "acceptance criteria",
    "rollback",
    "open questions",
)
_TRANSITIONS = {
    RFCStatus.DRAFT: {RFCStatus.UNDER_REVIEW, RFCStatus.WITHDRAWN},
    RFCStatus.UNDER_REVIEW: {
        RFCStatus.CHANGES_REQUESTED,
        RFCStatus.APPROVED,
        RFCStatus.REJECTED,
        RFCStatus.WITHDRAWN,
    },
    RFCStatus.CHANGES_REQUESTED: {RFCStatus.DRAFT, RFCStatus.UNDER_REVIEW},
    RFCStatus.APPROVED: {RFCStatus.IMPLEMENTING, RFCStatus.SUPERSEDED},
    RFCStatus.IMPLEMENTING: {RFCStatus.IMPLEMENTED, RFCStatus.SUPERSEDED},
    RFCStatus.IMPLEMENTED: {RFCStatus.SUPERSEDED},
    RFCStatus.SUPERSEDED: set(),
    RFCStatus.REJECTED: set(),
    RFCStatus.WITHDRAWN: set(),
}


def _checksum(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _safe_id(value: str, label: str) -> str:
    if not _ID.fullmatch(value):
        raise RFCInvalid(f"Invalid {label}")
    return value


def _safe_reference(value: str) -> str:
    normalized = value.replace("\\", "/").strip()
    if not normalized or normalized.startswith(("/", "~")) or ":" in normalized:
        raise RFCInvalid("Reference must be relative or opaque")
    if any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise RFCInvalid("Reference contains an unsafe path segment")
    return normalized


def _redact(metadata: dict[str, Any]) -> dict[str, Any]:
    blocked = {"secret", "token", "password", "prompt", "content", "private_eval"}
    return {key: value for key, value in metadata.items() if key.lower() not in blocked}


class ProjectGovernancePolicy:
    def classify(self, request: RFCGateRequest) -> ChangeClassificationResult:
        impact = request.impact
        explicit = impact.get("classification")
        if explicit:
            classification = ChangeClass(str(explicit))
        elif impact.get("destructive"):
            classification = ChangeClass.DESTRUCTIVE
        elif impact.get("removal"):
            classification = ChangeClass.REMOVAL
        elif impact.get("persistence"):
            classification = ChangeClass.PERSISTENCE_CHANGE
        elif impact.get("lifecycle"):
            classification = ChangeClass.LIFECYCLE_CHANGE
        elif impact.get("policy") or impact.get("permissions"):
            classification = ChangeClass.POLICY_CHANGE
        elif request.contracts or impact.get("api") or impact.get("commands"):
            classification = ChangeClass.CONTRACT_CHANGE
        elif impact.get("architectural") or len(request.domains) > 1:
            classification = ChangeClass.ARCHITECTURAL
        elif impact.get("behavioral"):
            classification = ChangeClass.BEHAVIORAL
        elif impact.get("documentation_only") or impact.get("test_only"):
            classification = ChangeClass.LOCAL_NON_BEHAVIORAL
        else:
            classification = ChangeClass.TRIVIAL
        required = classification not in {
            ChangeClass.TRIVIAL,
            ChangeClass.LOCAL_NON_BEHAVIORAL,
        }
        recommended = classification is ChangeClass.BEHAVIORAL
        disposition = (
            "rfc_required"
            if required
            else ("rfc_recommended" if recommended else "rfc_not_required")
        )
        high = classification in {
            ChangeClass.ARCHITECTURAL,
            ChangeClass.CONTRACT_CHANGE,
            ChangeClass.PERSISTENCE_CHANGE,
            ChangeClass.LIFECYCLE_CHANGE,
            ChangeClass.POLICY_CHANGE,
            ChangeClass.DESTRUCTIVE,
            ChangeClass.REMOVAL,
        }
        return ChangeClassificationResult(
            classification,
            disposition,
            (f"classified as {classification.value}",),
            ("technical_reviewer", "owner") if high else ("technical_reviewer",),
            ("test_result", "architecture_check") if high else ("test_result",),
            approval_required=high,
        )

    @staticmethod
    def can_permanently_approve(reviewer_type: str) -> bool:
        return reviewer_type not in {"ephemeral", "ephemeral_agent"}

    @staticmethod
    def critical_requires_human(risk_level: str) -> bool:
        return risk_level in {"high", "critical"}


class ProjectRegistry:
    def __init__(
        self,
        store: GovernanceRecordStore,
        documents: ProjectDocumentPort,
        events: Any,
    ) -> None:
        self.store = store
        self.documents = documents
        self.events = events

    def register(self, manifest: ProjectManifest, *, actor_id: str) -> ProjectManifest:
        _safe_id(manifest.project_id, "project_id")
        root = _safe_reference(manifest.root_reference)
        if any(item.root_reference == root for item in self.list()):
            raise ProjectConflict("Project root reference is already registered")
        prepared = replace(
            manifest,
            root_reference=root,
            metadata=_redact(manifest.metadata),
            checksum="",
        )
        prepared = replace(prepared, checksum=_checksum(asdict(prepared)))
        try:
            self.store.put(prepared.project_id, asdict(prepared), create_only=True)
        except Exception as exc:
            raise ProjectConflict(f"Project already exists: {prepared.project_id}") from exc
        self.documents.write_project(root, asdict(prepared))
        self.events.emit(
            "project.registered",
            actor_id,
            {
                "project_id": prepared.project_id,
                "revision": prepared.revision,
                "checksum": prepared.checksum,
            },
        )
        return prepared

    def get(self, project_id: str) -> ProjectManifest:
        try:
            return _project(self.store.get(project_id))
        except Exception as exc:
            raise ProjectNotFound(f"Project not found: {project_id}") from exc

    def list(self) -> tuple[ProjectManifest, ...]:
        return tuple(_project(item) for item in self.store.list())

    def update(self, project_id: str, updates: dict[str, Any], *, actor_id: str) -> ProjectManifest:
        current = self.get(project_id)
        forbidden = {"project_id", "root_reference", "created_at", "checksum", "revision"}
        if forbidden & updates.keys():
            raise ProjectConflict("Immutable project fields cannot be updated")
        allowed = set(ProjectManifest.__dataclass_fields__) - forbidden
        unknown = set(updates) - allowed
        if unknown:
            raise ProjectConflict(f"Unsupported project fields: {sorted(unknown)}")
        if "metadata" in updates:
            updates["metadata"] = _redact(dict(updates["metadata"]))
        if "status" in updates:
            updates["status"] = ProjectStatus(updates["status"])
        updated = replace(
            current,
            **updates,
            revision=current.revision + 1,
            updated_at=now_iso(),
            checksum="",
        )
        updated = replace(updated, checksum=_checksum(asdict(updated)))
        self.store.put(project_id, asdict(updated), expected_revision=current.revision)
        self.documents.write_project(updated.root_reference, asdict(updated))
        event = (
            "project.archived" if updated.status is ProjectStatus.ARCHIVED else "project.updated"
        )
        self.events.emit(
            event,
            actor_id,
            {
                "project_id": project_id,
                "revision": updated.revision,
                "checksum": updated.checksum,
            },
        )
        return updated

    def archive(self, project_id: str, *, actor_id: str) -> ProjectManifest:
        return self.update(project_id, {"status": ProjectStatus.ARCHIVED}, actor_id=actor_id)

    def pause(self, project_id: str, *, actor_id: str) -> ProjectManifest:
        return self.update(project_id, {"status": ProjectStatus.PAUSED}, actor_id=actor_id)

    def reactivate(self, project_id: str, *, actor_id: str) -> ProjectManifest:
        current = self.get(project_id)
        if current.status not in {ProjectStatus.PAUSED, ProjectStatus.UNAVAILABLE}:
            raise ProjectConflict(f"Project cannot reactivate from {current.status.value}")
        return self.update(project_id, {"status": ProjectStatus.ACTIVE}, actor_id=actor_id)


class RFCVersionStore:
    def __init__(self, store: GovernanceRecordStore) -> None:
        self.store = store

    def add(self, revision: RFCRevision) -> None:
        self.store.put(
            f"{revision.project_id}--{revision.rfc_id}--{revision.revision}",
            asdict(revision),
            create_only=True,
        )

    def list(self, project_id: str, rfc_id: str) -> tuple[RFCRevision, ...]:
        items = self.store.list({"project_id": project_id, "rfc_id": rfc_id})
        return tuple(RFCRevision(**item) for item in sorted(items, key=lambda x: x["revision"]))


class RFCRegistry:
    def __init__(
        self,
        store: GovernanceRecordStore,
        versions: RFCVersionStore,
        documents: ProjectDocumentPort,
        projects: ProjectRegistry,
        plans: GovernanceRecordStore,
        events: Any,
    ) -> None:
        self.store = store
        self.versions = versions
        self.documents = documents
        self.projects = projects
        self.plan_store = plans
        self.events = events

    def create(self, manifest: RFCManifest, markdown: str, *, actor_id: str) -> RFCManifest:
        project = self.projects.get(manifest.project_id)
        _safe_id(manifest.rfc_id, "rfc_id")
        for reference in manifest.affected_references:
            _safe_reference(reference)
        prepared = replace(
            manifest,
            metadata=_redact(manifest.metadata),
            checksum="",
        )
        prepared = replace(prepared, checksum=_rfc_checksum(prepared, markdown))
        try:
            self.store.put(
                _rfc_key(prepared.project_id, prepared.rfc_id),
                asdict(prepared),
                create_only=True,
            )
        except Exception as exc:
            raise RFCRevisionConflict(f"RFC already exists: {prepared.rfc_id}") from exc
        self.versions.add(
            RFCRevision(
                prepared.rfc_id,
                prepared.project_id,
                prepared.revision,
                prepared.checksum,
                actor_id,
                "initial revision",
                None,
            )
        )
        self.documents.write_rfc(
            project.root_reference,
            prepared.rfc_id,
            asdict(prepared),
            markdown,
            revision=prepared.revision,
        )
        self._emit("rfc.created", prepared, actor_id)
        return prepared

    def get(self, project_id: str, rfc_id: str) -> RFCManifest:
        try:
            return _rfc(self.store.get(_rfc_key(project_id, rfc_id)))
        except Exception as exc:
            raise RFCNotFound(f"RFC not found: {project_id}/{rfc_id}") from exc

    def content(self, project_id: str, rfc_id: str) -> str:
        project = self.projects.get(project_id)
        _manifest, markdown = self.documents.read_rfc(project.root_reference, rfc_id)
        return markdown

    def list(
        self,
        project_id: str | None = None,
        *,
        status: str | None = None,
        domain: str | None = None,
    ) -> tuple[RFCManifest, ...]:
        filters = {"project_id": project_id} if project_id else {}
        items = [_rfc(item) for item in self.store.list(filters)]
        if status:
            items = [item for item in items if item.status.value == status]
        if domain:
            items = [item for item in items if domain in item.affected_domains]
        return tuple(items)

    def revise(
        self,
        project_id: str,
        rfc_id: str,
        markdown: str,
        *,
        actor_id: str,
        change_summary: str,
        updates: dict[str, Any] | None = None,
    ) -> RFCManifest:
        current = self.get(project_id, rfc_id)
        if current.status in {RFCStatus.IMPLEMENTED, RFCStatus.SUPERSEDED, RFCStatus.REJECTED}:
            raise RFCTransitionInvalid(f"RFC cannot be revised from {current.status.value}")
        safe_updates = dict(updates or {})
        forbidden = {"project_id", "rfc_id", "revision", "checksum", "created_at"}
        if forbidden & safe_updates.keys():
            raise RFCRevisionConflict("Revision cannot replace immutable RFC identity")
        for reference in safe_updates.get("affected_references", current.affected_references):
            _safe_reference(reference)
        revised = replace(
            current,
            **safe_updates,
            revision=current.revision + 1,
            status=RFCStatus.DRAFT,
            approved_at=None,
            updated_at=now_iso(),
            checksum="",
        )
        revised = replace(revised, checksum=_rfc_checksum(revised, markdown))
        self.store.put(
            _rfc_key(project_id, rfc_id),
            asdict(revised),
            expected_revision=current.revision,
        )
        self.versions.add(
            RFCRevision(
                rfc_id,
                project_id,
                revised.revision,
                revised.checksum,
                actor_id,
                change_summary,
                current.revision,
            )
        )
        project = self.projects.get(project_id)
        self.documents.write_rfc(
            project.root_reference,
            rfc_id,
            asdict(revised),
            markdown,
            revision=revised.revision,
        )
        self._stale_plans(project_id, rfc_id, revised.revision)
        self._emit("rfc.revised", revised, actor_id)
        return revised

    def transition(
        self,
        project_id: str,
        rfc_id: str,
        target: RFCStatus,
        *,
        actor_id: str,
        extra: dict[str, Any] | None = None,
    ) -> RFCManifest:
        current = self.get(project_id, rfc_id)
        if target not in _TRANSITIONS[current.status]:
            raise RFCTransitionInvalid(f"{current.status.value} -> {target.value} is not allowed")
        updated = replace(
            current,
            status=target,
            updated_at=now_iso(),
            **(extra or {}),
        )
        markdown = self.content(project_id, rfc_id)
        self.store.put(
            _rfc_key(project_id, rfc_id),
            asdict(updated),
            expected_revision=current.revision,
        )
        project = self.projects.get(project_id)
        self.documents.write_rfc(
            project.root_reference,
            rfc_id,
            asdict(updated),
            markdown,
            revision=updated.revision,
        )
        self._emit(f"rfc.{target.value}", updated, actor_id)
        return updated

    def conflicts(self, manifest: RFCManifest) -> tuple[str, ...]:
        active = {
            RFCStatus.DRAFT,
            RFCStatus.UNDER_REVIEW,
            RFCStatus.CHANGES_REQUESTED,
            RFCStatus.APPROVED,
            RFCStatus.IMPLEMENTING,
        }
        contracts = set(manifest.affected_contracts)
        return tuple(
            item.rfc_id
            for item in self.list(manifest.project_id)
            if item.rfc_id != manifest.rfc_id
            and item.status in active
            and contracts.intersection(item.affected_contracts)
        )

    def _stale_plans(self, project_id: str, rfc_id: str, revision: int) -> None:
        for raw in self.plan_store.list({"project_id": project_id, "rfc_id": rfc_id}):
            if raw["rfc_revision"] >= revision or raw["status"] == "stale":
                continue
            raw["status"] = "stale"
            raw["revision"] += 1
            raw["updated_at"] = now_iso()
            raw["checksum"] = _checksum({**raw, "checksum": ""})
            self.plan_store.put(raw["plan_id"], raw, expected_revision=raw["revision"] - 1)
            self.events.emit(
                "implementation_plan.stale",
                "project_governance",
                {
                    "project_id": project_id,
                    "rfc_id": rfc_id,
                    "plan_id": raw["plan_id"],
                    "reason": "rfc_revision_changed",
                },
            )

    def _emit(self, event_type: str, manifest: RFCManifest, actor_id: str) -> None:
        self.events.emit(
            event_type,
            actor_id,
            {
                "project_id": manifest.project_id,
                "rfc_id": manifest.rfc_id,
                "revision": manifest.revision,
                "checksum": manifest.checksum,
                "status": manifest.status.value,
            },
        )


class RFCValidationRuntime:
    def __init__(self, registry: RFCRegistry) -> None:
        self.registry = registry
        self.last_validation: str | None = None

    def validate(self, project_id: str, rfc_id: str) -> RFCValidationResult:
        manifest = self.registry.get(project_id, rfc_id)
        markdown = self.registry.content(project_id, rfc_id)
        headings = {
            re.sub(r"\s+", " ", item.strip().lower())
            for item in re.findall(r"^#{1,6}\s+(.+?)\s*$", markdown, flags=re.MULTILINE)
        }
        missing = tuple(section for section in _REQUIRED_SECTIONS if section not in headings)
        questions: tuple[str, ...] = ()
        open_match = re.search(
            r"^#{1,6}\s+Open Questions\s*$([\s\S]*?)(?=^#|\Z)",
            markdown,
            flags=re.MULTILINE | re.IGNORECASE,
        )
        if (
            open_match
            and "none" not in open_match.group(1).lower()
            and "not_applicable" not in open_match.group(1).lower()
        ):
            questions = tuple(
                line.strip(" -*")
                for line in open_match.group(1).splitlines()
                if line.strip().startswith(("-", "*"))
            )
        conflicts = self.registry.conflicts(manifest)
        missing_evals = tuple(
            item.eval_id
            for item in manifest.required_evals
            if item.required and not item.dataset_reference
        )
        missing_criteria = ("acceptance_criteria",) if not manifest.acceptance_criteria else ()
        checksum_valid = manifest.checksum == _rfc_checksum(manifest, markdown)
        warnings = () if checksum_valid else ("checksum mismatch",)
        self.last_validation = now_iso()
        return RFCValidationResult(
            valid=not (
                missing or conflicts or missing_evals or missing_criteria or not checksum_valid
            ),
            warnings=warnings,
            missing_sections=missing,
            unresolved_questions=questions,
            conflicting_rfcs=conflicts,
            missing_evals=missing_evals,
            missing_acceptance_criteria=missing_criteria,
        )


class RFCReviewRuntime:
    def __init__(
        self,
        registry: RFCRegistry,
        validation: RFCValidationRuntime,
        store: GovernanceRecordStore,
        policy: ProjectGovernancePolicy,
        events: Any,
    ) -> None:
        self.registry = registry
        self.validation = validation
        self.store = store
        self.policy = policy
        self.events = events

    def record(self, review: RFCReview) -> RFCReview:
        manifest = self.registry.get(review.project_id, review.rfc_id)
        if review.rfc_revision != manifest.revision:
            raise RFCRevisionConflict("Review targets a stale RFC revision")
        if not review.reference_id.strip():
            raise RFCInvalid("Structured review reference is required")
        if review.decision is ReviewDecision.APPROVE:
            self._assert_approval_allowed(manifest, review)
        self.store.put(review.review_id, asdict(review), create_only=True)
        self.events.emit(
            "rfc.reviewed",
            review.reviewer_id,
            {
                "project_id": review.project_id,
                "rfc_id": review.rfc_id,
                "revision": review.rfc_revision,
                "review_id": review.review_id,
                "decision": review.decision.value,
                "reference_type": review.reference_type,
                "reference_id": review.reference_id,
            },
        )
        if review.decision is ReviewDecision.REQUEST_CHANGES:
            self.registry.transition(
                review.project_id,
                review.rfc_id,
                RFCStatus.CHANGES_REQUESTED,
                actor_id=review.reviewer_id,
            )
        return review

    def list(self, project_id: str, rfc_id: str) -> tuple[RFCReview, ...]:
        return tuple(
            _review(item) for item in self.store.list({"project_id": project_id, "rfc_id": rfc_id})
        )

    def approve(self, review: RFCReview) -> RFCManifest:
        if review.decision is not ReviewDecision.APPROVE:
            raise RFCApprovalDenied("Approve requires an approve review decision")
        manifest = self.registry.get(review.project_id, review.rfc_id)
        if manifest.status is RFCStatus.DRAFT:
            manifest = self.registry.transition(
                review.project_id,
                review.rfc_id,
                RFCStatus.UNDER_REVIEW,
                actor_id=review.reviewer_id,
            )
            review = replace(review, rfc_revision=manifest.revision)
        result = self.validation.validate(review.project_id, review.rfc_id)
        if not result.valid:
            raise RFCApprovalDenied("Structurally invalid RFC cannot be approved")
        self.record(review)
        approvals = [
            item
            for item in self.list(review.project_id, review.rfc_id)
            if item.decision is ReviewDecision.APPROVE
        ]
        approved_roles = {item.role.value for item in approvals}
        missing_roles = set(manifest.required_approvals) - approved_roles
        if missing_roles:
            raise RFCApprovalDenied(f"Required approval roles are missing: {sorted(missing_roles)}")
        if self.policy.critical_requires_human(manifest.risk_level):
            if not any(item.reviewer_type in {"human", "owner", "admin"} for item in approvals):
                raise RFCApprovalDenied("Critical RFC requires human approval")
            if len({item.reviewer_id for item in approvals}) < 2:
                raise RFCApprovalDenied("Critical RFC requires segregated approval")
        return self.registry.transition(
            review.project_id,
            review.rfc_id,
            RFCStatus.APPROVED,
            actor_id=review.reviewer_id,
            extra={"approved_at": now_iso()},
        )

    def reject(self, review: RFCReview) -> RFCManifest:
        if review.decision is not ReviewDecision.REJECT:
            raise RFCApprovalDenied("Reject requires a reject review decision")
        manifest = self.registry.get(review.project_id, review.rfc_id)
        if manifest.status is RFCStatus.DRAFT:
            manifest = self.registry.transition(
                review.project_id,
                review.rfc_id,
                RFCStatus.UNDER_REVIEW,
                actor_id=review.reviewer_id,
            )
            review = replace(review, rfc_revision=manifest.revision)
        self.record(review)
        return self.registry.transition(
            review.project_id,
            review.rfc_id,
            RFCStatus.REJECTED,
            actor_id=review.reviewer_id,
        )

    def _assert_approval_allowed(self, manifest: RFCManifest, review: RFCReview) -> None:
        if not self.policy.can_permanently_approve(review.reviewer_type):
            raise RFCApprovalDenied("Ephemeral agents cannot permanently approve RFCs")
        segregation = manifest.risk_level in {"high", "critical"}
        if segregation and review.reviewer_id in manifest.authors:
            raise RFCApprovalDenied("Author cannot approve own critical revision")


class RequirementClarificationRuntime:
    _TOPICS = (
        "failure_behavior",
        "null_empty",
        "idempotency",
        "concurrency",
        "restart",
        "authority",
        "ownership",
        "lifecycle",
        "retention",
        "external_egress",
        "permissions",
        "compatibility",
        "cancellation",
        "rollback",
    )

    def analyze(self, decisions: dict[str, str], *, max_questions: int = 8) -> ClarificationResult:
        missing = [topic for topic in self._TOPICS if topic not in decisions]
        questions = tuple(
            {"topic": item, "question": f"Specify {item.replace('_', ' ')} behavior."}
            for item in missing[:max_questions]
        )
        return ClarificationResult(
            resolved_decisions=tuple(
                {"topic": key, "decision": value} for key, value in sorted(decisions.items())
            ),
            open_questions=questions,
            assumptions=(),
            risks=("unresolved critical requirements",) if questions else (),
            complete=not questions,
        )


class ImplementationPlanRegistry:
    def __init__(self, store: GovernanceRecordStore, rfcs: RFCRegistry, events: Any) -> None:
        self.store = store
        self.rfcs = rfcs
        self.events = events

    def create(self, plan: ImplementationPlan) -> ImplementationPlan:
        rfc = self.rfcs.get(plan.project_id, plan.rfc_id)
        if rfc.status not in {RFCStatus.APPROVED, RFCStatus.IMPLEMENTING}:
            raise ImplementationPlanInvalid("Implementation plan requires an approved RFC")
        if (plan.rfc_revision, plan.rfc_checksum) != (rfc.revision, rfc.checksum):
            raise ImplementationPlanInvalid("Implementation plan targets a stale RFC")
        if not plan.tasks or not plan.rollback_plan.strip():
            raise ImplementationPlanInvalid("Tasks and rollback plan are required")
        prepared = replace(plan, checksum="")
        prepared = replace(prepared, checksum=_checksum(asdict(prepared)))
        self.store.put(prepared.plan_id, asdict(prepared), create_only=True)
        self.events.emit(
            "implementation_plan.created",
            prepared.created_by,
            {
                "project_id": prepared.project_id,
                "rfc_id": prepared.rfc_id,
                "rfc_revision": prepared.rfc_revision,
                "plan_id": prepared.plan_id,
                "revision": prepared.revision,
                "checksum": prepared.checksum,
            },
        )
        return prepared

    def get(self, plan_id: str) -> ImplementationPlan:
        try:
            return _plan(self.store.get(plan_id))
        except Exception as exc:
            raise ImplementationPlanInvalid(f"Plan not found: {plan_id}") from exc

    def list(self, project_id: str | None = None) -> tuple[ImplementationPlan, ...]:
        filters = {"project_id": project_id} if project_id else {}
        return tuple(_plan(item) for item in self.store.list(filters))

    def validate(self, plan_id: str) -> ImplementationPlan:
        plan = self.get(plan_id)
        rfc = self.rfcs.get(plan.project_id, plan.rfc_id)
        if (plan.rfc_revision, plan.rfc_checksum) != (rfc.revision, rfc.checksum):
            return self._status(plan, ImplementationPlanStatus.STALE)
        if plan.status is ImplementationPlanStatus.DRAFT:
            return self._status(plan, ImplementationPlanStatus.VALIDATED)
        return plan

    def update_criteria(
        self, plan_id: str, criteria: tuple[AcceptanceCriterion, ...]
    ) -> ImplementationPlan:
        plan = self.get(plan_id)
        updated = replace(
            plan,
            acceptance_criteria=criteria,
            revision=plan.revision + 1,
            updated_at=now_iso(),
            checksum="",
        )
        updated = replace(updated, checksum=_checksum(asdict(updated)))
        self.store.put(plan_id, asdict(updated), expected_revision=plan.revision)
        return updated

    def _status(
        self, plan: ImplementationPlan, status: ImplementationPlanStatus
    ) -> ImplementationPlan:
        updated = replace(
            plan,
            status=status,
            revision=plan.revision + 1,
            updated_at=now_iso(),
            checksum="",
        )
        updated = replace(updated, checksum=_checksum(asdict(updated)))
        self.store.put(plan.plan_id, asdict(updated), expected_revision=plan.revision)
        return updated


class EvidenceRegistry:
    def __init__(
        self, store: GovernanceRecordStore, plans: ImplementationPlanRegistry, events: Any
    ):
        self.store = store
        self.plans = plans
        self.events = events

    def record(self, evidence: EvidenceRecord) -> EvidenceRecord:
        plan = self.plans.get(evidence.plan_id)
        if evidence.project_id != plan.project_id or evidence.rfc_id != plan.rfc_id:
            raise EvidenceInvalid("Evidence scope does not match its plan")
        if evidence.rfc_revision != plan.rfc_revision:
            raise EvidenceInvalid("Evidence targets a stale RFC revision")
        _safe_reference(evidence.artifact_reference)
        if not evidence.summary.strip() or not evidence.checksum:
            raise EvidenceInvalid("Evidence summary and checksum are required")
        self.store.put(evidence.evidence_id, asdict(evidence), create_only=True)
        self.events.emit(
            "evidence.recorded",
            evidence.produced_by,
            {
                "project_id": evidence.project_id,
                "rfc_id": evidence.rfc_id,
                "rfc_revision": evidence.rfc_revision,
                "plan_id": evidence.plan_id,
                "evidence_id": evidence.evidence_id,
                "evidence_type": evidence.evidence_type,
                "checksum": evidence.checksum,
                "correlation_id": evidence.correlation_id,
            },
        )
        return evidence

    def list(
        self, project_id: str, *, rfc_id: str | None = None, plan_id: str | None = None
    ) -> tuple[EvidenceRecord, ...]:
        filters: dict[str, Any] = {"project_id": project_id}
        if rfc_id:
            filters["rfc_id"] = rfc_id
        if plan_id:
            filters["plan_id"] = plan_id
        return tuple(EvidenceRecord(**item) for item in self.store.list(filters))


class ADRRegistry:
    def __init__(self, store: GovernanceRecordStore) -> None:
        self.store = store

    def add(self, record: ADRRecord) -> ADRRecord:
        prepared = replace(record, checksum="")
        prepared = replace(prepared, checksum=_checksum(asdict(prepared)))
        self.store.put(prepared.adr_id, asdict(prepared), create_only=True)
        return prepared

    def list(self, project_id: str) -> tuple[ADRRecord, ...]:
        return tuple(ADRRecord(**item) for item in self.store.list({"project_id": project_id}))


class ProjectContextRuntime:
    def __init__(
        self,
        projects: ProjectRegistry,
        rfcs: RFCRegistry,
        plans: ImplementationPlanRegistry,
        adrs: ADRRegistry,
    ) -> None:
        self.projects = projects
        self.rfcs = rfcs
        self.plans = plans
        self.adrs = adrs

    def read_project_context(self, project_id: str, *, budget: int = 8000) -> ProjectContext:
        project = self.projects.get(project_id)
        rfcs = [
            item
            for item in self.rfcs.list(project_id)
            if item.status in {RFCStatus.UNDER_REVIEW, RFCStatus.APPROVED, RFCStatus.IMPLEMENTING}
        ]
        plans = [
            item
            for item in self.plans.list(project_id)
            if item.status
            not in {
                ImplementationPlanStatus.COMPLETED,
                ImplementationPlanStatus.CANCELLED,
                ImplementationPlanStatus.FAILED,
            }
        ]
        rfc_views = tuple(
            {
                "rfc_id": item.rfc_id,
                "revision": item.revision,
                "checksum": item.checksum,
                "title": item.title,
                "status": item.status.value,
                "classification": item.classification,
            }
            for item in rfcs
        )
        plan_views = tuple(
            {
                "plan_id": item.plan_id,
                "rfc_id": item.rfc_id,
                "rfc_revision": item.rfc_revision,
                "revision": item.revision,
                "checksum": item.checksum,
                "status": item.status.value,
            }
            for item in plans
        )
        adr_views = tuple(
            {
                "adr_id": item.adr_id,
                "title": item.title,
                "status": item.status,
                "revision": item.revision,
                "checksum": item.checksum,
            }
            for item in self.adrs.list(project_id)
        )
        gates = tuple(asdict(gate) for item in rfcs for gate in item.required_quality_gates)
        estimate = len(json.dumps((rfc_views, plan_views, adr_views, gates))) // 4
        truncated = estimate > budget
        if truncated:
            rfc_views = rfc_views[: max(1, budget // 500)]
            plan_views = plan_views[: max(1, budget // 500)]
            adr_views = adr_views[: max(1, budget // 500)]
        return ProjectContext(
            project_id,
            project.revision,
            rfc_views,
            adr_views,
            plan_views,
            tuple(project.rfc_policy.get("constraints", ())),
            tuple(dict.fromkeys(value for item in rfcs for value in item.invariants)),
            tuple(project.skill_scope.get("allowed_skills", ())),
            gates,
            (
                {
                    "source": "project_manifest",
                    "revision": project.revision,
                    "checksum": project.checksum,
                },
            ),
            project.classification,
            truncated,
        )


class RFCGate:
    def __init__(
        self,
        policy: ProjectGovernancePolicy,
        projects: ProjectRegistry,
        rfcs: RFCRegistry,
        plans: ImplementationPlanRegistry,
        validation: RFCValidationRuntime,
        events: Any,
    ) -> None:
        self.policy = policy
        self.projects = projects
        self.rfcs = rfcs
        self.plans = plans
        self.validation = validation
        self.events = events

    def evaluate_gate(self, request: RFCGateRequest) -> RFCGateResult:
        self.projects.get(request.project_id)
        classification = self.policy.classify(request)
        if classification.rfc_disposition == "rfc_not_required" and not request.rfc_id:
            return self._result(request, "allowed_without_rfc", True, classification.reasons)
        if not request.rfc_id:
            return self._result(
                request, "blocked_missing_rfc", False, ("RFC is required for this change",)
            )
        try:
            rfc = self.rfcs.get(request.project_id, request.rfc_id)
        except RFCNotFound:
            return self._result(request, "blocked_missing_rfc", False, ("RFC not found",))
        if rfc.status not in {RFCStatus.APPROVED, RFCStatus.IMPLEMENTING}:
            return self._result(
                request,
                "blocked_unapproved_rfc",
                False,
                (f"RFC status is {rfc.status.value}",),
                rfc,
            )
        if request.rfc_revision is not None and (
            request.rfc_revision != rfc.revision or request.rfc_checksum != rfc.checksum
        ):
            return self._result(
                request, "blocked_stale_rfc", False, ("RFC revision or checksum is stale",), rfc
            )
        if not set(request.domains).issubset(set(rfc.affected_domains)) or not set(
            request.contracts
        ).issubset(set(rfc.affected_contracts)):
            return self._result(
                request, "blocked_scope_mismatch", False, ("Requested scope exceeds RFC",), rfc
            )
        conflicts = self.rfcs.conflicts(rfc)
        if conflicts:
            return self._result(
                request,
                "blocked_contract_conflict",
                False,
                (f"Conflicting RFCs: {', '.join(conflicts)}",),
                rfc,
            )
        validation = self.validation.validate(request.project_id, request.rfc_id)
        if validation.missing_acceptance_criteria:
            return self._result(
                request,
                "blocked_missing_acceptance_criteria",
                False,
                ("Required acceptance criteria are missing",),
                rfc,
            )
        if validation.missing_evals:
            return self._result(
                request,
                "blocked_missing_evals",
                False,
                ("Required eval references are missing",),
                rfc,
            )
        if request.plan_reference:
            try:
                plan = self.plans.get(str(request.plan_reference["plan_id"]))
            except Exception:
                return self._result(
                    request, "blocked_stale_rfc", False, ("Plan is unavailable",), rfc
                )
            if plan.status is ImplementationPlanStatus.STALE or (
                plan.rfc_revision,
                plan.rfc_checksum,
            ) != (rfc.revision, rfc.checksum):
                return self._result(
                    request, "blocked_stale_rfc", False, ("Implementation plan is stale",), rfc
                )
            if plan.status not in {
                ImplementationPlanStatus.VALIDATED,
                ImplementationPlanStatus.APPROVED,
                ImplementationPlanStatus.EXECUTING,
            }:
                return self._result(
                    request,
                    "blocked_stale_rfc",
                    False,
                    (f"Implementation plan status is {plan.status.value}",),
                    rfc,
                )
            if (
                request.plan_reference.get("revision") != plan.revision
                or request.plan_reference.get("checksum") != plan.checksum
            ):
                return self._result(
                    request,
                    "blocked_stale_rfc",
                    False,
                    ("Implementation plan revision or checksum is stale",),
                    rfc,
                )
        return self._result(request, "allowed", True, classification.reasons, rfc)

    def _result(
        self,
        request: RFCGateRequest,
        disposition: str,
        allowed: bool,
        reasons: tuple[str, ...],
        rfc: RFCManifest | None = None,
        *,
        approval_required: bool = False,
    ) -> RFCGateResult:
        result = RFCGateResult(
            disposition,
            allowed,
            reasons,
            approval_required,
            rfc.rfc_id if rfc else None,
            rfc.revision if rfc else None,
            rfc.checksum if rfc else None,
        )
        self.events.emit(
            "rfc.gate_allowed" if allowed else "rfc.gate_blocked",
            request.requester,
            {
                "project_id": request.project_id,
                "rfc_id": result.rfc_id,
                "revision": result.rfc_revision,
                "checksum": result.rfc_checksum,
                "reason": disposition,
                "correlation_id": request.correlation_id,
            },
        )
        return result


class ProjectGovernanceRuntime:
    def __init__(
        self,
        *,
        events: Any,
        documents: ProjectDocumentPort,
        stores: Mapping[str, GovernanceRecordStore],
        quality_gates: QualityGateExecutionPort | None = None,
    ) -> None:
        self.events = events
        self.quality_gates = quality_gates
        self.policy = ProjectGovernancePolicy()
        self.projects = ProjectRegistry(stores["projects"], documents, events)
        self.versions = RFCVersionStore(stores["versions"])
        self.rfcs = RFCRegistry(
            stores["rfcs"],
            self.versions,
            documents,
            self.projects,
            stores["plans"],
            events,
        )
        self.plans = ImplementationPlanRegistry(stores["plans"], self.rfcs, events)
        self.validation = RFCValidationRuntime(self.rfcs)
        self.reviews = RFCReviewRuntime(
            self.rfcs, self.validation, stores["reviews"], self.policy, events
        )
        self.clarification = RequirementClarificationRuntime()
        self.evidence = EvidenceRegistry(stores["evidence"], self.plans, events)
        self.adrs = ADRRegistry(stores["adrs"])
        self.context = ProjectContextRuntime(self.projects, self.rfcs, self.plans, self.adrs)
        self.gate = RFCGate(
            self.policy, self.projects, self.rfcs, self.plans, self.validation, events
        )

    def read_project_context(self, project_id: str, *, budget: int = 8000) -> ProjectContext:
        return self.context.read_project_context(project_id, budget=budget)

    def evaluate_gate(self, request: RFCGateRequest) -> RFCGateResult:
        return self.gate.evaluate_gate(request)

    def validate_binding(self, binding: RFCImplementationBinding) -> RFCGateResult:
        return self.evaluate_gate(
            RFCGateRequest(
                project_id=binding.project_id,
                requested_change="execute implementation plan",
                domains=(),
                contracts=(),
                rfc_id=binding.rfc_id,
                rfc_revision=binding.rfc_revision,
                rfc_checksum=binding.rfc_checksum,
                plan_reference={
                    "plan_id": binding.plan_id,
                    "revision": binding.plan_revision,
                    "checksum": binding.plan_checksum,
                },
                impact={"behavioral": True},
            )
        )

    def record_evidence(self, evidence: EvidenceRecord) -> EvidenceRecord:
        return self.evidence.record(evidence)

    def preview_quality_gate(
        self, descriptor: QualityGateDescriptor, arguments: dict[str, Any], *, actor_id: str
    ) -> Any:
        if self.quality_gates is None:
            raise ImplementationPlanInvalid("Quality gate execution boundary is unavailable")
        return self.quality_gates.preview(descriptor.tool_reference, arguments, actor_id=actor_id)

    def execute_quality_gate(
        self,
        descriptor: QualityGateDescriptor,
        arguments: dict[str, Any],
        *,
        actor_id: str,
        approval_id: str | None = None,
    ) -> Any:
        if self.quality_gates is None:
            raise ImplementationPlanInvalid("Quality gate execution boundary is unavailable")
        return self.quality_gates.execute(
            descriptor.tool_reference,
            arguments,
            actor_id=actor_id,
            approval_id=approval_id,
        )

    def update_criterion(
        self,
        plan_id: str,
        criterion_id: str,
        status: CriterionStatus,
        *,
        actor_id: str,
        result_reference: str | None = None,
        waiver: dict[str, Any] | None = None,
    ) -> AcceptanceCriterion:
        plan = self.plans.get(plan_id)
        current = next(
            (item for item in plan.acceptance_criteria if item.criterion_id == criterion_id),
            None,
        )
        if current is None:
            raise EvidenceInvalid(f"Acceptance criterion not found: {criterion_id}")
        if status is CriterionStatus.WAIVED:
            required = {"reason", "actor", "policy", "approval"}
            if not waiver or not required <= waiver.keys():
                raise EvidenceInvalid("Waiver requires reason, actor, policy and approval")
        updated = replace(current, status=status, result_reference=result_reference, waiver=waiver)
        criteria = tuple(
            updated if item.criterion_id == criterion_id else item
            for item in plan.acceptance_criteria
        )
        self.plans.update_criteria(plan_id, criteria)
        self.events.emit(
            "acceptance_criterion.updated",
            actor_id,
            {
                "project_id": plan.project_id,
                "rfc_id": plan.rfc_id,
                "plan_id": plan.plan_id,
                "criterion_id": criterion_id,
                "status": status.value,
            },
        )
        return updated

    def start_implementation(self, project_id: str, rfc_id: str, *, actor_id: str) -> RFCManifest:
        return self.rfcs.transition(project_id, rfc_id, RFCStatus.IMPLEMENTING, actor_id=actor_id)

    def mark_implemented(self, project_id: str, rfc_id: str, *, actor_id: str) -> RFCManifest:
        rfc = self.rfcs.get(project_id, rfc_id)
        plans = [item for item in self.plans.list(project_id) if item.rfc_id == rfc_id]
        current = [item for item in plans if item.rfc_revision == rfc.revision]
        if not current:
            raise ImplementationPlanInvalid("No current implementation plan")
        criteria = [criterion for plan in current for criterion in plan.acceptance_criteria]
        if not criteria or any(
            item.required and item.status not in {CriterionStatus.SATISFIED, CriterionStatus.WAIVED}
            for item in criteria
        ):
            raise EvidenceInvalid("Required acceptance criteria are not satisfied")
        evidence = self.evidence.list(project_id, rfc_id=rfc_id)
        if not evidence:
            raise EvidenceInvalid("RFC cannot be implemented without evidence")
        return self.rfcs.transition(
            project_id,
            rfc_id,
            RFCStatus.IMPLEMENTED,
            actor_id=actor_id,
            extra={"implemented_at": now_iso()},
        )

    def health_snapshot(self) -> dict[str, Any]:
        projects = self.projects.list()
        rfcs = self.rfcs.list()
        conflicts = sum(len(self.rfcs.conflicts(item)) for item in rfcs)
        stale = sum(item.status is ImplementationPlanStatus.STALE for item in self.plans.list())
        missing = sum(
            item.status is RFCStatus.UNDER_REVIEW
            and not self.reviews.list(item.project_id, item.rfc_id)
            for item in rfcs
        )
        return {
            "registry": "available",
            "projects": len(projects),
            "invalid_manifests": 0,
            "rfc_conflicts": conflicts,
            "stale_plans": stale,
            "missing_approvals": missing,
            "evidence_store": "available",
            "recovery": "storage_primitives",
            "last_validation": self.validation.last_validation,
            "unresolved_critical_questions": 0,
        }


def _rfc_key(project_id: str, rfc_id: str) -> str:
    return f"{project_id}--{rfc_id}"


def _rfc_checksum(manifest: RFCManifest, markdown: str) -> str:
    payload = asdict(replace(manifest, checksum=""))
    for field in ("status", "approved_at", "implemented_at", "updated_at"):
        payload.pop(field, None)
    return _checksum({"manifest": payload, "markdown": markdown.replace("\r\n", "\n")})


def _project(raw: dict[str, Any]) -> ProjectManifest:
    return ProjectManifest(
        **{
            **raw,
            "status": ProjectStatus(raw["status"]),
            "allowed_provider_profiles": tuple(raw.get("allowed_provider_profiles", ())),
        }
    )


def _criterion(raw: dict[str, Any]) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        **{
            **raw,
            "status": CriterionStatus(raw.get("status", "pending")),
            "evidence_types": tuple(raw.get("evidence_types", ())),
            "linked_requirements": tuple(raw.get("linked_requirements", ())),
            "linked_invariants": tuple(raw.get("linked_invariants", ())),
        }
    )


def _gate_descriptor(raw: dict[str, Any]) -> QualityGateDescriptor:
    return QualityGateDescriptor(
        **{**raw, "platform_constraints": tuple(raw.get("platform_constraints", ()))}
    )


def _eval(raw: dict[str, Any]) -> EvalReference:
    return EvalReference(**raw)


def _rfc(raw: dict[str, Any]) -> RFCManifest:
    return RFCManifest(
        **{
            **raw,
            "status": RFCStatus(raw["status"]),
            "change_classification": ChangeClass(raw["change_classification"]),
            "authors": tuple(raw.get("authors", ())),
            "reviewers": tuple(raw.get("reviewers", ())),
            "affected_domains": tuple(raw.get("affected_domains", ())),
            "affected_contracts": tuple(raw.get("affected_contracts", ())),
            "supersedes": tuple(raw.get("supersedes", ())),
            "affected_references": tuple(raw.get("affected_references", ())),
            "required_approvals": tuple(raw.get("required_approvals", ())),
            "required_evals": tuple(_eval(item) for item in raw.get("required_evals", ())),
            "required_quality_gates": tuple(
                _gate_descriptor(item) for item in raw.get("required_quality_gates", ())
            ),
            "implementation_plan_ids": tuple(raw.get("implementation_plan_ids", ())),
            "acceptance_criteria": tuple(
                _criterion(item) for item in raw.get("acceptance_criteria", ())
            ),
            "invariants": tuple(raw.get("invariants", ())),
            "out_of_scope": tuple(raw.get("out_of_scope", ())),
            "allowed_provider_profiles": tuple(raw.get("allowed_provider_profiles", ())),
        }
    )


def _review(raw: dict[str, Any]) -> RFCReview:
    return RFCReview(
        **{
            **raw,
            "role": ReviewRole(raw["role"]),
            "decision": ReviewDecision(raw["decision"]),
        }
    )


def _plan(raw: dict[str, Any]) -> ImplementationPlan:
    return ImplementationPlan(
        **{
            **raw,
            "status": ImplementationPlanStatus(raw["status"]),
            "scope": tuple(raw.get("scope", ())),
            "allowed_domains": tuple(raw.get("allowed_domains", ())),
            "allowed_references": tuple(raw.get("allowed_references", ())),
            "forbidden_changes": tuple(raw.get("forbidden_changes", ())),
            "tasks": tuple(raw.get("tasks", ())),
            "dependencies": {
                key: tuple(value) for key, value in raw.get("dependencies", {}).items()
            },
            "required_skills": tuple(raw.get("required_skills", ())),
            "required_tools": tuple(raw.get("required_tools", ())),
            "quality_gates": tuple(_gate_descriptor(item) for item in raw.get("quality_gates", ())),
            "evals": tuple(_eval(item) for item in raw.get("evals", ())),
            "acceptance_criteria": tuple(
                _criterion(item) for item in raw.get("acceptance_criteria", ())
            ),
        }
    )
