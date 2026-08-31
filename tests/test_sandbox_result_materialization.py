from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from synapse.sandbox import (
    InvalidResultMaterialization,
    OpaqueReference,
    SandboxArtifactFingerprint,
    SandboxCancellationDecisionService,
    SandboxCancellationService,
    SandboxDeadlineService,
    SandboxEvidenceCategory,
    SandboxEvidenceDisclosureLevel,
    SandboxEvidenceItem,
    SandboxEvidencePolicy,
    SandboxEvidenceRedactionLevel,
    SandboxEvidenceRetention,
    SandboxEvidenceRetentionDisposition,
    SandboxExecutionResultOutcome,
    SandboxExitClassification,
    SandboxFunctionalResult,
    SandboxPolicyVersion,
    SandboxResultMaterializationRequest,
    SandboxResultMaterializationService,
    SandboxResultMaterializationStatus,
    SandboxRuntimeEventKind,
    SandboxRuntimeSupervisionService,
)
from test_sandbox_admission_policy import policy as admission_policy
from test_sandbox_cancellation import (
    cancellation_request,
    completed_events,
    deadline_set,
)
from test_sandbox_cancellation import (
    policy as cancellation_policy,
)
from test_sandbox_capability_grants import pipeline
from test_sandbox_runtime_supervision import (
    event,
    observation,
    proof,
    running_events,
    start_request,
)

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
REQUIRED = (
    SandboxEvidenceCategory.ADMISSION,
    SandboxEvidenceCategory.GRANTS,
    SandboxEvidenceCategory.MATERIALIZATION,
    SandboxEvidenceCategory.PLAN,
    SandboxEvidenceCategory.RUNTIME_LIFECYCLE,
    SandboxEvidenceCategory.TERMINATION,
)


def ref(value: str) -> OpaqueReference:
    return OpaqueReference(value)


def policy(**changes: object) -> SandboxEvidencePolicy:
    values: dict[str, object] = {
        "version": SandboxPolicyVersion("evidence-policy:v1"),
        "required_categories": REQUIRED,
        "max_items": 32,
        "max_summary_bytes": 128,
        "max_total_estimated_bytes": 4096,
        "max_diagnostics": 32,
        "max_stdio_references": 2,
        "allowed_disclosures": (
            SandboxEvidenceDisclosureLevel.AUDIT,
            SandboxEvidenceDisclosureLevel.RESTRICTED,
        ),
        "retention": SandboxEvidenceRetention(
            30, SandboxEvidenceRetentionDisposition.EXPIRE
        ),
    }
    values.update(changes)
    return SandboxEvidencePolicy.create(**values)  # type: ignore[arg-type]


def item(category: SandboxEvidenceCategory) -> SandboxEvidenceItem:
    return SandboxEvidenceItem(
        category,
        ref(f"evidence:{category.value}"),
        SandboxArtifactFingerprint.from_content((category, "bounded-summary")),
        f"bounded {category.value} summary",
        64,
        SandboxEvidenceRedactionLevel.REDACTED,
        SandboxEvidenceDisclosureLevel.AUDIT,
    )


def items(*, reverse: bool = False) -> tuple[SandboxEvidenceItem, ...]:
    selected = tuple(item(category) for category in REQUIRED)
    return tuple(reversed(selected)) if reverse else selected


def completed_context(*, occurred_at: datetime = NOW):
    start = start_request(occurred_at=occurred_at)
    current_attempt = SandboxRuntimeSupervisionService.create_attempt(start)
    termination = proof(current_attempt, occurred_at=occurred_at)
    supervision = SandboxRuntimeSupervisionService.evaluate(
        start,
        (
            *running_events(current_attempt),
            event(
                4,
                SandboxRuntimeEventKind.RUNTIME_EXITED,
                current_attempt,
                observation=observation(
                    alive=False,
                    exit_classification=SandboxExitClassification.SUCCEEDED,
                ),
                termination_proof=termination,
                occurred_at=occurred_at,
            ),
        ),
    )
    admission = pipeline()[3]
    assert admission.decision_id == start.plan.decision_id
    return start, current_attempt, supervision, termination, admission


