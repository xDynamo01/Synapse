from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from synapse.intelligence_boundary.models import OperatingProfile, ProcessingBoundary

from .catalog import DatasetBindingRef, EvalCaseVersionRef, EvaluatorIdentity
from .errors import (
    DuplicateReference,
    InvalidResult,
    InvalidRun,
    InvalidRunManifest,
    InvalidScore,
    SensitivePayloadViolation,
)
from .states import DeterminismMode, ResultStatus, RunStatus, ScoreKind, ScoreStatus, Verdict
from .values import (
    ContentChecksum,
    EvalResultId,
    EvalRunId,
    EvalRunManifestId,
    EvalSuiteId,
    EvalVersion,
    Fingerprint,
    Revision,
    UtcTimestamp,
)

_OPAQUE_REFERENCE_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*://\S+$")
_SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(?:api[_-]?key|authorization|password|private[_-]?key|secret|token)\s*[:=]"
)


def _require_text(value: str, field_name: str, error_type: type[ValueError]) -> None:
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{field_name} must be non-empty")


def _require_type(
    value: object,
    expected: type | tuple[type, ...],
    field_name: str,
    error_type: type[ValueError],
) -> None:
    if not isinstance(value, expected):
        raise error_type(f"{field_name} has an invalid type")


def _unique(values: tuple[object, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise DuplicateReference(f"duplicate {label} reference")


class ComponentKind(StrEnum):
    SKILL = "skill"
    TOOL = "tool"


@dataclass(frozen=True)
class VersionedComponentRef:
    kind: ComponentKind
    component_id: str
    version: str
    checksum: ContentChecksum

    def __post_init__(self) -> None:
        _require_type(self.kind, ComponentKind, "component kind", InvalidRunManifest)
        _require_type(self.checksum, ContentChecksum, "component checksum", InvalidRunManifest)
        _require_text(self.component_id, "component_id", InvalidRunManifest)
        _require_text(self.version, "component version", InvalidRunManifest)


@dataclass(frozen=True)
class DecodingParameters:
    temperature: Decimal
    top_p: Decimal
    max_output_tokens: int
    seed: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.temperature, Decimal) or not isinstance(self.top_p, Decimal):
            raise InvalidRunManifest("decoding parameters must be Decimal values")
        if not self.temperature.is_finite() or self.temperature < 0:
            raise InvalidRunManifest("temperature must be finite and non-negative")
        if not self.top_p.is_finite() or not Decimal("0") < self.top_p <= Decimal("1"):
            raise InvalidRunManifest("top_p must be in (0, 1]")
        if (
            isinstance(self.max_output_tokens, bool)
            or not isinstance(self.max_output_tokens, int)
            or self.max_output_tokens < 1
        ):
            raise InvalidRunManifest("max_output_tokens must be positive")
        if self.seed is not None and (
            isinstance(self.seed, bool) or not isinstance(self.seed, int)
        ):
            raise InvalidRunManifest("seed must be an integer or null")


@dataclass(frozen=True)
class ModelProviderSnapshot:
    provider_id: str
    processing_boundary: ProcessingBoundary
    model_id: str
    model_version: str
    configuration_checksum: ContentChecksum
    decoding: DecodingParameters
    credential_binding_id: str | None = None
    credential_binding_version: str | None = None

    def __post_init__(self) -> None:
        _require_type(
            self.processing_boundary,
            ProcessingBoundary,
            "processing boundary",
            InvalidRunManifest,
        )
        _require_type(
            self.configuration_checksum,
            ContentChecksum,
            "model configuration checksum",
            InvalidRunManifest,
        )
        _require_type(self.decoding, DecodingParameters, "decoding parameters", InvalidRunManifest)
        for value, name in (
            (self.provider_id, "provider_id"),
            (self.model_id, "model_id"),
            (self.model_version, "model_version"),
        ):
            _require_text(value, name, InvalidRunManifest)
        if (self.credential_binding_id is None) != (self.credential_binding_version is None):
            raise InvalidRunManifest(
                "credential binding identity and version must be provided together"
            )
        if self.credential_binding_id is not None:
            _require_text(self.credential_binding_id, "credential binding ID", InvalidRunManifest)
            _require_text(
                self.credential_binding_version or "",
                "credential binding version",
                InvalidRunManifest,
            )


@dataclass(frozen=True)
class SecuritySnapshotRef:
    operating_profile: OperatingProfile
    policy_references: tuple[str, ...]
    policy_checksums: tuple[ContentChecksum, ...]
    approval_manifest_references: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_type(
            self.operating_profile,
            OperatingProfile,
            "operating_profile",
            InvalidRunManifest,
        )
        if not self.policy_references:
            raise InvalidRunManifest("security snapshot requires a policy reference")
        if len(self.policy_references) != len(self.policy_checksums):
            raise InvalidRunManifest("security policy references and checksums must align")
        _unique(self.policy_references, "security policy")
        _unique(self.approval_manifest_references, "approval manifest")
        if any(not isinstance(value, ContentChecksum) for value in self.policy_checksums):
            raise InvalidRunManifest("security policy checksums must be typed")


@dataclass(frozen=True)
class ExecutionProtocol:
    determinism_mode: DeterminismMode
    repetitions: int
    concurrency: int
    retry_count: int
    logical_timeout_seconds: Decimal
    call_timeout_seconds: Decimal
    seeds: tuple[int, ...]
    aggregation_protocol: str

    def __post_init__(self) -> None:
        _require_type(
            self.determinism_mode,
            DeterminismMode,
            "determinism mode",
            InvalidRunManifest,
        )
        if not isinstance(self.logical_timeout_seconds, Decimal) or not isinstance(
            self.call_timeout_seconds, Decimal
        ):
            raise InvalidRunManifest("timeouts must be Decimal values")
        if isinstance(self.repetitions, bool) or self.repetitions < 1:
            raise InvalidRunManifest("repetitions must be positive")
        if isinstance(self.concurrency, bool) or self.concurrency < 1:
            raise InvalidRunManifest("concurrency must be positive")
        if isinstance(self.retry_count, bool) or self.retry_count < 0:
            raise InvalidRunManifest("retry count cannot be negative")
        for timeout in (self.logical_timeout_seconds, self.call_timeout_seconds):
            if not timeout.is_finite() or timeout <= 0:
                raise InvalidRunManifest("timeouts must be finite and positive")
        if any(isinstance(seed, bool) or not isinstance(seed, int) for seed in self.seeds):
            raise InvalidRunManifest("seeds must be integers")
        _unique(self.seeds, "seed")
        _require_text(self.aggregation_protocol, "aggregation protocol", InvalidRunManifest)
        if self.determinism_mode is DeterminismMode.DETERMINISTIC:
            if len(self.seeds) != self.repetitions:
                raise InvalidRunManifest(
                    "deterministic runs require one declared seed per repetition"
                )
        elif not self.seeds:
            raise InvalidRunManifest("stochastic runs must declare nondeterminism seeds")


@dataclass(frozen=True)
class EnvironmentSnapshot:
    operating_system: str
    architecture: str
    python_version: str
    runtime_version: str
    capability_versions: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for value, name in (
            (self.operating_system, "operating_system"),
            (self.architecture, "architecture"),
            (self.python_version, "python_version"),
            (self.runtime_version, "runtime_version"),
        ):
            _require_text(value, name, InvalidRunManifest)
        keys = tuple(key for key, _ in self.capability_versions)
        _unique(keys, "environment capability")
        for key, value in self.capability_versions:
            _require_text(key, "capability name", InvalidRunManifest)
            _require_text(value, "capability version", InvalidRunManifest)
            if key.casefold() in {"hostname", "username", "absolute_path", "process_inventory"}:
                raise SensitivePayloadViolation("environment snapshot contains a forbidden field")


@dataclass(frozen=True)
class RunProvenance:
    creator_id: str
    project_id: str
    source_fingerprint_authority: str
    governance_binding_reference: str | None = None
    prior_manifest_references: tuple[EvalRunManifestId, ...] = ()

    def __post_init__(self) -> None:
        for value, name in (
            (self.creator_id, "creator_id"),
            (self.project_id, "project_id"),
            (self.source_fingerprint_authority, "source fingerprint authority"),
        ):
            _require_text(value, name, InvalidRunManifest)
        _unique(self.prior_manifest_references, "prior manifest")


@dataclass(frozen=True)
class EvalRunManifest:
    manifest_id: EvalRunManifestId
    suite_id: EvalSuiteId
    suite_version: EvalVersion
    suite_checksum: ContentChecksum
    case_references: tuple[EvalCaseVersionRef, ...]
    dataset_binding: DatasetBindingRef
    evaluator: EvaluatorIdentity
    subject_kind: str
    source_fingerprint: Fingerprint
    model_provider: ModelProviderSnapshot | None
    component_references: tuple[VersionedComponentRef, ...]
    security: SecuritySnapshotRef
    execution: ExecutionProtocol
    environment: EnvironmentSnapshot
    provenance: RunProvenance
    protocol_fingerprint: Fingerprint
    subject_fingerprint: Fingerprint
    run_fingerprint: Fingerprint
    environment_fingerprint: Fingerprint
    checksum: ContentChecksum

    def __post_init__(self) -> None:
        for value, expected, name in (
            (self.manifest_id, EvalRunManifestId, "manifest_id"),
            (self.suite_id, EvalSuiteId, "suite_id"),
            (self.suite_version, EvalVersion, "suite version"),
            (self.suite_checksum, ContentChecksum, "suite checksum"),
            (self.dataset_binding, DatasetBindingRef, "dataset binding"),
            (self.evaluator, EvaluatorIdentity, "evaluator"),
            (self.source_fingerprint, Fingerprint, "source fingerprint"),
            (self.security, SecuritySnapshotRef, "security snapshot"),
            (self.execution, ExecutionProtocol, "execution protocol"),
            (self.environment, EnvironmentSnapshot, "environment snapshot"),
            (self.provenance, RunProvenance, "provenance"),
            (self.protocol_fingerprint, Fingerprint, "protocol fingerprint"),
            (self.subject_fingerprint, Fingerprint, "subject fingerprint"),
            (self.run_fingerprint, Fingerprint, "run fingerprint"),
            (self.environment_fingerprint, Fingerprint, "environment fingerprint"),
            (self.checksum, ContentChecksum, "manifest checksum"),
        ):
            _require_type(value, expected, name, InvalidRunManifest)
        if any(not isinstance(reference, EvalCaseVersionRef) for reference in self.case_references):
            raise InvalidRunManifest("case references must be typed")
        if any(
            not isinstance(reference, VersionedComponentRef)
            for reference in self.component_references
        ):
            raise InvalidRunManifest("component references must be typed")
        if not self.case_references:
            raise InvalidRunManifest("run manifest requires versioned cases")
        if any(reference.suite_id != self.suite_id for reference in self.case_references):
            raise InvalidRunManifest("run manifest contains a case from another suite")
        _unique(self.case_references, "manifest case")
        _unique(self.component_references, "component")
        _require_text(self.subject_kind, "subject_kind", InvalidRunManifest)
        model_subjects = {"model", "provider_model", "model_provider"}
        if self.subject_kind.casefold() in model_subjects and self.model_provider is None:
            raise InvalidRunManifest("model subject requires a model/provider snapshot")
        if self.run_fingerprint in {
            self.protocol_fingerprint,
            self.subject_fingerprint,
            self.environment_fingerprint,
        }:
            raise InvalidRunManifest("run fingerprint must identify the composed run state")


@dataclass(frozen=True)
class EvalRun:
    run_id: EvalRunId
    suite_id: EvalSuiteId
    suite_version: EvalVersion
    status: RunStatus
    revision: Revision
    created_at: UtcTimestamp
    updated_at: UtcTimestamp
    manifest_id: EvalRunManifestId | None = None
    accepted_result_count: int = 0
    failed_execution_count: int = 0
    finalization_reference: str | None = None

    def __post_init__(self) -> None:
        for value, expected, name in (
            (self.run_id, EvalRunId, "run_id"),
            (self.suite_id, EvalSuiteId, "suite_id"),
            (self.suite_version, EvalVersion, "suite version"),
            (self.status, RunStatus, "run status"),
            (self.revision, Revision, "run revision"),
            (self.created_at, UtcTimestamp, "created_at"),
            (self.updated_at, UtcTimestamp, "updated_at"),
        ):
            _require_type(value, expected, name, InvalidRun)
        if self.manifest_id is not None:
            _require_type(self.manifest_id, EvalRunManifestId, "manifest_id", InvalidRun)
        if self.updated_at.instant < self.created_at.instant:
            raise InvalidRun("updated_at cannot precede created_at")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in (self.accepted_result_count, self.failed_execution_count)
        ):
            raise InvalidRun("run counters cannot be negative")
        if self.status in {
            RunStatus.READY,
            RunStatus.RUNNING,
            RunStatus.PARTIALLY_FAILED,
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        } and self.manifest_id is None:
            raise InvalidRun("prepared or terminal run requires a manifest reference")
        terminal = {
            RunStatus.PARTIALLY_FAILED,
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.INVALID,
            RunStatus.POLICY_DENIED,
        }
        if self.status in terminal and not self.finalization_reference:
            raise InvalidRun("terminal run requires a finalization reference")


