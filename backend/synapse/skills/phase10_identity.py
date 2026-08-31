from __future__ import annotations

import hashlib
from datetime import datetime

from synapse.skills.phase2_models import PublishedSkillVersionId
from synapse.skills.phase2_serialization import canonical_json_bytes
from synapse.skills.phase10_refs import (
    ExternalAuthorityRef,
    ExternalBinderRef,
    ExternalBindingOccurrenceRef,
    ExternalBindingRef,
    GovernanceDecisionKindRef,
    GovernanceDecisionRef,
    GovernancePolicyRef,
    IntelligenceAnalysisRef,
    IntelligenceFactKindRef,
    IntelligenceFactRef,
    IntelligenceProfileRef,
)


def _governance_binding_ref(
    identity: PublishedSkillVersionId,
    authority_ref: ExternalAuthorityRef,
    decision_ref: GovernanceDecisionRef,
    decision_kind_ref: GovernanceDecisionKindRef,
    policy_ref: GovernancePolicyRef,
) -> ExternalBindingRef:
    projection = (
        "governance",
        identity.to_canonical_text(),
        str(authority_ref),
        str(decision_ref),
        str(decision_kind_ref),
        str(policy_ref),
    )
    return ExternalBindingRef(f"governance-binding:{_digest(projection)}")


def _intelligence_binding_ref(
    identity: PublishedSkillVersionId,
    authority_ref: ExternalAuthorityRef,
    fact_ref: IntelligenceFactRef,
    fact_kind_ref: IntelligenceFactKindRef,
    profile_ref: IntelligenceProfileRef,
    analysis_ref: IntelligenceAnalysisRef | None,
) -> ExternalBindingRef:
    projection = (
        "intelligence",
        identity.to_canonical_text(),
        str(authority_ref),
        str(fact_ref),
        str(fact_kind_ref),
        str(profile_ref),
        str(analysis_ref) if analysis_ref is not None else "",
    )
    return ExternalBindingRef(f"intelligence-binding:{_digest(projection)}")


def _binding_occurrence_ref(
    family: str,
    binding_ref: ExternalBindingRef,
    binder_ref: ExternalBinderRef,
    bound_at: datetime,
) -> ExternalBindingOccurrenceRef:
    projection = (
        str(binding_ref),
        str(binder_ref),
        bound_at.isoformat(),
    )
    return ExternalBindingOccurrenceRef(f"{family}-binding-occurrence:{_digest(projection)}")


def _digest(projection: tuple[object, ...]) -> str:
    return hashlib.sha256(canonical_json_bytes(projection)).hexdigest()
