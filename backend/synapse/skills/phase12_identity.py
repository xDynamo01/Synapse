from __future__ import annotations

import hashlib

from synapse.skills.phase2_serialization import canonical_json_bytes
from synapse.skills.phase12_models import SkillExecutionHandoffDraft
from synapse.skills.phase12_refs import SkillExecutionHandoffId


def _handoff_id(draft: SkillExecutionHandoffDraft) -> SkillExecutionHandoffId:
    """Hash semantic inputs only; readiness, diagnostics and limits are excluded."""

    security = draft.security_declaration
    requirements = draft.requirements
    resolution = draft.resolution
    projection = (
        draft.format_version.value,
        draft.subject.to_canonical_text(),
        str(draft.installation_id),
        str(draft.activation_id) if draft.activation_id else None,
        (
            requirements.require_active_subject,
            requirements.require_complete_dependency_resolution,
            requirements.require_resolved_dependency_registrations,
            requirements.allow_optional_dependency_omissions,
            requirements.require_declared_execution_profile,
            requirements.bindings.require_governance,
            requirements.bindings.require_intelligence,
            requirements.bindings.require_private_evals,
            requirements.bindings.require_complete_histories,
        ),
        (
            draft.installation.selected_record_known,
            draft.installation.current_registration,
            draft.installation.history_complete,
            draft.installation.terminated_registration,
            draft.installation.corrupted_registration_observed,
        ),
        (
            draft.lifecycle.history_complete,
            draft.lifecycle.active,
            draft.lifecycle.revoked,
            draft.lifecycle.deprecated,
            draft.lifecycle.superseded,
            (
                str(draft.lifecycle.active_installation_id)
                if draft.lifecycle.active_installation_id
                else None
            ),
        ),
        (
            str(resolution.profile_ref),
            str(resolution.policy_version),
            resolution.status.value,
            resolution.complete,
            resolution.required_resolved,
            resolution.has_optional_omissions,
            resolution.has_degraded_selections,
            tuple(item.value for item in resolution.conflict_kinds),
            resolution.has_graph_cycles,
        ),
        tuple(
            (
                item.selected.to_canonical_text(),
                item.requirement_ids,
                str(item.policy_version),
                item.lifecycle_status.value,
                item.compatibility_status.value,
                item.degraded,
            )
            for item in draft.dependencies
        ),
        tuple(
            (
                item.dependency.to_canonical_text(),
                item.status.value,
                str(item.installation_id) if item.installation_id else None,
                item.history_complete,
            )
            for item in draft.dependency_registrations
        ),
        tuple(
            (
                str(item.capability_id),
                str(item.version_constraint) if item.version_constraint else None,
            )
            for item in draft.capabilities
        ),
        (
            security.classification_ceiling.value,
            security.network_requirement.value,
            security.external_processing_requirement.value,
            security.filesystem_requirement.value,
            security.egress_requirement.value,
            (
                str(security.sandbox_profile_requirement)
                if security.sandbox_profile_requirement
                else None
            ),
            tuple(str(item) for item in security.secret_reference_requirements),
        ),
        tuple(
            (item.timeout_seconds, item.memory_mebibytes, item.cpu_millicores)
            for item in draft.resources
        ),
        tuple(
            (
                str(item.tool_id),
                str(item.version_constraint) if item.version_constraint else None,
            )
            for item in draft.required_tools
        ),
        draft.execution_runtime.value if draft.execution_runtime else None,
        str(draft.execution_profile) if draft.execution_profile else None,
        (
            draft.logical_entrypoint.logical_path.to_canonical_text()
            if draft.logical_entrypoint
            else None
        ),
        tuple(str(item) for item in draft.governance_occurrences),
        tuple(str(item) for item in draft.intelligence_occurrences),
        tuple(str(item) for item in draft.private_eval_occurrences),
        tuple(
            (item.family.value, item.supplied, item.complete)
            for item in draft.binding_histories
        ),
    )
    return SkillExecutionHandoffId(
        hashlib.sha256(canonical_json_bytes(projection)).hexdigest()
    )
