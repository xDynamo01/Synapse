from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

import synapse.skills as public_skills
from synapse.skills.phase2_errors import InvalidSkillContentReference
from synapse.skills.phase2_models import (
    CapabilityRequirement,
    PublishedSkillManifest,
    PublishedSkillVersionId,
    SkillContentFingerprint,
    SkillContentKind,
    SkillContentRef,
    SkillExecutionDeclaration,
    SkillExecutionRuntime,
    SkillId,
    SkillLogicalPath,
    SkillManifestFingerprint,
    SkillManifestFormatVersion,
    SkillProvenance,
    SkillPublicationScope,
    SkillRequirementId,
    SkillResourceRequirement,
    SkillSemanticReference,
    SkillVersion,
)
from synapse.skills.phase3_records import (
    PublishedSkillVersionRecord,
    SkillActivationRecord,
    SkillInstallationRecord,
    SkillLifecycleReason,
)
from synapse.skills.phase3_values import SkillStoreRecordId
from synapse.skills.phase6_models import (
    SkillActivationState,
    SkillLifecycleProjection,
    SkillSelectionState,
)
from synapse.skills.phase7_models import SkillInstallationProjection
from synapse.skills.phase8_models import (
    SkillCompatibilityStatus,
    SkillDependencyId,
    SkillDependencyLifecycleStatus,
)
from synapse.skills.phase9_models import (
    SkillDependencyCandidateDecision,
    SkillDependencyResolutionPlan,
    SkillDependencyResolutionStatus,
    SkillDependencySelectionCriterion,
    SkillDependencySelectionRationale,
    SkillDependencyTieBreak,
    SkillResolvedDependency,
)
from synapse.skills.phase9_policy import (
    SkillDependencyCompatibilityPolicy,
    SkillDependencyCompletenessPolicy,
    SkillDependencyDegradedLifecyclePolicy,
    SkillDependencyResolutionLimits,
    SkillDependencyResolutionPolicy,
    SkillDependencyResolutionPolicyVersion,
    SkillDependencyVersionMode,
    SkillDependencyVersionPreference,
    SkillOptionalDependencyPolicy,
)
from synapse.skills.phase10_identity import (
    _binding_occurrence_ref,
    _governance_binding_ref,
    _intelligence_binding_ref,
)
from synapse.skills.phase10_models import (
    SkillGovernanceBindingHistory,
    SkillGovernanceBindingRecord,
    SkillIntelligenceBindingHistory,
    SkillIntelligenceBindingRecord,
)
from synapse.skills.phase10_projection import (
    _governance_projection,
    _intelligence_projection,
)
from synapse.skills.phase10_refs import (
    ExternalAuthorityRef,
    ExternalBinderRef,
    ExternalBindingRef,
    GovernanceDecisionKindRef,
    GovernanceDecisionRef,
    GovernancePolicyRef,
    IntelligenceFactKindRef,
    IntelligenceFactRef,
    IntelligenceProfileRef,
)
from synapse.skills.phase11_identity import (
    _private_eval_binding_ref,
    _private_eval_occurrence_ref,
)
from synapse.skills.phase11_models import (
    SkillPrivateEvalBindingGranularity,
    SkillPrivateEvalBindingHistory,
    SkillPrivateEvalBindingRecord,
)
from synapse.skills.phase11_projection import _private_eval_projection
from synapse.skills.phase11_refs import (
    PrivateEvalBindingRef,
    PrivateEvalProfileRef,
    PrivateEvalResultRef,
    PrivateEvalRunRef,
    PrivateEvalSuiteRef,
)
from synapse.skills.phase12_errors import (
    InvalidSkillExecutionHandoffPolicy,
    SkillExecutionHandoffCorrespondenceError,
    SkillExecutionHandoffLimitExceeded,
)
from synapse.skills.phase12_handoff import SkillExecutionHandoffService
from synapse.skills.phase12_identity import _handoff_id
from synapse.skills.phase12_models import (
    BuildSkillExecutionHandoffRequest,
    SkillDependencyRegistrationStatus,
    SkillExecutionDependencyRegistrationFact,
    SkillExecutionHandoffDiagnostic,
    SkillExecutionHandoffDiagnosticCode,
    SkillExecutionReadinessStatus,
)
from synapse.skills.phase12_policy import (
    SkillExecutionBindingCompletenessPolicy,
    SkillExecutionHandoffBuildPolicy,
    SkillExecutionHandoffLimits,
)
from synapse.skills.phase12_refs import (
    SkillExecutionHandoffFormatVersion,
    SkillExecutionProfileRef,
)