@dataclass(frozen=True)
class Score:
    metric_id: str
    evaluator: EvaluatorIdentity
    kind: ScoreKind
    status: ScoreStatus
    raw_value: Decimal | None
    scale_minimum: Decimal
    scale_maximum: Decimal
    normalized_value: Decimal | None
    weight: Decimal
    sample_count: int
    confidence: Decimal | None
    variance: Decimal | None
    confidence_method: str | None
    critical: bool
    required: bool
    reason_code: str | None
    checksum: ContentChecksum

    def __post_init__(self) -> None:
        _require_type(self.evaluator, EvaluatorIdentity, "evaluator", InvalidScore)
        _require_type(self.kind, ScoreKind, "score kind", InvalidScore)
        _require_type(self.status, ScoreStatus, "score status", InvalidScore)
        _require_type(self.checksum, ContentChecksum, "score checksum", InvalidScore)
        decimal_values = (
            self.raw_value,
            self.scale_minimum,
            self.scale_maximum,
            self.normalized_value,
            self.weight,
            self.confidence,
            self.variance,
        )
        if any(value is not None and not isinstance(value, Decimal) for value in decimal_values):
            raise InvalidScore("score numeric values must be Decimal values")
        _require_text(self.metric_id, "metric_id", InvalidScore)
        numbers = (self.scale_minimum, self.scale_maximum, self.weight)
        if any(not number.is_finite() for number in numbers):
            raise InvalidScore("score scale and weight must be finite")
        if self.scale_minimum >= self.scale_maximum:
            raise InvalidScore("score scale minimum must be below maximum")
        if self.weight <= 0:
            raise InvalidScore("score weight must be greater than zero")
        if isinstance(self.sample_count, bool) or self.sample_count < 0:
            raise InvalidScore("sample_count cannot be negative")
        if self.confidence is not None and (
            not self.confidence.is_finite() or not Decimal("0") <= self.confidence <= Decimal("1")
        ):
            raise InvalidScore("confidence must be in [0, 1]")
        if self.variance is not None and (
            not self.variance.is_finite() or self.variance < 0
        ):
            raise InvalidScore("variance must be finite and non-negative")
        if (self.confidence is None) != (self.confidence_method is None):
            raise InvalidScore("confidence and its method must be provided together")
        if self.critical and not self.required:
            raise InvalidScore("critical score must also be required")
        if self.status is ScoreStatus.VALID:
            if self.raw_value is None or self.normalized_value is None or self.sample_count < 1:
                raise InvalidScore("valid score requires values and at least one sample")
            if not self.raw_value.is_finite():
                raise InvalidScore("raw score must be finite")
            if not self.scale_minimum <= self.raw_value <= self.scale_maximum:
                raise InvalidScore("raw score is outside its scale")
            if not self.normalized_value.is_finite() or not (
                Decimal("0") <= self.normalized_value <= Decimal("1")
            ):
                raise InvalidScore("normalized score must be in [0, 1]")
            if self.reason_code is not None:
                raise InvalidScore("valid score cannot carry an invalidity reason")
            if self.kind is ScoreKind.BINARY and (
                self.scale_minimum != 0
                or self.scale_maximum != 1
                or self.raw_value not in {Decimal("0"), Decimal("1")}
                or self.normalized_value != self.raw_value
            ):
                raise InvalidScore("binary score must use canonical 0..1 values")
            expected_normalized = (self.raw_value - self.scale_minimum) / (
                self.scale_maximum - self.scale_minimum
            )
            if self.normalized_value != expected_normalized:
                raise InvalidScore("normalized score does not match its scale")
        else:
            if self.normalized_value is not None:
                raise InvalidScore("invalid or missing score cannot be normalized")
            _require_text(self.reason_code or "", "score reason_code", InvalidScore)


