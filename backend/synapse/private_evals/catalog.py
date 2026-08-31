from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from synapse.intelligence_boundary.models import DataClassification, InformationOwnership

from .errors import (
    DuplicateReference,
    IncompatibleReference,
    InvalidCase,
    InvalidDatasetBinding,
    InvalidSuite,
    SensitivePayloadViolation,
)
from .states import (
    DatasetCustodyKind,
    DefinitionStatus,
    InputKind,
    SideEffectPolicy,
    SuiteStatus,
)
from .values import (
    ContentChecksum,
    DatasetBindingId,
    EvalCaseId,
    EvalSuiteId,
    EvaluatorId,
    EvalVersion,
    Fingerprint,
    Revision,
    UtcTimestamp,
)

_INLINE_CLASSIFICATIONS = {DataClassification.PUBLIC}
_OPAQUE_REFERENCE_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*://\S+$")


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


@dataclass(frozen=True)
class EvaluatorIdentity:
    evaluator_id: EvaluatorId
    version: EvalVersion
    implementation_checksum: ContentChecksum
    kind: str
    configuration_checksum: ContentChecksum

    def __post_init__(self) -> None:
        _require_type(self.evaluator_id, EvaluatorId, "evaluator_id", InvalidCase)
        _require_type(self.version, EvalVersion, "evaluator version", InvalidCase)
        _require_type(
            self.implementation_checksum,
            ContentChecksum,
            "implementation checksum",
            InvalidCase,
        )
        _require_type(
            self.configuration_checksum,
            ContentChecksum,
            "configuration checksum",
            InvalidCase,
        )
        _require_text(self.kind, "evaluator kind", InvalidCase)


@dataclass(frozen=True)
class EvalCaseVersionRef:
    suite_id: EvalSuiteId
    case_id: EvalCaseId
    version: EvalVersion
    checksum: ContentChecksum

    def __post_init__(self) -> None:
        _require_type(self.suite_id, EvalSuiteId, "suite_id", IncompatibleReference)
        _require_type(self.case_id, EvalCaseId, "case_id", IncompatibleReference)
        _require_type(self.version, EvalVersion, "case version", IncompatibleReference)
        _require_type(self.checksum, ContentChecksum, "case checksum", IncompatibleReference)


@dataclass(frozen=True)
class DatasetBindingRef:
    binding_id: DatasetBindingId
    revision: Revision
    checksum: ContentChecksum

    def __post_init__(self) -> None:
        _require_type(
            self.binding_id,
            DatasetBindingId,
            "binding_id",
            InvalidDatasetBinding,
        )
        _require_type(self.revision, Revision, "dataset revision", InvalidDatasetBinding)
        _require_type(self.checksum, ContentChecksum, "dataset checksum", InvalidDatasetBinding)


@dataclass(frozen=True)
class ContentBinding:
    kind: InputKind
    classification: DataClassification
    inline_value: str | None = field(default=None, repr=False)
    asset_id: str | None = None
    item_reference: str | None = field(default=None, repr=False)
    checksum: ContentChecksum | None = None

    def __post_init__(self) -> None:
        _require_type(self.kind, InputKind, "input kind", InvalidCase)
        _require_type(self.classification, DataClassification, "classification", InvalidCase)
        if self.kind is InputKind.INLINE:
            if not isinstance(self.inline_value, str) or not self.inline_value:
                raise InvalidCase("inline content must be non-empty")
            if self.classification not in _INLINE_CLASSIFICATIONS:
                raise SensitivePayloadViolation(
                    "non-public case content must use a governed reference until policy approval"
                )
            if self.asset_id is not None or self.item_reference is not None:
                raise InvalidCase("inline content cannot also contain a governed reference")
            return
        if self.inline_value is not None:
            raise SensitivePayloadViolation("referenced content cannot contain an inline payload")
        _require_text(self.asset_id or "", "asset_id", InvalidCase)
        _require_text(self.item_reference or "", "item_reference", InvalidCase)
        if not _OPAQUE_REFERENCE_PATTERN.fullmatch(self.item_reference or ""):
            raise InvalidCase("item_reference must be an opaque URI, not inline content")
        if self.checksum is None:
            raise InvalidCase("referenced content requires a checksum")
        _require_type(self.checksum, ContentChecksum, "content checksum", InvalidCase)