NOW = datetime(2026, 7, 29, 15, 0, tzinfo=UTC)


def _publication(name: str = "handoff-skill") -> PublishedSkillVersionRecord:
    instructions_bytes = b"# Handoff"
    entrypoint_bytes = b"opaque"
    instructions = SkillContentRef(
        SkillLogicalPath("SKILL.md"),
        SkillContentFingerprint(hashlib.sha256(instructions_bytes).hexdigest()),
        SkillContentKind.INSTRUCTIONS,
        "text/markdown",
        len(instructions_bytes),
    )
    entrypoint = SkillContentRef(
        SkillLogicalPath("scripts/main.py"),
        SkillContentFingerprint(hashlib.sha256(entrypoint_bytes).hexdigest()),
        SkillContentKind.ENTRYPOINT,
        "text/x-python",
        len(entrypoint_bytes),
    )
    execution = SkillExecutionDeclaration(
        entrypoint,
        SkillExecutionRuntime.PYTHON,
        SkillSemanticReference("sandbox-profile:restricted"),
        SkillResourceRequirement(30, 128, 100),
        required_capabilities=(CapabilityRequirement(SkillRequirementId("text.generate")),),
    )
    manifest = PublishedSkillManifest(
        SkillManifestFormatVersion(1),
        SkillId(name),
        SkillVersion.parse("1.0.0"),
        "Handoff skill",
        "Structural execution handoff.",
        "A structural handoff test subject.",
        SkillProvenance(SkillSemanticReference("publisher:test")),
        (SkillPublicationScope.PROJECT,),
        (instructions, entrypoint),
        capabilities=(CapabilityRequirement(SkillRequirementId("image.inspect")),),
        execution=(execution,),
    )
    identity = PublishedSkillVersionId.from_manifest(
        manifest, SkillContentFingerprint(hashlib.sha256(instructions_bytes + entrypoint_bytes).hexdigest())
    )
    return PublishedSkillVersionRecord(
        identity,
        manifest,
        NOW,
        SkillSemanticReference("actor:publisher"),
        SkillSemanticReference("publication:test"),
    )


def _resolution(subject: PublishedSkillVersionId, *, complete: bool = True) -> SkillDependencyResolutionPlan:
    policy = SkillDependencyResolutionPolicy(
        SkillDependencyResolutionPolicyVersion(1),
        SkillDependencyVersionMode.SINGLE_VERSION,
        SkillDependencyVersionPreference.HIGHER_SEMVER,
        SkillDependencyCompatibilityPolicy.OBSERVED_ONLY,
        SkillDependencyDegradedLifecyclePolicy.DENY,
        SkillOptionalDependencyPolicy.RESOLVE_WHEN_POSSIBLE,
        SkillDependencyCompletenessPolicy.REQUIRE_COMPLETE_ANALYSIS,
        False,
        SkillDependencyResolutionLimits(10, 10, 10, 100, 10, 10, 20),
    )
    return SkillDependencyResolutionPlan(
        subject,
        SkillSemanticReference("resolution-profile:strict"),
        policy,
        (),
        (),
        (),
        (),
        (),
        SkillDependencyResolutionStatus.RESOLVED if complete else SkillDependencyResolutionStatus.INCOMPLETE,
        complete,
        complete,
        False,
        False,
    )


def _policy(*, max_capabilities: int = 10) -> SkillExecutionHandoffBuildPolicy:
    return SkillExecutionHandoffBuildPolicy(
        True,
        True,
        True,
        True,
        True,
        SkillExecutionBindingCompletenessPolicy(False, False, False, True),
        SkillExecutionHandoffLimits(10, max_capabilities, 10, 10, 10, 30),
    )


