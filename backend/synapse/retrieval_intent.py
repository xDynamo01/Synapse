from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from enum import Enum


class RetrievalIntent(str, Enum):
    NONE = "none"
    PROJECT_KNOWLEDGE = "project_knowledge"
    FILE_SEARCH = "file_search"
    WEB_SEARCH = "web_search"


class RetrievalIntentSource(str, Enum):
    NONE = "none"
    SLASH = "slash"
    VOICE_EXPLICIT = "voice_explicit"
    TEXT_EXPLICIT = "text_explicit"


class RetrievalPolicyMode(str, Enum):
    OFF = "off"
    EXPLICIT = "explicit"
    AUTO = "auto"


@dataclass(frozen=True)
class RetrievalDirective:
    intent: RetrievalIntent = RetrievalIntent.NONE
    source: RetrievalIntentSource = RetrievalIntentSource.NONE
    query: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            **asdict(self),
            "intent": self.intent.value,
            "source": self.source.value,
        }


_PROJECT_COMMAND = re.compile(r"^/project(?:\s+(?P<query>.+))?$", re.IGNORECASE | re.DOTALL)

_EXPLICIT_PROJECT_PATTERNS = (
    re.compile(
        r"^(?:pesquise|pesquisar|procure|buscar|busque|consulte|verifique|olhe|leia)\s+"
        r"(?:nesse|neste|no|na|nos|nas|dentro do|dentro dos)?\s*"
        r"(?:projeto|arquivos?|documentos?|anexos?|base de conhecimento|knowledge|rag)"
        r"(?:\s+(?:atual|armazenados?|do projeto|desse projeto|deste projeto|sobre|onde|por|qual|quais))?"
        r"\s*(?P<query>.*)$"
    ),
    re.compile(
        r"^(?:nos|nosso|no)\s+(?:arquivos?|documentos?)\s+"
        r"(?:procure|pesquise|busque|consulte|verifique)\s*(?P<query>.*)$"
    ),
)


def detect_text_retrieval_intent(message: str) -> RetrievalDirective:
    stripped = message.strip()
    command = _PROJECT_COMMAND.match(stripped)
    if command:
        return RetrievalDirective(
            intent=RetrievalIntent.PROJECT_KNOWLEDGE,
            source=RetrievalIntentSource.SLASH,
            query=_clean_query(command.group("query") or ""),
        )
    explicit = _detect_explicit_project_request(stripped, RetrievalIntentSource.TEXT_EXPLICIT)
    if explicit.intent is not RetrievalIntent.NONE:
        return explicit
    return RetrievalDirective()


def detect_voice_retrieval_intent(transcript: str) -> RetrievalDirective:
    return _detect_explicit_project_request(transcript, RetrievalIntentSource.VOICE_EXPLICIT)


def _detect_explicit_project_request(
    value: str,
    source: RetrievalIntentSource,
) -> RetrievalDirective:
    normalized = _normalize(value)
    for pattern in _EXPLICIT_PROJECT_PATTERNS:
        match = pattern.match(normalized)
        if match:
            return RetrievalDirective(
                intent=RetrievalIntent.PROJECT_KNOWLEDGE,
                source=source,
                query=_clean_query(match.group("query") or ""),
            )
    return RetrievalDirective()


def normalize_retrieval_directive(
    value: RetrievalDirective | dict[str, str] | None,
) -> RetrievalDirective:
    if value is None:
        return RetrievalDirective()
    if isinstance(value, RetrievalDirective):
        return value
    return RetrievalDirective(
        intent=RetrievalIntent(str(value.get("intent") or RetrievalIntent.NONE.value)),
        source=RetrievalIntentSource(str(value.get("source") or RetrievalIntentSource.NONE.value)),
        query=_clean_query(str(value.get("query") or "")),
    )


def _clean_query(value: str) -> str:
    return " ".join(value.strip(" .").split())


def _normalize(value: str) -> str:
    lowered = value.casefold()
    normalized = unicodedata.normalize("NFKD", lowered)
    return "".join(char for char in normalized if not unicodedata.combining(char)).strip(" .!")