@dataclass(frozen=True)
class EvalSuite:
    suite_id: EvalSuiteId
    name: str
    description: str
    owner: InformationOwnership
    project_id: str
    classification: DataClassification
    status: SuiteStatus
    revision: Revision
    created_at: UtcTimestamp
    updated_at: UtcTimestamp
    default_regression_rule_id: str | None = None

    def __post_init__(self) -> None:
        _require_type(self.suite_id, EvalSuiteId, "suite_id", InvalidSuite)
        _require_type(self.owner, InformationOwnership, "suite owner", InvalidSuite)
        _require_type(self.classification, DataClassification, "classification", InvalidSuite)
        _require_type(self.status, SuiteStatus, "suite status", InvalidSuite)
        _require_type(self.revision, Revision, "suite revision", InvalidSuite)
        _require_type(self.created_at, UtcTimestamp, "created_at", InvalidSuite)
        _require_type(self.updated_at, UtcTimestamp, "updated_at", InvalidSuite)
        _require_text(self.name, "suite name", InvalidSuite)
        _require_text(self.owner.value, "suite owner", InvalidSuite)
        _require_text(self.project_id, "project_id", InvalidSuite)
        if self.updated_at.instant < self.created_at.instant:
            raise InvalidSuite("updated_at cannot precede created_at")
        if self.default_regression_rule_id is not None:
            _require_text(
                self.default_regression_rule_id,
                "default_regression_rule_id",
                InvalidSuite,
            )


@dataclass(frozen=True)
class EvalSuiteVersion:
    suite_id: EvalSuiteId
    version: EvalVersion
    case_references: tuple[EvalCaseVersionRef, ...]
    dataset_references: tuple[DatasetBindingRef, ...]
    scoring_protocol_version: EvalVersion
    default_repetitions: int
    default_concurrency: int
    default_timeout_seconds: Decimal
    default_retry_count: int
    compatible_versions: tuple[EvalVersion, ...]
    required_case_ids: tuple[EvalCaseId, ...]
    classification: DataClassification
    owner: InformationOwnership
    status: DefinitionStatus
    checksum: ContentChecksum

    def __post_init__(self) -> None:
        _require_type(self.suite_id, EvalSuiteId, "suite_id", InvalidSuite)
        _require_type(self.version, EvalVersion, "suite version", InvalidSuite)
        _require_type(
            self.scoring_protocol_version,
            EvalVersion,
            "scoring protocol version",
            InvalidSuite,
        )
        _require_type(self.classification, DataClassification, "classification", InvalidSuite)
        _require_type(self.owner, InformationOwnership, "suite owner", InvalidSuite)
        _require_type(self.status, DefinitionStatus, "suite version status", InvalidSuite)
        _require_type(self.checksum, ContentChecksum, "suite version checksum", InvalidSuite)
        if any(not isinstance(reference, EvalCaseVersionRef) for reference in self.case_references):
            raise InvalidSuite("case references must be typed")
        if any(not isinstance(reference, DatasetBindingRef) for reference in self.dataset_references):
            raise InvalidSuite("dataset references must be typed")
        if any(not isinstance(value, EvalVersion) for value in self.compatible_versions):
            raise InvalidSuite("compatible versions must be typed")
        if any(not isinstance(value, EvalCaseId) for value in self.required_case_ids):
            raise InvalidSuite("required case IDs must be typed")
        if not isinstance(self.default_timeout_seconds, Decimal):
            raise InvalidSuite("default timeout must be a Decimal")
        if not self.case_references:
            raise InvalidSuite("suite version requires at least one case")
        if any(reference.suite_id != self.suite_id for reference in self.case_references):
            raise IncompatibleReference("case reference belongs to another suite")
        _unique(self.case_references, "case version")
        _unique(self.dataset_references, "dataset binding")
        _unique(self.compatible_versions, "compatible version")
        _unique(self.required_case_ids, "required case")
        available = {reference.case_id for reference in self.case_references}
        if not set(self.required_case_ids) <= available:
            raise IncompatibleReference("required case is absent from suite version")
        if self.version in self.compatible_versions:
            raise InvalidSuite("suite version cannot list itself as a compatibility target")
        if isinstance(self.default_repetitions, bool) or self.default_repetitions < 1:
            raise InvalidSuite("default repetitions must be positive")
        if isinstance(self.default_concurrency, bool) or self.default_concurrency < 1:
            raise InvalidSuite("default concurrency must be positive")
        if self.default_timeout_seconds <= 0 or not self.default_timeout_seconds.is_finite():
            raise InvalidSuite("default timeout must be finite and positive")
        if isinstance(self.default_retry_count, bool) or self.default_retry_count < 0:
            raise InvalidSuite("default retry count cannot be negative")


