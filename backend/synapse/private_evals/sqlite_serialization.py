from __future__ import annotations

import importlib
import inspect
import json
import types
from dataclasses import fields, is_dataclass
from decimal import Decimal
from enum import Enum
from functools import lru_cache
from typing import Any, Union, get_args, get_origin, get_type_hints

from .canonical import canonical_json
from .store_errors import EvalIntegrityConflict

_ALLOWED_MODULES = (
    "synapse.intelligence_boundary.models",
    "synapse.project_governance.models",
    "synapse.private_evals.analysis",
    "synapse.private_evals.catalog",
    "synapse.private_evals.case_evaluation",
    "synapse.private_evals.evaluation_records",
    "synapse.private_evals.evidence_projection",
    "synapse.private_evals.evidence_submission_models",
    "synapse.private_evals.execution_records",
    "synapse.private_evals.result_models",
    "synapse.private_evals.run_finalization_models",
    "synapse.private_evals.run_scoring",
    "synapse.private_evals.runs",
    "synapse.private_evals.scoring",
    "synapse.private_evals.security",
    "synapse.private_evals.states",
    "synapse.private_evals.values",
)


@lru_cache(maxsize=1)
def _type_registry() -> dict[str, type[Any]]:
    registry: dict[str, type[Any]] = {}
    for module_name in _ALLOWED_MODULES:
        module = importlib.import_module(module_name)
        for _, candidate in inspect.getmembers(module, inspect.isclass):
            if candidate.__module__ != module_name:
                continue
            if is_dataclass(candidate) or issubclass(candidate, Enum):
                registry[f"{candidate.__module__}.{candidate.__qualname__}"] = candidate
    return registry


def _type_name(value: type[Any]) -> str:
    return f"{value.__module__}.{value.__qualname__}"


def _encode(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            "$type": _type_name(type(value)),
            "$fields": {item.name: _encode(getattr(value, item.name)) for item in fields(value)},
        }
    if isinstance(value, Enum):
        return {"$enum": _type_name(type(value)), "$value": value.value}
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise EvalIntegrityConflict()
        return {"$decimal": format(value, "f")}
    if isinstance(value, tuple):
        return {"$tuple": [_encode(item) for item in value]}
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise EvalIntegrityConflict()


def encode_record(record: Any) -> str:
    if not is_dataclass(record) or isinstance(record, type):
        raise EvalIntegrityConflict()
    try:
        return canonical_json({"format_version": 1, "record": _encode(record)})
    except (TypeError, ValueError) as error:
        raise EvalIntegrityConflict() from error


def _decode_untyped(value: Any) -> Any:
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if not isinstance(value, dict):
        raise EvalIntegrityConflict()
    if set(value) == {"$decimal"} and isinstance(value["$decimal"], str):
        return Decimal(value["$decimal"])
    if set(value) == {"$tuple"} and isinstance(value["$tuple"], list):
        return tuple(_decode_untyped(item) for item in value["$tuple"])
    if set(value) == {"$enum", "$value"}:
        enum_type = _type_registry().get(value["$enum"])
        if enum_type is None or not issubclass(enum_type, Enum):
            raise EvalIntegrityConflict()
        return enum_type(value["$value"])
    if set(value) == {"$type", "$fields"}:
        record_type = _type_registry().get(value["$type"])
        if record_type is None or not is_dataclass(record_type):
            raise EvalIntegrityConflict()
        return _decode_dataclass(value, record_type)
    raise EvalIntegrityConflict()


def _decode_dataclass(value: Any, expected: type[Any]) -> Any:
    if not isinstance(value, dict) or set(value) != {"$type", "$fields"}:
        raise EvalIntegrityConflict()
    if value["$type"] != _type_name(expected) or not isinstance(value["$fields"], dict):
        raise EvalIntegrityConflict()
    declared = {item.name: item for item in fields(expected) if item.init}
    if set(value["$fields"]) != set(declared):
        raise EvalIntegrityConflict()
    hints = get_type_hints(expected)
    try:
        arguments = {
            name: _decode_typed(value["$fields"][name], hints[name]) for name in declared
        }
        return expected(**arguments)
    except EvalIntegrityConflict:
        raise
    except Exception as error:
        raise EvalIntegrityConflict() from error


def _decode_typed(value: Any, expected: Any) -> Any:
    if expected is Any:
        return _decode_untyped(value)
    origin = get_origin(expected)
    arguments = get_args(expected)
    if origin in (Union, types.UnionType):
        matches: list[Any] = []
        for candidate in arguments:
            if candidate is type(None) and value is None:
                matches.append(None)
                continue
            try:
                matches.append(_decode_typed(value, candidate))
            except EvalIntegrityConflict:
                pass
        if len(matches) != 1:
            raise EvalIntegrityConflict()
        return matches[0]
    if origin is tuple:
        if not isinstance(value, dict) or set(value) != {"$tuple"}:
            raise EvalIntegrityConflict()
        raw = value["$tuple"]
        if not isinstance(raw, list):
            raise EvalIntegrityConflict()
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return tuple(_decode_typed(item, arguments[0]) for item in raw)
        if len(raw) != len(arguments):
            raise EvalIntegrityConflict()
        return tuple(_decode_typed(item, kind) for item, kind in zip(raw, arguments))
    if expected is Decimal:
        if not isinstance(value, dict) or set(value) != {"$decimal"}:
            raise EvalIntegrityConflict()
        try:
            result = Decimal(value["$decimal"])
        except (ValueError, TypeError) as error:
            raise EvalIntegrityConflict() from error
        if not result.is_finite():
            raise EvalIntegrityConflict()
        return result
    if inspect.isclass(expected) and issubclass(expected, Enum):
        if (
            not isinstance(value, dict)
            or set(value) != {"$enum", "$value"}
            or value["$enum"] != _type_name(expected)
        ):
            raise EvalIntegrityConflict()
        try:
            return expected(value["$value"])
        except (TypeError, ValueError) as error:
            raise EvalIntegrityConflict() from error
    if inspect.isclass(expected) and is_dataclass(expected):
        return _decode_dataclass(value, expected)
    if expected is bool:
        if not isinstance(value, bool):
            raise EvalIntegrityConflict()
        return value
    if expected is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise EvalIntegrityConflict()
        return value
    if expected is str:
        if not isinstance(value, str):
            raise EvalIntegrityConflict()
        return value
    raise EvalIntegrityConflict()


def decode_record(payload: str, expected: type[Any]) -> Any:
    def reject_duplicate_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise EvalIntegrityConflict()
            result[key] = value
        return result

    try:
        raw = json.loads(payload, object_pairs_hook=reject_duplicate_fields)
    except EvalIntegrityConflict:
        raise
    except (TypeError, json.JSONDecodeError) as error:
        raise EvalIntegrityConflict() from error
    if not isinstance(raw, dict) or set(raw) != {"format_version", "record"}:
        raise EvalIntegrityConflict()
    if raw["format_version"] != 1:
        raise EvalIntegrityConflict()
    if canonical_json(raw) != payload:
        raise EvalIntegrityConflict()
    return _decode_dataclass(raw["record"], expected)
