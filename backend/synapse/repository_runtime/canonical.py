"""Versioned canonical encoding for Repository Runtime semantic facts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Callable, Protocol, cast

from .errors import RepositoryCanonicalizationError, UnsupportedRepositoryFormat

CANONICAL_FORMAT = "repository-json-v1"


class CanonicalValue(Protocol):
    def canonical_value(self) -> object: ...


def _normalize(value: object) -> object:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Enum):
        return _normalize(value.value)
    if hasattr(value, "canonical_value"):
        method = cast(Callable[[], object], getattr(value, "canonical_value"))
        return _normalize(method())
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _normalize(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise RepositoryCanonicalizationError("canonical mappings require string keys")
        return {key: _normalize(value[key]) for key in sorted(value)}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize(item) for item in value]
    raise RepositoryCanonicalizationError("value is not canonically encodable")


def canonical_bytes(value: object, *, format_version: str = CANONICAL_FORMAT) -> bytes:
    if format_version != CANONICAL_FORMAT:
        raise UnsupportedRepositoryFormat("unsupported canonical format")
    envelope = {"format": format_version, "value": _normalize(value)}
    try:
        return json.dumps(
            envelope, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True
        ).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise RepositoryCanonicalizationError("canonical encoding failed") from exc


def content_fingerprint(value: object, *, format_version: str = CANONICAL_FORMAT) -> str:
    digest = hashlib.sha256(canonical_bytes(value, format_version=format_version)).hexdigest()
    return f"sha256:{digest}"