@dataclass(frozen=True)
class EvalCaseVersion:
    suite_id: EvalSuiteId
    case_id: EvalCaseId
    version: EvalVersion
    input: ContentBinding
    expected_outcome: ContentBinding
    evaluator: EvaluatorIdentity
    weight: Decimal
    tags: tuple[str, ...]
    owner: InformationOwnership
    classification: DataClassification
    timeout_seconds: Decimal | None
    side_effect_policy: SideEffectPolicy
    required: bool
    critical: bool
    status: DefinitionStatus
    checksum: ContentChecksum

    def __post_init__(self) -> None:
        _require_type(self.suite_id, EvalSuiteId, "suite_id", InvalidCase)
        _require_type(self.case_id, EvalCaseId, "case_id", InvalidCase)
        _require_type(self.version, EvalVersion, "case version", InvalidCase)
        _require_type(self.input, ContentBinding, "case input", InvalidCase)
        _require_type(self.expected_outcome, ContentBinding, "expected outcome", InvalidCase)
        _require_type(self.evaluator, EvaluatorIdentity, "evaluator", InvalidCase)
        _require_type(self.owner, InformationOwnership, "case owner", InvalidCase)
        _require_type(self.classification, DataClassification, "classification", InvalidCase)
        _require_type(
            self.side_effect_policy,
            SideEffectPolicy,
            "side effect policy",
            InvalidCase,
        )
        _require_type(self.status, DefinitionStatus, "case status", InvalidCase)
        _require_type(self.checksum, ContentChecksum, "case checksum", InvalidCase)
        if not isinstance(self.weight, Decimal):
            raise InvalidCase("case weight must be a Decimal")
        if self.timeout_seconds is not None and not isinstance(self.timeout_seconds, Decimal):
            raise InvalidCase("case timeout must be a Decimal")
        if not self.weight.is_finite() or self.weight <= 0:
            raise InvalidCase("case weight must be finite and greater than zero")
        if self.timeout_seconds is not None and (
            not self.timeout_seconds.is_finite() or self.timeout_seconds <= 0
        ):
            raise InvalidCase("case timeout must be finite and greater than zero")
        normalized_tags = tuple(tag.strip().casefold() for tag in self.tags)
        if any(not tag for tag in normalized_tags):
            raise InvalidCase("case tags must be non-empty")
        if len(normalized_tags) != len(set(normalized_tags)):
            raise DuplicateReference("duplicate case tag")
        object.__setattr__(self, "tags", normalized_tags)
        if self.critical and not self.required:
            raise InvalidCase("critical case must also be required")
        if self.input.classification != self.classification:
            raise IncompatibleReference("case input classification must match the case")
        if self.expected_outcome.classification != self.classification:
            raise IncompatibleReference("expected outcome classification must match the case")

    @property
    def reference(self) -> EvalCaseVersionRef:
        return EvalCaseVersionRef(self.suite_id, self.case_id, self.version, self.checksum)


@dataclass(frozen=True)
class DatasetBinding:
    binding_id: DatasetBindingId
    asset_id: str
    content_reference: str = field(repr=False)
    dataset_revision: Revision
    content_checksum: ContentChecksum
    item_manifest_checksum: ContentChecksum
    item_count: int | None
    classification: DataClassification
    owner: InformationOwnership
    classification_snapshot_reference: str
    ownership_snapshot_reference: str
    retention_policy_reference: str
    selection_fingerprint: Fingerprint
    custody_kind: DatasetCustodyKind
    created_at: UtcTimestamp
    checksum: ContentChecksum

    def __post_init__(self) -> None:
        _require_type(self.binding_id, DatasetBindingId, "binding_id", InvalidDatasetBinding)
        _require_type(
            self.dataset_revision,
            Revision,
            "dataset revision",
            InvalidDatasetBinding,
        )
        _require_type(
            self.content_checksum,
            ContentChecksum,
            "content checksum",
            InvalidDatasetBinding,
        )
        _require_type(
            self.item_manifest_checksum,
            ContentChecksum,
            "item manifest checksum",
            InvalidDatasetBinding,
        )
        _require_type(
            self.classification,
            DataClassification,
            "classification",
            InvalidDatasetBinding,
        )
        _require_type(self.owner, InformationOwnership, "owner", InvalidDatasetBinding)
        _require_type(
            self.custody_kind,
            DatasetCustodyKind,
            "custody kind",
            InvalidDatasetBinding,
        )
        _require_type(
            self.selection_fingerprint,
            Fingerprint,
            "selection fingerprint",
            InvalidDatasetBinding,
        )
        _require_type(self.created_at, UtcTimestamp, "created_at", InvalidDatasetBinding)
        _require_type(self.checksum, ContentChecksum, "binding checksum", InvalidDatasetBinding)
        for value, name in (
            (self.asset_id, "asset_id"),
            (self.content_reference, "content_reference"),
            (self.classification_snapshot_reference, "classification snapshot"),
            (self.ownership_snapshot_reference, "ownership snapshot"),
            (self.retention_policy_reference, "retention policy"),
        ):
            _require_text(value, name, InvalidDatasetBinding)
        if not _OPAQUE_REFERENCE_PATTERN.fullmatch(self.content_reference):
            raise InvalidDatasetBinding(
                "content_reference must be an opaque URI, not dataset payload"
            )
        if self.item_count is not None and (
            isinstance(self.item_count, bool) or self.item_count < 0
        ):
            raise InvalidDatasetBinding("item_count cannot be negative")

    @property
    def reference(self) -> DatasetBindingRef:
        return DatasetBindingRef(self.binding_id, self.dataset_revision, self.checksum)