def request(
    *,
    occurred_at: datetime = NOW,
    evidence_items: tuple[SandboxEvidenceItem, ...] | None = None,
    evidence_policy: SandboxEvidencePolicy | None = None,
) -> SandboxResultMaterializationRequest:
    start, current_attempt, supervision, termination, admission = completed_context(
        occurred_at=occurred_at
    )
    return SandboxResultMaterializationRequest(
        admission,
        start.plan,
        start.capabilities,
        start.filesystem,
        start.network,
        start.process,
        start.resources,
        start.secrets,
        start.materialization_plan,
        start.materialization,
        current_attempt,
        supervision,
        None,
        termination,
        evidence_policy or policy(),
        items() if evidence_items is None else evidence_items,
        (ref("stdio:stdout"), ref("stdio:stderr")),
        occurred_at,
    )


def test_materializes_clean_success_only_from_compatible_supervision() -> None:
    outcome = SandboxResultMaterializationService.materialize(request())
    assert outcome.status is SandboxResultMaterializationStatus.MATERIALIZED
    assert outcome.result is not None
    assert outcome.bundle is not None
    assert outcome.result.outcome is SandboxExecutionResultOutcome.SUCCEEDED
    assert outcome.result.functional_result is SandboxFunctionalResult.SUCCEEDED
    assert outcome.result.termination_proof_ref is not None
    assert not outcome.result.cleanup_required


def test_evidence_order_and_occurrence_do_not_change_semantic_identity() -> None:
    first = SandboxResultMaterializationService.materialize(request())
    second_request = request(
        occurred_at=NOW + timedelta(minutes=1), evidence_items=items(reverse=True)
    )
    second = SandboxResultMaterializationService.materialize(second_request)
    assert first.result is not None and second.result is not None
    assert first.bundle is not None and second.bundle is not None
    assert first.result.result_fingerprint == second.result.result_fingerprint
    assert first.bundle.evidence_fingerprint == second.bundle.evidence_fingerprint
    assert first.bundle.items == tuple(
        sorted(first.bundle.items, key=lambda item: (item.category.value, item.reference.value))
    )


def test_unverified_termination_never_produces_clean_result() -> None:
    selected = request()
    start = start_request()
    current_attempt = SandboxRuntimeSupervisionService.create_attempt(start)
    supervision = SandboxRuntimeSupervisionService.evaluate(
        start,
        (*running_events(current_attempt), event(4, SandboxRuntimeEventKind.RUNTIME_EXITED, current_attempt)),
    )
    outcome = SandboxResultMaterializationService.materialize(
        replace(
            selected,
            attempt=current_attempt,
            supervision=supervision,
            termination_proof=None,
            evidence_items=items()
            + (
                item(SandboxEvidenceCategory.CLEANUP_REQUIREMENT),
                item(SandboxEvidenceCategory.DIAGNOSTICS),
            ),
        )
    )
    assert outcome.result is not None
    assert outcome.result.outcome is SandboxExecutionResultOutcome.TERMINATION_UNVERIFIED
    assert outcome.result.functional_result is SandboxFunctionalResult.NOT_AVAILABLE
    assert outcome.result.cleanup_required


def test_timeout_remains_distinct_from_cancellation_and_failure() -> None:
    selected = request()
    start = start_request()
    current_attempt = SandboxRuntimeSupervisionService.create_attempt(start)
    supervision = SandboxRuntimeSupervisionService.evaluate(
        start,
        (
            *running_events(current_attempt),
            event(
                4,
                SandboxRuntimeEventKind.RUNTIME_OBSERVED,
                current_attempt,
                observation=observation(
                    alive=False,
                    exit_classification=SandboxExitClassification.TIMED_OUT,
                ),
            ),
        ),
    )
    outcome = SandboxResultMaterializationService.materialize(
        replace(
            selected,
            attempt=current_attempt,
            supervision=supervision,
            termination_proof=None,
            evidence_items=items()
            + (
                item(SandboxEvidenceCategory.CLEANUP_REQUIREMENT),
                item(SandboxEvidenceCategory.DIAGNOSTICS),
            ),
        )
    )
    assert outcome.result is not None
    assert outcome.result.outcome is SandboxExecutionResultOutcome.TIMED_OUT
    assert outcome.result.cleanup_required


