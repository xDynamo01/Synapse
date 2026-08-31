"""Reference-only translation from frozen Skills handoff V1 to Sandbox admission DTOs."""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from datetime import datetime
from enum import StrEnum

from synapse.sandbox import (
    AdmissionFactDimension,
    ArtifactAvailability,
    CapabilityDeclaration,
    DimensionCompleteness,
    FactCompleteness,
    HandoffReadiness,
    OpaqueReference,
    RequestedCapability,
    ResourceRequest,
    SandboxAdmissionFactsSnapshot,
    SandboxAdmissionRequest,
    SandboxArtifactFact,
    SandboxArtifactFingerprint,
    SandboxHandoffFact,
    SandboxIsolationProfileId,
    SandboxPolicyVersion,
    SandboxRuntimeDescriptor,
    SandboxRuntimeKind,
    SandboxWorkloadId,
)
from synapse.skills import (
    SkillExecutionHandoffDraft,
    SkillExecutionHandoffFormatVersion,
    SkillExecutionReadinessStatus,
)

SKILLS_SANDBOX_ADAPTER_FORMAT = "skills-sandbox-handoff-adapter-v1"
_NAME = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_RUNTIME_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+){0,3}$")
_SKILLS_HANDOFF_FIELDS = frozenset(
    {
        "format_version",
        "handoff_id",
        "subject",
        "installation_id",
        "activation_id",
        "requirements",
        "installation",
        "lifecycle",
        "resolution",
        "dependencies",
        "dependency_registrations",
        "capabilities",
        "security_declaration",
        "resources",
        "required_tools",
        "execution_runtime",
        "execution_profile",
        "logical_entrypoint",
        "governance_occurrences",
        "intelligence_occurrences",
        "private_eval_occurrences",
        "binding_histories",
        "readiness",
        "diagnostics",
    }
)


class SandboxSkillsHandoffStatus(StrEnum):
    TRANSLATED = "translated"
    INCOMPATIBLE = "incompatible"


class SandboxSkillsHandoffDiagnosticCode(StrEnum):
    UNKNOWN_VERSION = "unknown_version"
    UNKNOWN_FIELD = "unknown_field"
    HANDOFF_INCOMPLETE = "handoff_incomplete"
    SUBJECT_MISMATCH = "subject_mismatch"
    HANDOFF_FINGERPRINT_MISMATCH = "handoff_fingerprint_mismatch"
    ARTIFACT_MISMATCH = "artifact_mismatch"
    RUNTIME_INCOMPATIBLE = "runtime_incompatible"
    ENTRYPOINT_INCOMPATIBLE = "entrypoint_incompatible"
    EXECUTION_PROFILE_MISMATCH = "execution_profile_mismatch"
    ISOLATION_PROFILE_MISMATCH = "isolation_profile_mismatch"
    CAPABILITY_INVALID = "capability_invalid"
    RESOURCE_INVALID = "resource_invalid"
    REQUIRED_FIELD_UNTRANSLATABLE = "required_field_untranslatable"


@dataclass(frozen=True, order=True, slots=True)
class SandboxSkillsHandoffDiagnostic:
    code: SandboxSkillsHandoffDiagnosticCode
    field: str


@dataclass(frozen=True, slots=True)
class SkillsSandboxCompatibility:
    format_version: str
    skills_handoff_version: str
    sandbox_admission_contract: str
    sandbox_facts_contract: str
    runtime_equivalences: tuple[tuple[str, SandboxRuntimeKind, str], ...]
    profile_equivalences: tuple[tuple[str, str], ...]


SKILLS_SANDBOX_COMPATIBILITY_V1 = SkillsSandboxCompatibility(
    SKILLS_SANDBOX_ADAPTER_FORMAT,
    SkillExecutionHandoffFormatVersion.V1.value,
    "SandboxAdmissionRequest:v1",
    "sandbox-admission-facts-v1",
    (
        ("python", SandboxRuntimeKind.PYTHON, "text/x-python"),
        ("wasm", SandboxRuntimeKind.WASM, "application/wasm"),
    ),
    (("execution-profile:restricted", "sandbox-profile:restricted"),),
)


