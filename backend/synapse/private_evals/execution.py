from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from synapse.intelligence_boundary.models import OperatingProfile

from .canonical import fingerprint
from .catalog import DatasetBindingRef, EvalCaseVersion, EvalCaseVersionRef, EvaluatorIdentity
from .execution_errors import (
    ExecutionIdentityMismatch,
    ExecutionProvenanceMissing,
    ExecutionRequestInvalid,
    ExecutionResponseMismatch,
    OutputReferenceMissing,
    RequestIdempotencyConflict,
    ResponseFingerprintMismatch,
    ResponseIntegrityConflict,
)
from .runs import EvalRunManifest, ExecutionProtocol, ResourceUsage, VersionedComponentRef
from .store_models import IdempotencyKey
from .values import (
    ContentChecksum,
    EvalRunId,
    EvalRunManifestId,
    EvalSuiteId,
    EvalVersion,
    Fingerprint,
    UtcTimestamp,
)

_SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~:-]{0,255}$")
_SENSITIVE = re.compile(
    r"(?i)(?:token|secret|password|credential|authorization|bearer|api[_-]?key|sk-)"
)


def _safe_reference(value: str, label: str) -> None:
    if not isinstance(value, str) or not _SAFE_REFERENCE.fullmatch(value):
        raise ExecutionRequestInvalid(f"{label} must be a safe opaque reference")
    if _SENSITIVE.search(value) or "/" in value or "\\" in value or "://" in value:
        raise ExecutionRequestInvalid(f"{label} must be a safe opaque reference")