def test_explicit_completed_cancellation_remains_cancelled() -> None:
    selected = request()
    current_attempt = selected.attempt
    selected_policy = cancellation_policy()
    deadlines = deadline_set(current_attempt, selected_policy)
    cancellation = SandboxCancellationDecisionService.decide(
        current_attempt,
        selected_policy,
        deadlines,
        cancellation_request(current_attempt, selected_policy, deadlines),
        SandboxDeadlineService.evaluate(deadlines, evaluated_at=NOW),
        occurred_at=NOW,
    )
    cancellation_result = SandboxCancellationService.reduce(
        cancellation,
        selected_policy,
        completed_events(current_attempt, cancellation),
        occurred_at=NOW,
    )
    outcome = SandboxResultMaterializationService.materialize(
        replace(
            selected,
            cancellation=cancellation_result,
            evidence_items=items()
            + (
                item(SandboxEvidenceCategory.CANCELLATION_TIMEOUT),
                item(SandboxEvidenceCategory.DIAGNOSTICS),
            ),
        )
    )
    assert outcome.result is not None
    assert outcome.result.outcome is SandboxExecutionResultOutcome.CANCELLED
    assert outcome.result.functional_result is SandboxFunctionalResult.NOT_AVAILABLE


def test_exact_binding_mismatch_fails_closed() -> None:
    selected = request()
    changed_plan = pipeline(
        admission_policy=admission_policy(version="admission-policy:v2")
    )[4]
    outcome = SandboxResultMaterializationService.materialize(
        replace(selected, plan=changed_plan)
    )
    assert outcome.status is SandboxResultMaterializationStatus.MISMATCH
    assert outcome.bundle is None
    assert "binding.admission_plan_mismatch" in outcome.diagnostics


def test_missing_evidence_is_explicit_and_never_yields_bundle() -> None:
    selected = request(evidence_items=items()[1:])
    outcome = SandboxResultMaterializationService.materialize(selected)
    assert outcome.status is SandboxResultMaterializationStatus.INCOMPLETE
    assert outcome.bundle is None


def test_unavailable_evidence_is_distinct_from_partial_evidence() -> None:
    outcome = SandboxResultMaterializationService.materialize(request(evidence_items=()))
    assert outcome.status is SandboxResultMaterializationStatus.UNAVAILABLE
    assert outcome.bundle is None


@pytest.mark.parametrize(
    "summary",
    ("token=opaque-is-not-a-value", "C:/Users/person/result", "/home/person/result"),
)
def test_sensitive_values_and_personal_paths_are_rejected_without_echo(summary: str) -> None:
    with pytest.raises(InvalidResultMaterialization) as captured:
        replace(items()[0], summary=summary)
    assert summary not in repr(captured.value)


def test_bounded_limits_and_duplicate_references_fail_explicitly() -> None:
    selected = request(evidence_policy=policy(max_items=5))
    limited = SandboxResultMaterializationService.materialize(selected)
    assert limited.status is SandboxResultMaterializationStatus.LIMIT_EXCEEDED
    duplicate = replace(selected, evidence_policy=policy(), evidence_items=items() + (items()[0],))
    duplicated = SandboxResultMaterializationService.materialize(duplicate)
    assert duplicated.status is SandboxResultMaterializationStatus.LIMIT_EXCEEDED
    assert duplicated.diagnostics == ("evidence.reference_duplicate",)


def test_stdio_references_are_bounded_opaque_and_semantic() -> None:
    first = SandboxResultMaterializationService.materialize(request())
    changed = SandboxResultMaterializationService.materialize(
        replace(request(), stdout_stderr_refs=(ref("stdio:stdout-v2"),))
    )
    assert first.result is not None and changed.result is not None
    assert first.result.result_fingerprint != changed.result.result_fingerprint
    assert all("/" not in item.value for item in first.result.stdout_stderr_refs)


def test_service_has_no_operational_api() -> None:
    assert not hasattr(SandboxResultMaterializationService, "persist")
    assert not hasattr(SandboxResultMaterializationService, "cleanup")
    assert not hasattr(SandboxResultMaterializationService, "rollback")