def _request() -> BuildSkillExecutionHandoffRequest:
    publication = _publication()
    identity = publication.identity
    installation_id = SkillStoreRecordId("installation:primary")
    installation = SkillInstallationRecord(
        installation_id,
        identity,
        identity.content_fingerprint,
        SkillSemanticReference("content:primary"),
        SkillSemanticReference("storage-profile:registral"),
        NOW,
        SkillSemanticReference("actor:installer"),
        SkillSemanticReference("registration:primary"),
    )
    installation_projection = SkillInstallationProjection(
        identity, (installation,), (installation,), (), (), (), True, installation, True
    )
    activation = SkillActivationRecord(
        SkillStoreRecordId("activation:primary"),
        identity,
        installation_id,
        NOW,
        SkillSemanticReference("actor:operator"),
        SkillLifecycleReason.OPERATOR,
    )
    lifecycle = SkillLifecycleProjection(
        identity,
        SkillActivationState.ACTIVE,
        SkillSelectionState.ELIGIBLE,
        False,
        False,
        False,
        True,
        False,
        True,
        True,
        installation_id,
        None,
        None,
        None,
        activation.record_id,
    )
    return BuildSkillExecutionHandoffRequest(
        subject=identity,
        publication=publication,
        installation_id=installation_id,
        installation=installation_projection,
        activation=activation,
        lifecycle=lifecycle,
        lifecycle_history_complete=True,
        resolution=_resolution(identity),
        dependency_registrations=(),
        logical_entrypoint=SkillLogicalPath("scripts/main.py"),
        execution_profile=SkillExecutionProfileRef("execution-profile:restricted"),
        governance=None,
        intelligence=None,
        private_evals=None,
        governance_occurrences=(),
        intelligence_occurrences=(),
        private_eval_occurrences=(),
        policy=_policy(),
    )


def _with_dependency(
    request: BuildSkillExecutionHandoffRequest,
    *,
    name: str = "dependency-skill",
    registered: bool,
) -> BuildSkillExecutionHandoffRequest:
    selected = _publication(name).identity
    dependency_id = SkillDependencyId("dependency:" + hashlib.sha256(name.encode()).hexdigest())
    decision = SkillDependencyCandidateDecision(dependency_id, selected, True, ())
    resolved = SkillResolvedDependency(
        selected.skill_id,
        (dependency_id,),
        selected,
        SkillDependencyResolutionPolicyVersion(1),
        SkillDependencyLifecycleStatus.ELIGIBLE,
        SkillCompatibilityStatus.OBSERVED_COMPATIBLE,
        False,
        SkillDependencySelectionRationale(
            (SkillDependencySelectionCriterion.REQUIRED_COVERAGE,),
            (decision,),
            SkillDependencyTieBreak.NONE,
        ),
    )
    resolution = replace(request.resolution, resolved=(resolved,))
    registrations = (
        SkillExecutionDependencyRegistrationFact(
            selected,
            (
                SkillDependencyRegistrationStatus.REGISTERED
                if registered
                else SkillDependencyRegistrationStatus.UNKNOWN
            ),
            SkillStoreRecordId("installation:dependency") if registered else None,
            True,
        ),
    )
    return replace(
        request,
        resolution=resolution,
        dependency_registrations=registrations,
    )


