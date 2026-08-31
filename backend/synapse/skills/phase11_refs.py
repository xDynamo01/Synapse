from __future__ import annotations

import re
from dataclasses import dataclass

from synapse.skills.phase11_errors import InvalidSkillPrivateEvalReference

_REFERENCE_LOCAL = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$", re.ASCII)
_BINDING_DIGEST = re.compile(r"^[0-9a-f]{64}$", re.ASCII)


def _validate_reference(value: object, namespace: str) -> None:
    prefix = f"{namespace}:"
    if (
        not isinstance(value, str)
        or not value.startswith(prefix)
        or not _REFERENCE_LOCAL.fullmatch(value.removeprefix(prefix))
    ):
        raise InvalidSkillPrivateEvalReference()


@dataclass(frozen=True, order=True)
class PrivateEvalRunRef:
    value: str

    def __post_init__(self) -> None:
        _validate_reference(self.value, "private-eval-run")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class PrivateEvalResultRef:
    value: str

    def __post_init__(self) -> None:
        _validate_reference(self.value, "private-eval-result")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class PrivateEvalVerdictRef:
    value: str

    def __post_init__(self) -> None:
        _validate_reference(self.value, "private-eval-verdict")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class PrivateEvalEvidenceRef:
    value: str

    def __post_init__(self) -> None:
        _validate_reference(self.value, "private-eval-evidence")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class PrivateEvalSuiteRef:
    value: str

    def __post_init__(self) -> None:
        _validate_reference(self.value, "private-eval-suite")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class PrivateEvalCaseRef:
    value: str

    def __post_init__(self) -> None:
        _validate_reference(self.value, "private-eval-case")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class PrivateEvalProfileRef:
    value: str

    def __post_init__(self) -> None:
        _validate_reference(self.value, "private-eval-profile")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class PrivateEvalBaselineRef:
    value: str

    def __post_init__(self) -> None:
        _validate_reference(self.value, "private-eval-baseline")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class PrivateEvalComparisonRef:
    value: str

    def __post_init__(self) -> None:
        _validate_reference(self.value, "private-eval-comparison")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class PrivateEvalRegressionRef:
    value: str

    def __post_init__(self) -> None:
        _validate_reference(self.value, "private-eval-regression")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class PrivateEvalBindingRef:
    value: str

    def __post_init__(self) -> None:
        prefix = "private-eval-binding:"
        if (
            not isinstance(self.value, str)
            or not self.value.startswith(prefix)
            or not _BINDING_DIGEST.fullmatch(self.value.removeprefix(prefix))
        ):
            raise InvalidSkillPrivateEvalReference()

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class PrivateEvalBindingOccurrenceRef:
    value: str

    def __post_init__(self) -> None:
        prefix = "private-eval-binding-occurrence:"
        if (
            not isinstance(self.value, str)
            or not self.value.startswith(prefix)
            or not _BINDING_DIGEST.fullmatch(self.value.removeprefix(prefix))
        ):
            raise InvalidSkillPrivateEvalReference()

    def __str__(self) -> str:
        return self.value
