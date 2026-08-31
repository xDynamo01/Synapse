from __future__ import annotations

import re
from dataclasses import dataclass

from synapse.skills.phase10_errors import InvalidSkillExternalReference

_REFERENCE_LOCAL = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$", re.ASCII)
_BINDING_DIGEST = re.compile(r"^[0-9a-f]{64}$", re.ASCII)


def _validate_reference(value: object, namespace: str) -> None:
    prefix = f"{namespace}:"
    if (
        not isinstance(value, str)
        or not value.startswith(prefix)
        or not _REFERENCE_LOCAL.fullmatch(value.removeprefix(prefix))
    ):
        raise InvalidSkillExternalReference()


@dataclass(frozen=True, order=True)
class ExternalAuthorityRef:
    value: str

    def __post_init__(self) -> None:
        _validate_reference(self.value, "external-authority")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class ExternalBinderRef:
    value: str

    def __post_init__(self) -> None:
        _validate_reference(self.value, "external-binder")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class GovernanceDecisionRef:
    value: str

    def __post_init__(self) -> None:
        _validate_reference(self.value, "governance-decision")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class GovernanceDecisionKindRef:
    value: str

    def __post_init__(self) -> None:
        _validate_reference(self.value, "governance-decision-kind")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class GovernancePolicyRef:
    value: str

    def __post_init__(self) -> None:
        _validate_reference(self.value, "governance-policy")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class IntelligenceFactRef:
    value: str

    def __post_init__(self) -> None:
        _validate_reference(self.value, "intelligence-fact")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class IntelligenceAnalysisRef:
    value: str

    def __post_init__(self) -> None:
        _validate_reference(self.value, "intelligence-analysis")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class IntelligenceFactKindRef:
    value: str

    def __post_init__(self) -> None:
        _validate_reference(self.value, "intelligence-fact-kind")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class IntelligenceProfileRef:
    value: str

    def __post_init__(self) -> None:
        _validate_reference(self.value, "intelligence-profile")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class ExternalBindingRef:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise InvalidSkillExternalReference()
        namespace, separator, digest = self.value.partition(":")
        if (
            separator != ":"
            or namespace
            not in {
                "governance-binding",
                "intelligence-binding",
            }
            or not _BINDING_DIGEST.fullmatch(digest)
        ):
            raise InvalidSkillExternalReference()

    @property
    def family(self) -> str:
        return self.value.partition(":")[0]

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class ExternalBindingOccurrenceRef:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise InvalidSkillExternalReference()
        namespace, separator, digest = self.value.partition(":")
        if (
            separator != ":"
            or namespace
            not in {
                "governance-binding-occurrence",
                "intelligence-binding-occurrence",
            }
            or not _BINDING_DIGEST.fullmatch(digest)
        ):
            raise InvalidSkillExternalReference()

    @property
    def family(self) -> str:
        return self.value.partition(":")[0]

    def __str__(self) -> str:
        return self.value
