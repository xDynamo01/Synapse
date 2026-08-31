"""Canonical Deployment JSON V1 and deterministic semantic fingerprints."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from enum import Enum

DEPLOYMENT_CANONICAL_FORMAT_V1 = "deployment-json-v1"


def _canonical_value(value: object, *, path: str = "root") -> object:
    canonical_method = getattr(value, "canonical_value", None)
    if callable(canonical_method):
        return _canonical_value(canonical_method(), path=path)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _canonical_value(getattr(value, item.name), path=f"{path}.{item.name}")
            for item in fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} keys must be strings")
            normalized[key] = _canonical_value(item, path=f"{path}.{key}")
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_canonical_value(item, path=f"{path}[]") for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"{path} contains an unsupported canonical value")


def canonical_json(value: object) -> str:
    return json.dumps(
        _canonical_value(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )


def content_fingerprint(value: object) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
