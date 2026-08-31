from __future__ import annotations

from dataclasses import replace

import pytest
from tests.test_skills_phase12_handoff import NOW, _request

from synapse.sandbox import (
    ArtifactAvailability,
    OpaqueReference,
    SandboxArtifactFingerprint,
    SandboxIsolationProfileId,
    SandboxPolicyVersion,
    SandboxWorkloadId,
)
from synapse.sandbox_integrations import (
    SKILLS_SANDBOX_COMPATIBILITY_V1,
    SandboxSkillsHandoffAdapter,
    SandboxSkillsHandoffDiagnosticCode,
    SandboxSkillsHandoffRequest,
    SandboxSkillsHandoffStatus,
)
from synapse.skills import SkillExecutionHandoffService, SkillExecutionReadinessStatus


def _translation_request() -> SandboxSkillsHandoffRequest:
    handoff = SkillExecutionHandoffService().build(_request()).draft
    entrypoint = handoff.logical_entrypoint
    assert entrypoint is not None
    return SandboxSkillsHandoffRequest(
        handoff=handoff,
        workload_id=SandboxWorkloadId("workload:skill-handoff"),
        expected_subject_identity=handoff.subject.to_canonical_text(),
        expected_handoff_fingerprint=SandboxArtifactFingerprint(
            f"sha256:{handoff.handoff_id.value}"
        ),
        expected_content_fingerprint=SandboxArtifactFingerprint(
            f"sha256:{handoff.subject.content_fingerprint.value}"
        ),
        expected_entrypoint=entrypoint.logical_path.value,
        expected_entrypoint_fingerprint=SandboxArtifactFingerprint(
            f"sha256:{entrypoint.fingerprint.value}"
        ),
        artifact_ref=OpaqueReference("skill-artifact:entrypoint"),
        actor_ref=OpaqueReference("actor:requester"),
        purpose="translate structural skill handoff",
        correlation_ref=OpaqueReference("correlation:skill-handoff"),
        expected_execution_profile=OpaqueReference("execution-profile:restricted"),
        expected_isolation_profile=SandboxIsolationProfileId("sandbox-profile:restricted"),
        isolation_policy_version=SandboxPolicyVersion("sandbox-policy:v1"),
        runtime_version="3.12",
        observed_at=NOW,
    )


def _codes(request: SandboxSkillsHandoffRequest) -> set[SandboxSkillsHandoffDiagnosticCode]:
    return {
        diagnostic.code
        for diagnostic in SandboxSkillsHandoffAdapter().translate(request).diagnostics
    }


def test_v1_translation_is_deterministic_reference_only_and_preserves_fingerprints() -> None:
    request = _translation_request()
    left = SandboxSkillsHandoffAdapter().translate(request)
    right = SandboxSkillsHandoffAdapter().translate(request)

    assert left == right
    assert left.status is SandboxSkillsHandoffStatus.TRANSLATED
    assert left.source_subject_identity == request.expected_subject_identity
    assert left.source_handoff_fingerprint == request.expected_handoff_fingerprint
    assert left.admission_request is not None
    assert left.admission_request.handoff_fingerprint == request.expected_handoff_fingerprint
    assert left.admission_request.structurally_complete
    assert left.facts_snapshot is not None
    assert (
        left.facts_snapshot.artifact_facts[0].fingerprint == request.expected_entrypoint_fingerprint
    )
    assert left.facts_snapshot.artifact_facts[0].availability is ArtifactAvailability.UNKNOWN


def test_structural_handoff_does_not_create_admission_authorization_or_grants() -> None:
    result = SandboxSkillsHandoffAdapter().translate(_translation_request())
    assert result.admission_request is not None
    assert result.admission_request.approval_ref is None
    assert result.admission_request.policy_refs == ()
    assert result.facts_snapshot is not None
    assert result.facts_snapshot.capability_facts == ()
    assert result.facts_snapshot.resource_facts == ()


def test_incomplete_handoff_fails_closed_even_if_installation_and_activation_exist() -> None:
    request = _translation_request()
    readiness = replace(
        request.handoff.readiness,
        handoff_structurally_complete=SkillExecutionReadinessStatus.INCOMPLETE,
    )
    changed = replace(request, handoff=replace(request.handoff, readiness=readiness))
    result = SandboxSkillsHandoffAdapter().translate(changed)
    assert result.status is SandboxSkillsHandoffStatus.INCOMPATIBLE
    assert result.admission_request is None
    assert SandboxSkillsHandoffDiagnosticCode.HANDOFF_INCOMPLETE in {
        item.code for item in result.diagnostics
    }