def _with_external_bindings(
    request: BuildSkillExecutionHandoffRequest,
) -> BuildSkillExecutionHandoffRequest:
    identity = request.subject
    authority = ExternalAuthorityRef("external-authority:authority-a")
    binder = ExternalBinderRef("external-binder:binder-a")
    decision = GovernanceDecisionRef("governance-decision:decision-a")
    decision_kind = GovernanceDecisionKindRef("governance-decision-kind:kind-a")
    policy = GovernancePolicyRef("governance-policy:policy-a")
    governance_binding = _governance_binding_ref(
        identity, authority, decision, decision_kind, policy
    )
    governance_occurrence = _binding_occurrence_ref(
        "governance", governance_binding, binder, NOW
    )
    governance_record = SkillGovernanceBindingRecord(
        governance_binding,
        governance_occurrence,
        identity,
        decision,
        decision_kind,
        policy,
        authority,
        binder,
        NOW,
    )
    governance = _governance_projection(
        identity, SkillGovernanceBindingHistory((governance_record,), True)
    )

    fact = IntelligenceFactRef("intelligence-fact:fact-a")
    fact_kind = IntelligenceFactKindRef("intelligence-fact-kind:kind-a")
    profile = IntelligenceProfileRef("intelligence-profile:profile-a")
    intelligence_binding = _intelligence_binding_ref(
        identity, authority, fact, fact_kind, profile, None
    )
    intelligence_occurrence = _binding_occurrence_ref(
        "intelligence", intelligence_binding, binder, NOW
    )
    intelligence_record = SkillIntelligenceBindingRecord(
        intelligence_binding,
        intelligence_occurrence,
        identity,
        fact,
        None,
        fact_kind,
        profile,
        authority,
        binder,
        NOW,
        NOW,
    )
    intelligence = _intelligence_projection(
        identity, SkillIntelligenceBindingHistory((intelligence_record,), True)
    )

    private_record = SkillPrivateEvalBindingRecord(
        PrivateEvalBindingRef("private-eval-binding:" + "0" * 64),
        _private_eval_occurrence_ref(
            PrivateEvalBindingRef("private-eval-binding:" + "0" * 64), binder, NOW
        ),
        identity,
        SkillPrivateEvalBindingGranularity.SUITE_RESULT,
        PrivateEvalRunRef("private-eval-run:run-a"),
        PrivateEvalResultRef("private-eval-result:result-a"),
        None,
        PrivateEvalSuiteRef("private-eval-suite:suite-a"),
        None,
        PrivateEvalProfileRef("private-eval-profile:profile-a"),
        None,
        None,
        None,
        (),
        binder,
        NOW,
        NOW,
    )
    private_binding = _private_eval_binding_ref(private_record)
    private_record = replace(
        private_record,
        binding_ref=private_binding,
        occurrence_ref=_private_eval_occurrence_ref(private_binding, binder, NOW),
    )
    private_evals = _private_eval_projection(
        identity, SkillPrivateEvalBindingHistory((private_record,), True)
    )
    return replace(
        request,
        governance=governance,
        intelligence=intelligence,
        private_evals=private_evals,
        governance_occurrences=(governance_record.occurrence_ref,),
        intelligence_occurrences=(intelligence_record.occurrence_ref,),
        private_eval_occurrences=(private_record.occurrence_ref,),
    )


def test_complete_handoff_is_deterministic_deeply_immutable_and_not_authorization() -> None:
    service = SkillExecutionHandoffService()
    left = service.build(_request())
    right = service.build(_request())
    assert left == right
    assert left.draft.handoff_id == right.draft.handoff_id
    assert (
        left.readiness.handoff_structurally_complete
        is SkillExecutionReadinessStatus.SATISFIED
    )
    assert not hasattr(left.draft, "authorized")
    assert not hasattr(left.draft, "executable")
    assert not hasattr(left.draft, "executed")
    with pytest.raises(FrozenInstanceError):
        left.draft.subject = _publication("other-skill").identity  # type: ignore[misc]


@pytest.mark.parametrize(
    "field",
    ("publication", "installation", "lifecycle", "resolution"),
)
def test_exact_subject_correspondence_is_structural(field: str) -> None:
    request = _request()
    other_publication = _publication("other-skill")
    if field == "publication":
        changed = replace(request, publication=other_publication)
    elif field == "installation":
        changed = replace(request, installation=replace(request.installation, identity=other_publication.identity))
    elif field == "lifecycle":
        changed = replace(request, lifecycle=replace(request.lifecycle, identity=other_publication.identity))
    else:
        changed = replace(request, resolution=_resolution(other_publication.identity))
    with pytest.raises(SkillExecutionHandoffCorrespondenceError):
        SkillExecutionHandoffService().build(changed)


