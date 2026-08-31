from __future__ import annotations

import json
from dataclasses import fields
from enum import StrEnum

from synapse.skills.phase2_values import (
    SkillContentFingerprint,
    SkillId,
    SkillLogicalPath,
    SkillManifestFingerprint,
    SkillManifestFormatVersion,
    SkillPackageFingerprint,
    SkillRequirementId,
    SkillSchemaVersionRequirement,
    SkillSemanticReference,
    SkillVersion,
    SkillVersionConstraint,
)

_CANONICAL_TEXT_TYPES = (
    SkillContentFingerprint,
    SkillId,
    SkillLogicalPath,
    SkillManifestFingerprint,
    SkillPackageFingerprint,
    SkillRequirementId,
    SkillSchemaVersionRequirement,
    SkillSemanticReference,
    SkillVersion,
    SkillVersionConstraint,
)


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        domain_data(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_sort_key(value: object) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def domain_data(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, SkillManifestFormatVersion):
        return value.value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, _CANONICAL_TEXT_TYPES):
        return value.to_canonical_text()
    if isinstance(value, tuple):
        return tuple(domain_data(item) for item in value)
    if hasattr(value, "__dataclass_fields__"):
        return {
            field.name: domain_data(getattr(value, field.name))
            for field in fields(value)  # type: ignore[arg-type]
        }
    raise TypeError("unsupported canonical skill domain value")