@pytest.mark.parametrize(
    ("change", "expected"),
    (
        ("subject", SandboxSkillsHandoffDiagnosticCode.SUBJECT_MISMATCH),
        ("handoff", SandboxSkillsHandoffDiagnosticCode.HANDOFF_FINGERPRINT_MISMATCH),
        ("content", SandboxSkillsHandoffDiagnosticCode.ARTIFACT_MISMATCH),
        ("entrypoint", SandboxSkillsHandoffDiagnosticCode.ENTRYPOINT_INCOMPATIBLE),
        ("entrypoint_fingerprint", SandboxSkillsHandoffDiagnosticCode.ARTIFACT_MISMATCH),
        ("profile", SandboxSkillsHandoffDiagnosticCode.EXECUTION_PROFILE_MISMATCH),
        ("isolation", SandboxSkillsHandoffDiagnosticCode.ISOLATION_PROFILE_MISMATCH),
    ),
)
def test_correspondence_mismatches_fail_closed(
    change: str, expected: SandboxSkillsHandoffDiagnosticCode
) -> None:
    request = _translation_request()
    replacements: dict[str, object] = {
        "subject": "other-subject",
        "handoff": SandboxArtifactFingerprint("sha256:" + "1" * 64),
        "content": SandboxArtifactFingerprint("sha256:" + "2" * 64),
        "entrypoint": "scripts/other.py",
        "entrypoint_fingerprint": SandboxArtifactFingerprint("sha256:" + "3" * 64),
        "profile": OpaqueReference("execution-profile:other"),
        "isolation": SandboxIsolationProfileId("sandbox-profile:other"),
    }
    fields = {
        "subject": "expected_subject_identity",
        "handoff": "expected_handoff_fingerprint",
        "content": "expected_content_fingerprint",
        "entrypoint": "expected_entrypoint",
        "entrypoint_fingerprint": "expected_entrypoint_fingerprint",
        "profile": "expected_execution_profile",
        "isolation": "expected_isolation_profile",
    }
    changed = replace(request, **{fields[change]: replacements[change]})
    assert expected in _codes(changed)
    assert SandboxSkillsHandoffAdapter().translate(changed).admission_request is None


def test_unknown_version_and_unsafe_declarations_are_not_ignored() -> None:
    version_request = _translation_request()
    object.__setattr__(version_request.handoff, "format_version", "v2")
    assert SandboxSkillsHandoffDiagnosticCode.UNKNOWN_VERSION in _codes(version_request)

    capability_request = _translation_request()
    capability = capability_request.handoff.capabilities[0]
    object.__setattr__(capability.capability_id, "value", "INVALID CAPABILITY")
    assert SandboxSkillsHandoffDiagnosticCode.CAPABILITY_INVALID in _codes(capability_request)

    resource_request = _translation_request()
    resource_request = replace(
        resource_request,
        handoff=replace(resource_request.handoff, resources=()),
    )
    assert SandboxSkillsHandoffDiagnosticCode.RESOURCE_INVALID in _codes(resource_request)


def test_runtime_and_entrypoint_equivalence_is_explicit_and_versioned() -> None:
    assert SKILLS_SANDBOX_COMPATIBILITY_V1.skills_handoff_version == "v1"
    assert SKILLS_SANDBOX_COMPATIBILITY_V1.runtime_equivalences == (
        ("python", SKILLS_SANDBOX_COMPATIBILITY_V1.runtime_equivalences[0][1], "text/x-python"),
        ("wasm", SKILLS_SANDBOX_COMPATIBILITY_V1.runtime_equivalences[1][1], "application/wasm"),
    )
    request = _translation_request()
    entrypoint = request.handoff.logical_entrypoint
    assert entrypoint is not None
    incompatible = replace(
        request,
        handoff=replace(
            request.handoff,
            logical_entrypoint=replace(entrypoint, media_type="application/octet-stream"),
        ),
    )
    assert SandboxSkillsHandoffDiagnosticCode.RUNTIME_INCOMPATIBLE in _codes(incompatible)
    assert SandboxSkillsHandoffDiagnosticCode.RUNTIME_INCOMPATIBLE in _codes(
        replace(request, runtime_version="latest")
    )