@pytest.mark.parametrize(
    ("change", "code"),
    (
        ("missing_installation", SkillExecutionHandoffDiagnosticCode.INSTALLATION_MISSING),
        ("incomplete_history", SkillExecutionHandoffDiagnosticCode.INSTALLATION_HISTORY_INCOMPLETE),
        ("missing_activation", SkillExecutionHandoffDiagnosticCode.ACTIVATION_MISSING),
        ("inactive", SkillExecutionHandoffDiagnosticCode.LIFECYCLE_INACTIVE),
        ("revoked", SkillExecutionHandoffDiagnosticCode.LIFECYCLE_REVOKED),
        ("resolution", SkillExecutionHandoffDiagnosticCode.RESOLUTION_INCOMPLETE),
        ("profile", SkillExecutionHandoffDiagnosticCode.EXECUTION_PROFILE_MISSING),
    ),
)
def test_incomplete_but_structurally_valid_inputs_produce_diagnostics(
    change: str, code: SkillExecutionHandoffDiagnosticCode
) -> None:
    request = _request()
    if change == "missing_installation":
        request = replace(request, installation=replace(request.installation, installations=(), current_registrations=(), has_current_registration=False, last_fact=None))
    elif change == "incomplete_history":
        request = replace(request, installation=replace(request.installation, complete=False))
    elif change == "missing_activation":
        request = replace(request, activation=None)
    elif change == "inactive":
        request = replace(request, lifecycle=replace(request.lifecycle, active=False, activation_state=SkillActivationState.INACTIVE))
    elif change == "revoked":
        request = replace(request, lifecycle=replace(request.lifecycle, active=False, revoked=True, selection_state=SkillSelectionState.REVOKED))
    elif change == "resolution":
        request = replace(request, resolution=_resolution(request.subject, complete=False))
    else:
        request = replace(request, execution_profile=None)
    result = SkillExecutionHandoffService().build(request)
    assert code in {item.code for item in result.draft.diagnostics}
    assert (
        result.readiness.handoff_structurally_complete
        is SkillExecutionReadinessStatus.INCOMPLETE
    )


def test_changed_profile_changes_semantic_identity() -> None:
    request = _request()
    left = SkillExecutionHandoffService().build(request)
    right = SkillExecutionHandoffService().build(
        replace(request, execution_profile=SkillExecutionProfileRef("execution-profile:another"))
    )
    assert left.draft.handoff_id != right.draft.handoff_id


def test_changed_installation_changes_semantic_identity() -> None:
    request = _request()
    assert request.activation is not None
    original = SkillExecutionHandoffService().build(request)
    new_id = SkillStoreRecordId("installation:replacement")
    record = replace(request.installation.installations[0], record_id=new_id)
    activation = replace(
        request.activation,
        record_id=SkillStoreRecordId("activation:replacement"),
        installation_id=new_id,
    )
    changed = replace(
        request,
        installation_id=new_id,
        installation=replace(
            request.installation,
            installations=(record,),
            current_registrations=(record,),
            last_fact=record,
        ),
        activation=activation,
        lifecycle=replace(
            request.lifecycle,
            active_installation_id=new_id,
            last_record_id=activation.record_id,
        ),
    )
    assert (
        SkillExecutionHandoffService().build(changed).draft.handoff_id
        != original.draft.handoff_id
    )


@pytest.mark.parametrize("registered", (False, True))
def test_resolved_dependency_is_distinct_from_local_registration(registered: bool) -> None:
    result = SkillExecutionHandoffService().build(
        _with_dependency(_request(), registered=registered)
    )
    assert len(result.draft.dependencies) == 1
    codes = {item.code for item in result.draft.diagnostics}
    if registered:
        assert SkillExecutionHandoffDiagnosticCode.DEPENDENCY_REGISTRATION_INVALID not in codes
        assert (
            result.readiness.dependency_registration_known
            is SkillExecutionReadinessStatus.SATISFIED
        )
    else:
        assert SkillExecutionHandoffDiagnosticCode.DEPENDENCY_REGISTRATION_INVALID in codes
        assert (
            result.readiness.dependency_registration_known
            is SkillExecutionReadinessStatus.UNKNOWN
        )


