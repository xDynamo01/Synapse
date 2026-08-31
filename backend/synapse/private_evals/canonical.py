from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from .errors import SensitivePayloadViolation
from .values import ContentChecksum, Fingerprint

_FORBIDDEN_KEYS = {
    "api_key",
    "authorization",
    "credential",
    "credentials",
    "password",
    "private_key",
    "secret",
    "token",
}


def _is_sensitive_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    if normalized in {"credential_binding_id", "credential_binding_version"}:
        return False
    return any(
        part in _FORBIDDEN_KEYS
        or part.endswith(("_api_key", "_credential", "_credentials", "_password", "_secret", "_token"))
        for part in normalized.split(".")
    )


def _canonical_value(value: Any, *, path: str = "root") -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        normalized_dataclass = {}
        for item in fields(value):
            if _is_sensitive_key(item.name):
                raise SensitivePayloadViolation(
                    "canonical data contains a forbidden sensitive field"
                )
            normalized_dataclass[item.name] = _canonical_value(
                getattr(value, item.name), path=f"{path}.{item.name}"
            )
        return normalized_dataclass
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"{path} must be finite")
        if value.is_zero():
            return "0"
        return format(value.normalize(), "f")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must be finite")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} keys must be strings")
            if _is_sensitive_key(key):
                raise SensitivePayloadViolation("canonical data contains a forbidden sensitive key")
            normalized[key] = _canonical_value(item, path=f"{path}.{key}")
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_canonical_value(item, path=f"{path}[]") for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"{path} contains an unsupported canonical value")


def canonical_json(value: Any) -> str:
    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def content_checksum(value: Any) -> ContentChecksum:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return ContentChecksum(digest)


def fingerprint(value: Any) -> Fingerprint:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return Fingerprint(digest)
