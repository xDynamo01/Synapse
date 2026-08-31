from __future__ import annotations

import json
import types
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TypeVar, get_args, get_origin, get_type_hints

from .errors import SkillPersistenceRecordDecodeFailed

_T = TypeVar("_T")
_MAX_PAYLOAD_BYTES = 1_048_576
_MAX_NESTING_DEPTH = 64


def encode_record(value: object) -> str:
    try:
        payload = json.dumps(
            _encode(value),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        if len(payload.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
            raise ValueError
        return payload
    except (TypeError, ValueError) as exc:
        raise SkillPersistenceRecordDecodeFailed() from exc


def decode_record(payload: str, record_type: type[_T]) -> _T:
    try:
        if len(payload.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
            raise ValueError
        raw = json.loads(
            payload,
            object_pairs_hook=_unique_object,
            parse_float=_reject_json_number,
            parse_constant=_reject_json_number,
        )
        _assert_depth(raw, 0)
        value = _decode(raw, record_type)
    except (KeyError, TypeError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        raise SkillPersistenceRecordDecodeFailed() from exc
    if not isinstance(value, record_type):
        raise SkillPersistenceRecordDecodeFailed()
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError
        value[key] = item
    return value


def _reject_json_number(_value: str) -> object:
    raise ValueError


def _assert_depth(value: object, depth: int) -> None:
    if depth > _MAX_NESTING_DEPTH:
        raise ValueError
    if isinstance(value, dict):
        for item in value.values():
            _assert_depth(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _assert_depth(item, depth + 1)


def canonical_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SkillPersistenceRecordDecodeFailed()
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _encode(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _encode(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, datetime):
        return canonical_timestamp(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError


def _decode(value: object, expected: object) -> object:
    origin = get_origin(expected)
    args = get_args(expected)
    if origin in (types.UnionType,):
        for candidate in args:
            if candidate is type(None) and value is None:
                return None
            try:
                return _decode(value, candidate)
            except (TypeError, ValueError):
                continue
        raise TypeError
    if origin is tuple:
        if not isinstance(value, list):
            raise TypeError
        item_type = args[0]
        return tuple(_decode(item, item_type) for item in value)
    if expected is datetime:
        if not isinstance(value, str) or not value.endswith("Z"):
            raise TypeError
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        if canonical_timestamp(parsed) != value:
            raise ValueError
        return parsed
    if isinstance(expected, type) and issubclass(expected, Enum):
        return expected(value)
    if isinstance(expected, type) and is_dataclass(expected):
        if not isinstance(value, dict) or set(value) != {item.name for item in fields(expected)}:
            raise TypeError
        hints = get_type_hints(expected)
        return expected(
            **{
                field.name: _decode(value[field.name], hints[field.name])
                for field in fields(expected)
            }
        )
    if expected in (str, int, bool):
        if not isinstance(value, expected) or expected is int and isinstance(value, bool):
            raise TypeError
        return value
    if expected is type(None) and value is None:
        return None
    raise TypeError