def test_changed_resolution_changes_semantic_identity() -> None:
    first = SkillExecutionHandoffService().build(
        _with_dependency(_request(), name="dependency-one", registered=True)
    )
    second = SkillExecutionHandoffService().build(
        _with_dependency(_request(), name="dependency-two", registered=True)
    )
    assert first.draft.handoff_id != second.draft.handoff_id


def test_required_external_families_are_structural_not_approval() -> None:
    request = _request()
    binding_policy = SkillExecutionBindingCompletenessPolicy(True, True, True, True)
    result = SkillExecutionHandoffService().build(
        replace(request, policy=replace(request.policy, bindings=binding_policy))
    )
    assert sum(
        item.code is SkillExecutionHandoffDiagnosticCode.EXTERNAL_BINDING_ABSENT
        for item in result.draft.diagnostics
    ) == 3
    assert (
        result.readiness.external_bindings_complete
        is SkillExecutionReadinessStatus.INCOMPLETE
    )
    assert not hasattr(result.draft, "approved")


@pytest.mark.parametrize(
    "value",
    (
        "",
        "profile:wrong",
        "execution-profile:",
        "execution-profile:with space",
        "execution-profile:../../escape",
        "execution-profile:module:callable",
        "execution-profile:$(shell)",
    ),
)
def test_execution_profile_is_bounded_opaque_and_non_executable(value: str) -> None:
    with pytest.raises(RuntimeError):
        SkillExecutionProfileRef(value)


@pytest.mark.parametrize("value", (0, -1, True))
def test_limits_reject_non_positive_and_bool(value: int) -> None:
    with pytest.raises(InvalidSkillExecutionHandoffPolicy):
        SkillExecutionHandoffLimits(value, 1, 1, 1, 1, 1)


def test_exact_limit_passes_and_max_plus_one_fails() -> None:
    request = _request()
    assert SkillExecutionHandoffService().build(
        replace(request, policy=_policy(max_capabilities=2))
    )
    with pytest.raises(SkillExecutionHandoffLimitExceeded):
        SkillExecutionHandoffService().build(
            replace(request, policy=_policy(max_capabilities=1))
        )


@pytest.mark.parametrize(
    "fingerprint_field",
    ("manifest_fingerprint", "content_fingerprint"),
)
def test_same_skill_and_semver_with_divergent_fingerprint_is_rejected(
    fingerprint_field: str,
) -> None:
    request = _request()
    divergent = SkillManifestFingerprint("f" * 64)
    if fingerprint_field == "manifest_fingerprint":
        identity = replace(request.subject, manifest_fingerprint=divergent)
    else:
        identity = replace(
            request.subject,
            content_fingerprint=SkillContentFingerprint("e" * 64),
        )
    assert identity.skill_id == request.subject.skill_id
    assert identity.version == request.subject.version
    with pytest.raises(SkillExecutionHandoffCorrespondenceError):
        SkillExecutionHandoffService().build(replace(request, subject=identity))


def test_identity_excludes_readiness_and_diagnostics_outputs() -> None:
    draft = SkillExecutionHandoffService().build(_request()).draft
    changed = replace(
        draft,
        diagnostics=(
            SkillExecutionHandoffDiagnostic(
                SkillExecutionHandoffDiagnosticCode.LIFECYCLE_DEPRECATED
            ),
        ),
        readiness=replace(
            draft.readiness,
            handoff_structurally_complete=SkillExecutionReadinessStatus.INCOMPLETE,
        ),
    )
    assert _handoff_id(changed) == draft.handoff_id


def test_semantic_policy_change_changes_identity_but_limit_change_does_not() -> None:
    request = _request()
    baseline = SkillExecutionHandoffService().build(request).draft.handoff_id
    policy_change = replace(request.policy, require_active_subject=False)
    changed = SkillExecutionHandoffService().build(
        replace(request, policy=policy_change)
    ).draft.handoff_id
    limit_change = SkillExecutionHandoffService().build(
        replace(
            request,
            policy=replace(
                request.policy,
                limits=replace(request.policy.limits, max_diagnostics=31),
            ),
        )
    ).draft.handoff_id
    assert changed != baseline
    assert limit_change == baseline


