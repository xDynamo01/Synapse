from __future__ import annotations

import re
from dataclasses import dataclass

from .catalog import EvalCaseVersionRef
from .result_errors import ResultMaterializationInvalid
from .runs import ResourceUsage
from .values import (
    ContentChecksum,
    EvalRunId,
    Fingerprint,
    MaterializedOutputId,
    UtcTimestamp,
)

_SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~:-]{0,255}$")
_SENSITIVE = re.compile(
    r"(?i)(?:token|secret|password|credential|authorization|bearer|api[_-]?key|sk-)"
)


def validate_safe_materialization_reference(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or not _SAFE_REFERENCE.fullmatch(value)
        or _SENSITIVE.search(value)
        or "/" in value
        or "\\" in value
        or "://" in value
    ):
        raise ResultMaterializationInvalid(f"{label} must be a safe opaque reference")


@dataclass(frozen=True)
class MaterializedOutputRecord:
    """Immutable execution output fact, deliberately independent of scoring."""

    output_id: MaterializedOutputId
    run_id: EvalRunId
    case_reference: EvalCaseVersionRef
    repetition: int
    logical_execution_fingerprint: Fingerprint
    execution_attempt_reference: Fingerprint
    output_asset_reference: str
    output_checksum: ContentChecksum
    evaluator_artifact_reference: str
    provenance_reference: str
    resource_usage: ResourceUsage
    producer_id: str
    producer_version: str
    created_at: UtcTimestamp
    materialization_fingerprint: Fingerprint
    checksum: ContentChecksum

    def __post_init__(self) -> None:
        typed = (
            (self.output_id, MaterializedOutputId),
            (self.run_id, EvalRunId),
            (self.case_reference, EvalCaseVersionRef),
            (self.logical_execution_fingerprint, Fingerprint),
            (self.execution_attempt_reference, Fingerprint),
            (self.output_checksum, ContentChecksum),
            (self.resource_usage, ResourceUsage),
            (self.created_at, UtcTimestamp),
            (self.materialization_fingerprint, Fingerprint),
            (self.checksum, ContentChecksum),
        )
        if any(not isinstance(value, expected) for value, expected in typed):
            raise ResultMaterializationInvalid()
        if (
            isinstance(self.repetition, bool)
            or not isinstance(self.repetition, int)
            or self.repetition < 1
        ):
            raise ResultMaterializationInvalid()
        for value, label in (
            (self.output_asset_reference, "output asset reference"),
            (self.evaluator_artifact_reference, "evaluator artifact reference"),
            (self.provenance_reference, "provenance reference"),
            (self.producer_id, "producer ID"),
            (self.producer_version, "producer version"),
        ):
            validate_safe_materialization_reference(value, label)

    def __repr__(self) -> str:
        return (
            "MaterializedOutputRecord("
            f"output_id={self.output_id!r}, run_id={self.run_id!r}, "
            f"case_reference={self.case_reference!r}, repetition={self.repetition!r}, "
            f"materialization_fingerprint={self.materialization_fingerprint!r})"
        )
