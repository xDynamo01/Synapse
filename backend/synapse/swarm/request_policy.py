"""Safe user-facing policy for requesting a Swarm.

This module deliberately does not create missions or agents. It only turns an
explicit user request into a decision that the Primary Agent can confirm
before invoking the execution runtime.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SwarmRequest:
    requested: bool
    requested_agents: int | None
    explicit_models: tuple[str, ...]
    requires_confirmation: bool


_SWARM_RE = re.compile(r"\b(?:swarm|equipe de agentes|vários agentes|varios agentes)\b", re.I)
_ACTION_RE = re.compile(
    r"\b(?:use|usar|utilize|crie|criar|inicie|iniciar|monte|montar|ative|ativar|"
    r"execute|executar|faça|faca|quero|preciso|start|create|run|launch)\b",
    re.I,
)
_INFORMATIONAL_RE = re.compile(
    r"^\s*(?:o que|what\s+(?:is|are)|como\s+(?:funciona|crio|usar)|"
    r"how\s+(?:does|do|can)|quando\s+devo|when\s+should|qual\s+é)",
    re.I,
)
_COUNT_RE = re.compile(r"\b(?:com|crie|use|usando)\s+(\d{1,2})\s+(?:agentes?|agents?)\b", re.I)
_MODEL_RE = re.compile(
    r"\b(?:modelo|modelos)\s+([\w./:-]+(?:\s*(?:,|\s+e\s+|\s+and\s+)\s*[\w./:-]+)*)",
    re.I,
)
# Descriptions of a selection policy are not model identifiers. Unknown explicit
# names still reach route validation; they must not silently choose another model.
_MODEL_DESCRIPTORS = frozenset({
    "mais", "menos", "melhor", "melhores", "recomendado", "recomendados",
    "adequado", "adequados", "apropriado", "apropriados", "ideal", "ideais",
    "disponível", "disponivel", "disponíveis", "disponiveis", "local", "locais",
    "instalado", "instalados", "leve", "leves", "pequeno", "pequenos",
    "que", "para", "de", "do", "da", "dos", "das", "necessário", "necessários",
})


def classify_swarm_request(text: str) -> SwarmRequest:
    """Classify only explicit Swarm requests; ordinary tasks remain direct chat."""
    if (
        not _SWARM_RE.search(text)
        or not _ACTION_RE.search(text)
        or _INFORMATIONAL_RE.search(text)
    ):
        return SwarmRequest(False, None, (), False)
    count_match = _COUNT_RE.search(text)
    names: list[str] = []
    for model_match in _MODEL_RE.finditer(text):
        candidates = re.split(r"\s*,\s*|\s+(?:e|and)\s+", model_match.group(1), flags=re.I)
        if candidates[0].casefold() in _MODEL_DESCRIPTORS:
            continue
        for candidate in candidates:
            name = candidate.strip().rstrip(".,;")
            if name.casefold() in _MODEL_DESCRIPTORS:
                break
            if name and name not in names:
                names.append(name)
    # An explicit request can proceed without a confirmation only when the
    # user supplied enough execution intent for the Primary to validate.
    return SwarmRequest(
        requested=True,
        requested_agents=int(count_match.group(1)) if count_match else None,
        explicit_models=tuple(names),
        requires_confirmation=False,
    )