def test_revocation_is_blocking_even_when_active_is_not_required() -> None:
    request = _request()
    request = replace(
        request,
        lifecycle=replace(
            request.lifecycle,
            active=False,
            revoked=True,
            selection_state=SkillSelectionState.REVOKED,
        ),
        policy=replace(request.policy, require_active_subject=False),
    )
    result = SkillExecutionHandoffService().build(request)
    assert (
        result.readiness.lifecycle_activation_satisfied
        is SkillExecutionReadinessStatus.INCOMPLETE
    )
    assert (
        result.readiness.handoff_structurally_complete
        is SkillExecutionReadinessStatus.INCOMPLETE
    )


def test_incomplete_lifecycle_history_is_explicit() -> None:
    result = SkillExecutionHandoffService().build(
        replace(_request(), lifecycle_history_complete=False)
    )
    assert (
        SkillExecutionHandoffDiagnosticCode.LIFECYCLE_HISTORY_INCOMPLETE
        in {item.code for item in result.draft.diagnostics}
    )


def test_security_declaration_is_not_relabelled_as_permissions() -> None:
    draft = SkillExecutionHandoffService().build(_request()).draft
    assert draft.security_declaration == _request().publication.manifest.security
    assert not hasattr(draft, "permissions")
    assert "SkillPermissionDeclaration" not in public_skills.__all__


def test_resources_are_declared_not_allocated() -> None:
    draft = SkillExecutionHandoffService().build(_request()).draft
    assert draft.resources == (SkillResourceRequirement(30, 128, 100),)
    assert not hasattr(draft, "resource_allocation")
    assert not hasattr(draft, "resource_grant")


@pytest.mark.parametrize(
    "value",
    (
        "../main.py",
        "/main.py",
        "C:/main.py",
        r"\\server\share\main.py",
        "scripts/main.py;rm",
        "module:callable",
        "python scripts/main.py",
        "scripts/\x00main.py",
    ),
)
def test_entrypoint_rejects_non_logical_or_executable_syntax(value: str) -> None:
    with pytest.raises(InvalidSkillContentReference):
        SkillLogicalPath(value)


def test_entrypoint_case_is_semantic_and_not_normalized() -> None:
    assert SkillLogicalPath("scripts/Main.py") != SkillLogicalPath("scripts/main.py")


@pytest.mark.parametrize("value", ("v2", 2, True, None))
def test_future_or_invalid_format_version_is_rejected(value: object) -> None:
    with pytest.raises((TypeError, ValueError, RuntimeError)):
        SkillExecutionHandoffFormatVersion(value)  # type: ignore[arg-type]


def test_empty_optional_collections_are_valid() -> None:
    draft = SkillExecutionHandoffService().build(_request()).draft
    assert draft.dependencies == ()
    assert draft.dependency_registrations == ()
    assert draft.governance_occurrences == ()
    assert draft.intelligence_occurrences == ()
    assert draft.private_eval_occurrences == ()


def test_configured_limit_max_and_max_plus_one() -> None:
    assert SkillExecutionHandoffLimits(5_000, 5_000, 5_000, 5_000, 5_000, 5_000)
    with pytest.raises(InvalidSkillExecutionHandoffPolicy):
        SkillExecutionHandoffLimits(5_001, 5_000, 5_000, 5_000, 5_000, 5_000)


def test_public_surface_omits_internal_projection_and_specific_internal_errors() -> None:
    internal = {
        "SkillExecutionDependencyFact",
        "SkillExecutionBindingFamily",
        "SkillExecutionResolutionFact",
        "CorruptSkillExecutionInputProjection",
        "InvalidSkillExecutionBindingReference",
    }
    assert internal.isdisjoint(public_skills.__all__)
    assert {
        "BuildSkillExecutionHandoffRequest",
        "SkillExecutionHandoffDraft",
        "SkillExecutionHandoffBuildResult",
        "SkillExecutionHandoffService",
    }.issubset(public_skills.__all__)


