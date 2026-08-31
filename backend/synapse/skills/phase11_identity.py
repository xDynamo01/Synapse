from __future__ import annotations

import hashlib
from datetime import datetime

from synapse.skills.phase2_serialization import canonical_json_bytes
from synapse.skills.phase10_refs import ExternalBinderRef
from synapse.skills.phase11_models import (
    BindSkillPrivateEvalResultRequest,
    SkillPrivateEvalBindingRecord,
)
from synapse.skills.phase11_refs import (
    PrivateEvalBindingOccurrenceRef,
    PrivateEvalBindingRef,
)


def _private_eval_binding_ref(
    value: BindSkillPrivateEvalResultRequest | SkillPrivateEvalBindingRecord,
) -> PrivateEvalBindingRef:
    projection = (
        "private-evals",
        value.identity.to_canonical_text(),
        value.granularity.value,
        str(value.run_ref),
        str(value.result_ref),
        str(value.verdict_ref) if value.verdict_ref is not None else "",
        str(value.suite_ref),
        str(value.case_ref) if value.case_ref is not None else "",
        str(value.profile_ref),
        str(value.baseline_ref) if value.baseline_ref is not None else "",
        str(value.comparison_ref) if value.comparison_ref is not None else "",
        str(value.regression_ref) if value.regression_ref is not None else "",
        tuple(str(reference) for reference in value.evidence_refs),
    )
    return PrivateEvalBindingRef(f"private-eval-binding:{_digest(projection)}")


def _private_eval_occurrence_ref(
    binding_ref: PrivateEvalBindingRef,
    binder_ref: ExternalBinderRef,
    bound_at: datetime,
) -> PrivateEvalBindingOccurrenceRef:
    projection = (
        str(binding_ref),
        str(binder_ref),
        bound_at.isoformat(),
    )
    return PrivateEvalBindingOccurrenceRef(
        f"private-eval-binding-occurrence:{_digest(projection)}"
    )


def _digest(projection: tuple[object, ...]) -> str:
    return hashlib.sha256(canonical_json_bytes(projection)).hexdigest()
