"""Internal deterministic encoding for Coding Sessions semantic values."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Callable, cast

from .errors import CodingSessionCanonicalizationError, CodingSessionVersionMismatch

CANONICAL_FORMAT = "coding-sessions-json-v1"


def _normalized(value: object) -> object:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Enum):
        return _normalized(value.value)
    if hasattr(value, "canonical_value"):
        method = cast(Callable[[], object], getattr(value, "canonical_value"))
        return _normalized(method())
    if hasattr(value, "semantic_content"):
        method = cast(Callable[[], object], getattr(value, "semantic_content"))
        return _normalized(method())
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _normalized(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise CodingSessionCanonicalizationError()
        return {key: _normalized(value[key]) for key in sorted(value)}
    if isinstance(value, tuple):
        return [_normalized(item) for item in value]
    if isinstance(value, frozenset):
        normalized = [_normalized(item) for item in value]
        return sorted(normalized, key=_json_sort_key)
    raise CodingSessionCanonicalizationError()


def _json_sort_key(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def canonical_bytes(value: object, *, format_version: str = CANONICAL_FORMAT) -> bytes:
    if format_version != CANONICAL_FORMAT:
        raise CodingSessionVersionMismatch()
    try:
        return json.dumps(
            {"format": format_version, "value": _normalized(value)},
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except (TypeError, ValueError) as exc:
        raise CodingSessionCanonicalizationError() from exc


def content_fingerprint(value: object, *, format_version: str = CANONICAL_FORMAT) -> str:
    digest = hashlib.sha256(canonical_bytes(value, format_version=format_version)).hexdigest()
    return f"sha256:{digest}"
