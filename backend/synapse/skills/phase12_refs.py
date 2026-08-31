from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from synapse.skills.phase12_errors import InvalidSkillExecutionHandoffRequest

_REF = r"^[a-z0-9][a-z0-9._-]{1,127}$"
_DIGEST = r"^[0-9a-f]{64}$"


class SkillExecutionHandoffFormatVersion(StrEnum):
    V1 = "v1"


@dataclass(frozen=True, order=True)
class SkillExecutionProfileRef:
    value: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.value, str)
            or len(self.value) > 128
            or not self.value.startswith("execution-profile:")
            or not re.fullmatch(_REF, self.value.removeprefix("execution-profile:"))
        ):
            raise InvalidSkillExecutionHandoffRequest()

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class SkillExecutionHandoffId:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not re.fullmatch(_DIGEST, self.value):
            raise InvalidSkillExecutionHandoffRequest()

    def __str__(self) -> str:
        return self.value