def test_all_three_external_occurrence_families_are_confirmed_from_histories() -> None:
    request = _with_external_bindings(_request())
    request = replace(
        request,
        policy=replace(
            request.policy,
            bindings=SkillExecutionBindingCompletenessPolicy(
                True, True, True, True
            ),
        ),
    )
    result = SkillExecutionHandoffService().build(request)
    assert (
        result.readiness.external_bindings_complete
        is SkillExecutionReadinessStatus.SATISFIED
    )
    assert len(result.draft.governance_occurrences) == 1
    assert len(result.draft.intelligence_occurrences) == 1
    assert len(result.draft.private_eval_occurrences) == 1


@pytest.mark.parametrize("family", ("governance", "intelligence", "private_evals"))
def test_fabricated_external_binding_correspondence_is_rejected(family: str) -> None:
    request = _with_external_bindings(_request())
    if family == "governance":
        assert request.governance is not None
        governance_record = replace(
            request.governance.history.records[0],
            binding_ref=ExternalBindingRef("governance-binding:" + "f" * 64),
        )
        request = replace(
            request,
            governance=replace(
                request.governance,
                history=SkillGovernanceBindingHistory((governance_record,), True),
            ),
        )
    elif family == "intelligence":
        assert request.intelligence is not None
        intelligence_record = replace(
            request.intelligence.history.records[0],
            binding_ref=ExternalBindingRef("intelligence-binding:" + "e" * 64),
        )
        request = replace(
            request,
            intelligence=replace(
                request.intelligence,
                history=SkillIntelligenceBindingHistory((intelligence_record,), True),
            ),
        )
    else:
        assert request.private_evals is not None
        private_eval_record = replace(
            request.private_evals.history.records[0],
            binding_ref=PrivateEvalBindingRef(
                "private-eval-binding:" + "d" * 64
            ),
        )
        request = replace(
            request,
            private_evals=replace(
                request.private_evals,
                history=SkillPrivateEvalBindingHistory((private_eval_record,), True),
            ),
        )
    with pytest.raises(RuntimeError):
        SkillExecutionHandoffService().build(request)


@pytest.mark.parametrize("family", ("governance", "intelligence", "private_evals"))
def test_duplicate_external_occurrence_selection_is_rejected(family: str) -> None:
    request = _with_external_bindings(_request())
    if family == "governance":
        request = replace(
            request,
            governance_occurrences=request.governance_occurrences * 2,
        )
    elif family == "intelligence":
        request = replace(
            request,
            intelligence_occurrences=request.intelligence_occurrences * 2,
        )
    else:
        request = replace(
            request,
            private_eval_occurrences=request.private_eval_occurrences * 2,
        )
    with pytest.raises(RuntimeError):
        SkillExecutionHandoffService().build(request)


@pytest.mark.parametrize("family", ("governance", "intelligence", "private_evals"))
def test_incomplete_selected_external_history_is_policy_relative(family: str) -> None:
    request = _with_external_bindings(_request())
    if family == "governance":
        assert request.governance is not None
        request = replace(
            request,
            governance=replace(
                request.governance,
                history=replace(request.governance.history, complete=False),
                complete=False,
            ),
        )
    elif family == "intelligence":
        assert request.intelligence is not None
        request = replace(
            request,
            intelligence=replace(
                request.intelligence,
                history=replace(request.intelligence.history, complete=False),
                complete=False,
            ),
        )
    else:
        assert request.private_evals is not None
        request = replace(
            request,
            private_evals=replace(
                request.private_evals,
                history=replace(request.private_evals.history, complete=False),
                complete=False,
            ),
        )
    result = SkillExecutionHandoffService().build(request)
    assert (
        SkillExecutionHandoffDiagnosticCode.BINDING_HISTORY_INCOMPLETE
        in {item.code for item in result.draft.diagnostics}
    )