@dataclass(frozen=True)
class ResourceUsage:
    duration_ms: int
    cpu_ms: int = 0
    peak_memory_bytes: int = 0
    input_units: int = 0
    output_units: int = 0

    def __post_init__(self) -> None:
        values = (
            self.duration_ms,
            self.cpu_ms,
            self.peak_memory_bytes,
            self.input_units,
            self.output_units,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in values
        ):
            raise InvalidResult("resource usage cannot be negative")


@dataclass(frozen=True)
class EvalResult:
    result_id: EvalResultId
    run_id: EvalRunId
    case_reference: EvalCaseVersionRef
    repetition: int
    execution_record_reference: str
    status: ResultStatus
    output_asset_id: str | None
    output_reference: str | None = field(repr=False)
    output_checksum: ContentChecksum | None
    safe_summary: str
    scores: tuple[Score, ...]
    verdict: Verdict
    error_code: str | None
    resource_usage: ResourceUsage
    evaluator_artifact_reference: str | None
    provenance_reference: str | None
    result_fingerprint: Fingerprint
    producer_id: str
    producer_version: str
    created_at: UtcTimestamp
    checksum: ContentChecksum

    def __post_init__(self) -> None:
        for value, expected, name in (
            (self.result_id, EvalResultId, "result_id"),
            (self.run_id, EvalRunId, "run_id"),
            (self.case_reference, EvalCaseVersionRef, "case reference"),
            (self.status, ResultStatus, "result status"),
            (self.resource_usage, ResourceUsage, "resource usage"),
            (self.result_fingerprint, Fingerprint, "result fingerprint"),
            (self.created_at, UtcTimestamp, "result created_at"),
            (self.checksum, ContentChecksum, "result checksum"),
        ):
            _require_type(value, expected, name, InvalidResult)
        _require_type(self.verdict, Verdict, "verdict", InvalidResult)
        if self.output_checksum is not None:
            _require_type(self.output_checksum, ContentChecksum, "output checksum", InvalidResult)
        if any(not isinstance(value, Score) for value in self.scores):
            raise InvalidResult("result scores must be typed")
        if isinstance(self.repetition, bool) or self.repetition < 1:
            raise InvalidResult("result repetition must be positive")
        _require_text(
            self.execution_record_reference,
            "execution record reference",
            InvalidResult,
        )
        metric_ids = tuple(score.metric_id for score in self.scores)
        _unique(metric_ids, "result metric")
        if self.status is ResultStatus.VALID:
            for text_value, name in (
                (self.evaluator_artifact_reference or "", "evaluator artifact reference"),
                (self.provenance_reference or "", "provenance reference"),
                (self.producer_id, "result producer ID"),
                (self.producer_version, "result producer version"),
            ):
                _require_text(text_value, name, InvalidResult)
            if self.error_code is not None:
                raise InvalidResult("valid result cannot also contain an infrastructure error")
            if self.output_checksum is None:
                raise InvalidResult("valid result requires an output checksum")
            if self.output_reference is not None and self.output_asset_id is None:
                raise InvalidResult("output custody reference requires an output asset")
            if self.output_reference is not None and not _OPAQUE_REFERENCE_PATTERN.fullmatch(
                self.output_reference
            ):
                raise InvalidResult("output reference must be an opaque URI, not output payload")
            if self.verdict not in {
                Verdict.PASSED,
                Verdict.FAILED,
                Verdict.INCONCLUSIVE,
                Verdict.INVALID,
            }:
                raise InvalidResult("valid result has an incompatible verdict")
            if any(score.status is ScoreStatus.INVALID for score in self.scores) and self.verdict is not Verdict.INVALID:
                raise InvalidResult("invalid score requires an invalid case verdict")
            if any(score.status is ScoreStatus.MISSING and score.required for score in self.scores) and self.verdict is not Verdict.INCONCLUSIVE:
                raise InvalidResult("missing required score requires an inconclusive case verdict")
        else:
            if self.evaluator_artifact_reference is not None or self.provenance_reference is not None:
                raise InvalidResult("non-valid result cannot contain final evaluator references")
            if self.output_reference is not None or self.output_asset_id is not None:
                raise InvalidResult("non-valid result cannot expose an output reference")
            if self.scores:
                raise InvalidResult("non-valid result cannot contain accepted scores")
            expected_verdict = {
                ResultStatus.INFRASTRUCTURE_FAILED: Verdict.INCONCLUSIVE,
                ResultStatus.INVALID: Verdict.INVALID,
                ResultStatus.POLICY_DENIED: Verdict.POLICY_DENIED,
                ResultStatus.CANCELLED: Verdict.INCONCLUSIVE,
            }[self.status]
            if self.verdict is not expected_verdict:
                raise InvalidResult("result status and verdict are contradictory")
            _require_text(self.error_code or "", "error_code", InvalidResult)
        if self.verdict in {Verdict.BLOCKED, Verdict.POLICY_DENIED} and self.status is ResultStatus.VALID:
            raise InvalidResult("blocked or policy-denied verdict is not a successful measurement")
        if len(self.safe_summary) > 1024:
            raise InvalidResult("safe summary exceeds the bounded metadata limit")
        if _SENSITIVE_ASSIGNMENT_PATTERN.search(self.safe_summary):
            raise SensitivePayloadViolation("safe summary appears to contain sensitive material")