def _positive(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ExecutionRequestInvalid(f"{label} must be positive")


def _unique(values: tuple[object, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ExecutionRequestInvalid(f"duplicate {label} reference")


class CaseExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    INFRASTRUCTURE_FAILED = "infrastructure_failed"
    CANCELLED = "cancelled"
    POLICY_DENIED = "policy_denied"
    INVALID = "invalid"
    TIMED_OUT = "timed_out"


class ExecutionReasonCode(StrEnum):
    COMPLETED = "completed"
    INFRASTRUCTURE_UNAVAILABLE = "infrastructure_unavailable"
    CANCELLED_BY_REQUEST = "cancelled_by_request"
    POLICY_NOT_AUTHORIZED = "policy_not_authorized"
    RESPONSE_INVALID = "response_invalid"
    EXECUTION_TIMEOUT = "execution_timeout"


class ReplayDisposition(StrEnum):
    NEW = "new"
    SAFE_REPLAY = "safe_replay"


@dataclass(frozen=True)
class LogicalExecutionIdentity:
    """Unique accepted result identity: run + case version + repetition."""

    run_id: EvalRunId
    case_reference: EvalCaseVersionRef
    repetition: int
    fingerprint: Fingerprint | None = None

    def __post_init__(self) -> None:
        _positive(self.repetition, "repetition")
        expected = fingerprint(
            {
                "run_id": self.run_id,
                "case_reference": self.case_reference,
                "repetition": self.repetition,
            }
        )
        if self.fingerprint is None:
            object.__setattr__(self, "fingerprint", expected)
        elif self.fingerprint != expected:
            raise ExecutionIdentityMismatch("logical execution fingerprint is inconsistent")


@dataclass(frozen=True)
class ExecutionAttemptIdentity:
    logical_execution_fingerprint: Fingerprint
    attempt: int
    fingerprint: Fingerprint | None = None

    def __post_init__(self) -> None:
        _positive(self.attempt, "execution attempt")
        expected = fingerprint(
            {
                "logical_execution_fingerprint": self.logical_execution_fingerprint,
                "attempt": self.attempt,
            }
        )
        if self.fingerprint is None:
            object.__setattr__(self, "fingerprint", expected)
        elif self.fingerprint != expected:
            raise ExecutionIdentityMismatch("attempt fingerprint is inconsistent")


@dataclass(frozen=True)
class CaseExecutionRequest:
    logical_execution: LogicalExecutionIdentity
    attempt_identity: ExecutionAttemptIdentity
    manifest_id: EvalRunManifestId
    manifest_fingerprint: Fingerprint
    suite_id: EvalSuiteId
    suite_version: EvalVersion
    dataset_binding: DatasetBindingRef
    input_asset_references: tuple[str, ...]
    expected_evaluator: EvaluatorIdentity
    model_provider_snapshot_reference: str | None
    model_provider_snapshot_fingerprint: Fingerprint | None
    skill_references: tuple[VersionedComponentRef, ...]
    tool_references: tuple[VersionedComponentRef, ...]
    security_snapshot_reference: str
    security_snapshot_fingerprint: Fingerprint
    reauthorization_reference: str | None
    canonical_egress_manifest_reference: str
    canonical_egress_manifest_fingerprint: Fingerprint
    operating_profile: OperatingProfile
    timeout_seconds: Decimal
    seed: int
    execution_protocol: ExecutionProtocol
    idempotency_key: IdempotencyKey
    correlation_reference: str
    fingerprint: Fingerprint | None = None

    def __post_init__(self) -> None:
        logical_fingerprint = self.logical_execution.fingerprint
        assert logical_fingerprint is not None
        if self.attempt_identity.logical_execution_fingerprint != logical_fingerprint:
            raise ExecutionIdentityMismatch("attempt does not identify the logical execution")
        if not isinstance(self.timeout_seconds, Decimal) or not self.timeout_seconds.is_finite():
            raise ExecutionRequestInvalid("execution timeout must be a finite Decimal")
        if self.timeout_seconds <= 0:
            raise ExecutionRequestInvalid("execution timeout must be positive")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ExecutionRequestInvalid("execution seed must be an integer")
        paired_model = (
            self.model_provider_snapshot_reference is None
            and self.model_provider_snapshot_fingerprint is None
        ) or (
            self.model_provider_snapshot_reference is not None
            and self.model_provider_snapshot_fingerprint is not None
        )
        if not paired_model:
            raise ExecutionRequestInvalid("model snapshot reference and fingerprint must be paired")
        for value, label in (
            (self.security_snapshot_reference, "security snapshot reference"),
            (self.canonical_egress_manifest_reference, "egress manifest reference"),
            (self.correlation_reference, "correlation reference"),
        ):
            _safe_reference(value, label)
        for optional_value, label in (
            (self.model_provider_snapshot_reference, "model provider snapshot reference"),
            (self.reauthorization_reference, "reauthorization reference"),
        ):
            if optional_value is not None:
                _safe_reference(optional_value, label)
        for reference in self.input_asset_references:
            _safe_reference(reference, "input asset reference")
        _unique(self.input_asset_references, "input asset")
        _unique(self.skill_references, "Skill")
        _unique(self.tool_references, "Tool")
        expected = request_fingerprint(self)
        if self.fingerprint is None:
            object.__setattr__(self, "fingerprint", expected)
        elif self.fingerprint != expected:
            raise ExecutionRequestInvalid("execution request fingerprint is inconsistent")

    def __repr__(self) -> str:
        return (
            "CaseExecutionRequest("
            f"logical_execution={self.logical_execution.fingerprint!r}, "
            f"attempt={self.attempt_identity.attempt!r}, fingerprint={self.fingerprint!r})"
        )


def request_fingerprint(request: CaseExecutionRequest) -> Fingerprint:
    """Semantic attempt request identity; excludes key and correlation metadata."""
    return fingerprint(
        {
            "logical_execution": request.logical_execution,
            "attempt_identity": request.attempt_identity,
            "manifest": (request.manifest_id, request.manifest_fingerprint),
            "suite": (request.suite_id, request.suite_version),
            "dataset_binding": request.dataset_binding,
            "input_assets": tuple(sorted(request.input_asset_references)),
            "expected_evaluator": request.expected_evaluator,
            "model_provider_snapshot": (
                request.model_provider_snapshot_reference,
                request.model_provider_snapshot_fingerprint,
            ),
            "skill_references": tuple(sorted(request.skill_references, key=repr)),
            "tool_references": tuple(sorted(request.tool_references, key=repr)),
            "security_snapshot": (
                request.security_snapshot_reference,
                request.security_snapshot_fingerprint,
            ),
            "reauthorization_reference": request.reauthorization_reference,
            "egress_manifest": (
                request.canonical_egress_manifest_reference,
                request.canonical_egress_manifest_fingerprint,
            ),
            "operating_profile": request.operating_profile,
            "timeout_seconds": request.timeout_seconds,
            "seed": request.seed,
            "execution_protocol": request.execution_protocol,
        }
    )


@dataclass(frozen=True)
class CaseExecutionResponse:
    logical_execution_reference: Fingerprint
    attempt_reference: Fingerprint
    status: CaseExecutionStatus
    output_asset_reference: str | None
    result_checksum: ContentChecksum | None
    evaluator_artifact_reference: str | None
    usage_summary: ResourceUsage
    started_at: UtcTimestamp
    finished_at: UtcTimestamp
    provider_execution_reference: str | None
    provenance_reference: str
    reason_codes: tuple[ExecutionReasonCode, ...]
    fingerprint: Fingerprint | None = None

    def __post_init__(self) -> None:
        _validate_response_fields(self)
        expected = response_fingerprint(self)
        if self.fingerprint is None:
            object.__setattr__(self, "fingerprint", expected)
        elif self.fingerprint != expected:
            raise ResponseFingerprintMismatch("execution response fingerprint is inconsistent")

    def __repr__(self) -> str:
        return (
            "CaseExecutionResponse("
            f"attempt_reference={self.attempt_reference!r}, status={self.status!r}, "
            f"fingerprint={self.fingerprint!r})"
        )


def _validate_response_fields(response: CaseExecutionResponse) -> None:
        if response.finished_at.instant < response.started_at.instant:
            raise ExecutionResponseMismatch("execution timestamps are inconsistent")
        if not response.provenance_reference:
            raise ExecutionProvenanceMissing("execution response requires provenance")
        _safe_reference(response.provenance_reference, "provenance reference")
        if response.provider_execution_reference is not None:
            _safe_reference(response.provider_execution_reference, "provider execution reference")
        _unique(response.reason_codes, "execution reason")
        if not response.reason_codes:
            raise ExecutionResponseMismatch("execution response requires a reason code")
        expected_reasons = {
            CaseExecutionStatus.SUCCEEDED: ExecutionReasonCode.COMPLETED,
            CaseExecutionStatus.INFRASTRUCTURE_FAILED: (
                ExecutionReasonCode.INFRASTRUCTURE_UNAVAILABLE
            ),
            CaseExecutionStatus.CANCELLED: ExecutionReasonCode.CANCELLED_BY_REQUEST,
            CaseExecutionStatus.POLICY_DENIED: ExecutionReasonCode.POLICY_NOT_AUTHORIZED,
            CaseExecutionStatus.INVALID: ExecutionReasonCode.RESPONSE_INVALID,
            CaseExecutionStatus.TIMED_OUT: ExecutionReasonCode.EXECUTION_TIMEOUT,
        }
        if expected_reasons[response.status] not in response.reason_codes:
            raise ExecutionResponseMismatch("execution response reason is incompatible with status")
        successful = response.status is CaseExecutionStatus.SUCCEEDED
        output_fields = (
            response.output_asset_reference,
            response.result_checksum,
            response.evaluator_artifact_reference,
        )
        if successful and any(value is None for value in output_fields):
            raise OutputReferenceMissing("successful execution requires final output references")
        if not successful and any(value is not None for value in output_fields):
            raise ExecutionResponseMismatch("non-successful execution cannot contain final output")
        for value, label in (
            (response.output_asset_reference, "output asset reference"),
            (response.evaluator_artifact_reference, "evaluator artifact reference"),
        ):
            if value is not None:
                _safe_reference(value, label)


def response_fingerprint(response: CaseExecutionResponse) -> Fingerprint:
    return fingerprint(
        {
            "logical_execution_reference": response.logical_execution_reference,
            "attempt_reference": response.attempt_reference,
            "status": response.status,
            "output_asset_reference": response.output_asset_reference,
            "result_checksum": response.result_checksum,
            "evaluator_artifact_reference": response.evaluator_artifact_reference,
            "usage_summary": response.usage_summary,
            "started_at": response.started_at,
            "finished_at": response.finished_at,
            "provider_execution_reference": response.provider_execution_reference,
            "provenance_reference": response.provenance_reference,
            "reason_codes": tuple(sorted(response.reason_codes, key=lambda item: item.value)),
        }
    )


def validate_request_against_manifest(
    request: CaseExecutionRequest,
    manifest: EvalRunManifest,
    case: EvalCaseVersion,
    expected_run_id: EvalRunId,
) -> None:
    if request.logical_execution.run_id != expected_run_id:
        raise ExecutionIdentityMismatch("request run identity is inconsistent")
    if request.manifest_id != manifest.manifest_id:
        raise ExecutionIdentityMismatch("request manifest identity is inconsistent")
    if request.manifest_fingerprint != manifest.run_fingerprint:
        raise ExecutionIdentityMismatch("request manifest fingerprint is inconsistent")
    if (request.suite_id, request.suite_version) != (manifest.suite_id, manifest.suite_version):
        raise ExecutionIdentityMismatch("request suite identity is inconsistent")
    if request.logical_execution.case_reference != case.reference:
        raise ExecutionIdentityMismatch("request case identity is inconsistent")
    if case.reference not in manifest.case_references:
        raise ExecutionIdentityMismatch("request case is absent from manifest")
    if request.dataset_binding != manifest.dataset_binding:
        raise ExecutionIdentityMismatch("request dataset binding is inconsistent")
    if request.expected_evaluator != manifest.evaluator or request.expected_evaluator != case.evaluator:
        raise ExecutionIdentityMismatch("request evaluator identity is inconsistent")
    if request.execution_protocol != manifest.execution:
        raise ExecutionIdentityMismatch("request execution protocol is inconsistent")
    if request.operating_profile != manifest.security.operating_profile:
        raise ExecutionIdentityMismatch("request operating profile is inconsistent")
    if request.security_snapshot_fingerprint != fingerprint(manifest.security):
        raise ExecutionIdentityMismatch("request security snapshot is inconsistent")
    expected_model = fingerprint(manifest.model_provider) if manifest.model_provider else None
    if request.model_provider_snapshot_fingerprint != expected_model:
        raise ExecutionIdentityMismatch("request model snapshot is inconsistent")
    manifest_skills = tuple(item for item in manifest.component_references if item.kind.value == "skill")
    manifest_tools = tuple(item for item in manifest.component_references if item.kind.value == "tool")
    if set(request.skill_references) != set(manifest_skills):
        raise ExecutionIdentityMismatch("request Skill references are inconsistent")
    if set(request.tool_references) != set(manifest_tools):
        raise ExecutionIdentityMismatch("request Tool references are inconsistent")
    if request.logical_execution.repetition > manifest.execution.repetitions:
        raise ExecutionRequestInvalid("request repetition exceeds execution protocol")
    expected_seed = manifest.execution.seeds[request.logical_execution.repetition - 1]
    if request.seed != expected_seed:
        raise ExecutionIdentityMismatch("request seed is inconsistent")


def validate_execution_response(
    request: CaseExecutionRequest,
    response: CaseExecutionResponse,
) -> None:
    _validate_response_fields(response)
    if response.logical_execution_reference != request.logical_execution.fingerprint:
        raise ExecutionResponseMismatch("response identifies another logical execution")
    if response.attempt_reference != request.attempt_identity.fingerprint:
        raise ExecutionResponseMismatch("response identifies another execution attempt")
    if not response.provenance_reference:
        raise ExecutionProvenanceMissing("execution response requires provenance")
    if response.fingerprint != response_fingerprint(response):
        raise ResponseFingerprintMismatch("execution response fingerprint is inconsistent")


def request_replay(
    existing: CaseExecutionRequest,
    candidate: CaseExecutionRequest,
) -> ReplayDisposition:
    if existing.idempotency_key.value != candidate.idempotency_key.value:
        return ReplayDisposition.NEW
    if existing.fingerprint != candidate.fingerprint:
        raise RequestIdempotencyConflict("idempotency key identifies different request content")
    return ReplayDisposition.SAFE_REPLAY


def response_replay(
    existing: CaseExecutionResponse,
    candidate: CaseExecutionResponse,
) -> ReplayDisposition:
    if existing.attempt_reference != candidate.attempt_reference:
        return ReplayDisposition.NEW
    if existing.fingerprint != candidate.fingerprint:
        raise ResponseIntegrityConflict("attempt identity identifies different response content")
    return ReplayDisposition.SAFE_REPLAY
