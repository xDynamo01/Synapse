from __future__ import annotations

from synapse.core.exceptions import ValidationError


class AudioValidationError(ValidationError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