@dataclass(frozen=True, kw_only=True, slots=True)
class SandboxSkillsHandoffRequest:
    handoff: SkillExecutionHandoffDraft
    workload_id: SandboxWorkloadId
    expected_subject_identity: str
    expected_handoff_fingerprint: SandboxArtifactFingerprint
    expected_content_fingerprint: SandboxArtifactFingerprint
    expected_entrypoint: str
    expected_entrypoint_fingerprint: SandboxArtifactFingerprint
    artifact_ref: OpaqueReference
    actor_ref: OpaqueReference
    purpose: str
    correlation_ref: OpaqueReference
    expected_execution_profile: OpaqueReference
    expected_isolation_profile: SandboxIsolationProfileId
    isolation_policy_version: SandboxPolicyVersion
    runtime_version: str
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class SandboxSkillsHandoffResult:
    status: SandboxSkillsHandoffStatus
    source_subject_identity: str
    source_handoff_fingerprint: SandboxArtifactFingerprint | None
    admission_request: SandboxAdmissionRequest | None
    facts_snapshot: SandboxAdmissionFactsSnapshot | None
    runtime: SandboxRuntimeDescriptor | None
    entrypoint_ref: OpaqueReference | None
    diagnostics: tuple[SandboxSkillsHandoffDiagnostic, ...]


