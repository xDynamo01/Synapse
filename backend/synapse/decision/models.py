from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DecisionCandidate:
    """One action the surrounding code is willing to execute."""

    candidate_id: str
    description: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DecisionResult:
    """A validated choice returned by a decision provider."""

    candidate_id: str
    confidence: float
    probabilities: dict[str, float]
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