class SandboxSkillsHandoffAdapter:
    """Pure translation only; it performs no admission, policy, grant or I/O operation."""

    def translate(self, request: SandboxSkillsHandoffRequest) -> SandboxSkillsHandoffResult:
        draft = request.handoff
        source_identity = draft.subject.to_canonical_text()
        handoff_fingerprint = _fingerprint(draft.handoff_id.value)
        diagnostics: list[SandboxSkillsHandoffDiagnostic] = []

        def reject(code: SandboxSkillsHandoffDiagnosticCode, field: str) -> None:
            diagnostics.append(SandboxSkillsHandoffDiagnostic(code, field))

        if draft.format_version is not SkillExecutionHandoffFormatVersion.V1:
            reject(SandboxSkillsHandoffDiagnosticCode.UNKNOWN_VERSION, "format_version")
        if {item.name for item in fields(draft)} != _SKILLS_HANDOFF_FIELDS:
            reject(SandboxSkillsHandoffDiagnosticCode.UNKNOWN_FIELD, "handoff")
        if (
            draft.readiness.handoff_structurally_complete
            is not SkillExecutionReadinessStatus.SATISFIED
        ):
            reject(SandboxSkillsHandoffDiagnosticCode.HANDOFF_INCOMPLETE, "readiness")
        if source_identity != request.expected_subject_identity:
            reject(SandboxSkillsHandoffDiagnosticCode.SUBJECT_MISMATCH, "subject")
        if handoff_fingerprint != request.expected_handoff_fingerprint:
            reject(SandboxSkillsHandoffDiagnosticCode.HANDOFF_FINGERPRINT_MISMATCH, "handoff_id")
        if (
            _fingerprint(draft.subject.content_fingerprint.value)
            != request.expected_content_fingerprint
        ):
            reject(
                SandboxSkillsHandoffDiagnosticCode.ARTIFACT_MISMATCH, "subject.content_fingerprint"
            )

        entrypoint = draft.logical_entrypoint
        runtime = draft.execution_runtime
        profile = draft.execution_profile
        if entrypoint is None:
            reject(
                SandboxSkillsHandoffDiagnosticCode.REQUIRED_FIELD_UNTRANSLATABLE,
                "logical_entrypoint",
            )
        elif entrypoint.logical_path.value != request.expected_entrypoint:
            reject(SandboxSkillsHandoffDiagnosticCode.ENTRYPOINT_INCOMPATIBLE, "logical_entrypoint")
        elif _fingerprint(entrypoint.fingerprint.value) != request.expected_entrypoint_fingerprint:
            reject(
                SandboxSkillsHandoffDiagnosticCode.ARTIFACT_MISMATCH,
                "logical_entrypoint.fingerprint",
            )
        if runtime is None:
            reject(
                SandboxSkillsHandoffDiagnosticCode.REQUIRED_FIELD_UNTRANSLATABLE,
                "execution_runtime",
            )
        runtime_mapping = next(
            (
                item
                for item in SKILLS_SANDBOX_COMPATIBILITY_V1.runtime_equivalences
                if runtime is not None and item[0] == runtime.value
            ),
            None,
        )
        if (
            runtime_mapping is None
            or entrypoint is not None
            and entrypoint.media_type != runtime_mapping[2]
            or not _RUNTIME_VERSION.fullmatch(request.runtime_version)
        ):
            reject(SandboxSkillsHandoffDiagnosticCode.RUNTIME_INCOMPATIBLE, "execution_runtime")
        if profile is None or profile.value != request.expected_execution_profile.value:
            reject(
                SandboxSkillsHandoffDiagnosticCode.EXECUTION_PROFILE_MISMATCH, "execution_profile"
            )
        required_isolation = draft.security_declaration.sandbox_profile_requirement
        profile_mapping = next(
            (
                item
                for item in SKILLS_SANDBOX_COMPATIBILITY_V1.profile_equivalences
                if profile is not None and item[0] == profile.value
            ),
            None,
        )
        mapped_isolation = (
            required_isolation.value
            if required_isolation is not None
            else profile_mapping[1]
            if profile_mapping is not None
            else None
        )
        if mapped_isolation != request.expected_isolation_profile.value:
            reject(
                SandboxSkillsHandoffDiagnosticCode.ISOLATION_PROFILE_MISMATCH,
                "security_declaration.sandbox_profile_requirement",
            )
        capabilities = tuple(item.capability_id.value for item in draft.capabilities)
        if (
            len(set(capabilities)) != len(capabilities)
            or any(not _NAME.fullmatch(item) for item in capabilities)
            or any(item.version_constraint is not None for item in draft.capabilities)
        ):
            reject(SandboxSkillsHandoffDiagnosticCode.CAPABILITY_INVALID, "capabilities")
        if draft.required_tools:
            reject(
                SandboxSkillsHandoffDiagnosticCode.REQUIRED_FIELD_UNTRANSLATABLE,
                "required_tools",
            )
        if len(draft.resources) != 1:
            reject(SandboxSkillsHandoffDiagnosticCode.RESOURCE_INVALID, "resources")
        diagnostics_tuple = tuple(sorted(set(diagnostics)))
        if diagnostics_tuple:
            return SandboxSkillsHandoffResult(
                SandboxSkillsHandoffStatus.INCOMPATIBLE,
                source_identity,
                handoff_fingerprint,
                None,
                None,
                None,
                None,
                diagnostics_tuple,
            )

        assert entrypoint is not None and runtime_mapping is not None and profile is not None
        resource = draft.resources[0]
        subject_ref = OpaqueReference(f"skill:{draft.subject.skill_id}@{draft.subject.version}")
        entrypoint_ref = OpaqueReference(f"skill-entrypoint:{entrypoint.logical_path.value}")
        declared = tuple(CapabilityDeclaration(item) for item in sorted(capabilities))
        resources = (
            ResourceRequest("timeout.seconds", resource.timeout_seconds, "seconds"),
            ResourceRequest("memory.mebibytes", resource.memory_mebibytes, "mebibytes"),
            ResourceRequest("cpu.millicores", resource.cpu_millicores, "millicores"),
        )
        admission = SandboxAdmissionRequest(
            request.workload_id,
            subject_ref,
            handoff_fingerprint,
            request.actor_ref,
            request.purpose,
            request.correlation_ref,
            (),
            None,
            declared,
            tuple(RequestedCapability(item.name) for item in declared),
            resources,
            request.expected_execution_profile,
            request.isolation_policy_version,
            request.expected_isolation_profile,
            tuple(
                OpaqueReference(item.value)
                for item in draft.security_declaration.secret_reference_requirements
            ),
            True,
        )
        completeness = tuple(
            DimensionCompleteness(
                dimension,
                FactCompleteness.COMPLETE
                if dimension
                in {
                    AdmissionFactDimension.HANDOFF,
                    AdmissionFactDimension.ARTIFACT,
                    AdmissionFactDimension.CAPABILITIES,
                    AdmissionFactDimension.RESOURCES,
                }
                else FactCompleteness.UNKNOWN,
            )
            for dimension in AdmissionFactDimension
        )
        snapshot = SandboxAdmissionFactsSnapshot.create(
            observed_at=request.observed_at,
            handoff_facts=(
                SandboxHandoffFact(
                    subject_ref,
                    handoff_fingerprint,
                    request.expected_content_fingerprint,
                    request.actor_ref,
                    request.purpose,
                    request.correlation_ref,
                    HandoffReadiness.READY,
                ),
            ),
            artifact_facts=(
                SandboxArtifactFact(
                    subject_ref,
                    request.artifact_ref,
                    request.expected_entrypoint_fingerprint,
                    ArtifactAvailability.UNKNOWN,
                ),
            ),
            completeness=completeness,
        )
        return SandboxSkillsHandoffResult(
            SandboxSkillsHandoffStatus.TRANSLATED,
            source_identity,
            handoff_fingerprint,
            admission,
            snapshot,
            SandboxRuntimeDescriptor(runtime_mapping[1], request.runtime_version),
            entrypoint_ref,
            (),
        )


def _fingerprint(value: str) -> SandboxArtifactFingerprint:
    return SandboxArtifactFingerprint(f"sha256:{value}")
