from __future__ import annotations

from dataclasses import dataclass

from synapse.retrieval_intent import RetrievalDirective, RetrievalIntent


@dataclass(frozen=True)
class RetrievalDecision:
    directive: RetrievalDirective
    project_id: str | None
    allowed: bool
    reason: str

    def to_dict(self) -> dict[str, str | bool | None]:
        return {
            "intent": self.directive.intent.value,
            "source": self.directive.source.value,
            "query": self.directive.query,
            "project_id": self.project_id,
            "allowed": self.allowed,
            "reason": self.reason,
        }


def decide_project_knowledge_retrieval(
    directive: RetrievalDirective,
    project_id: str | None,
) -> RetrievalDecision:
    if directive.intent is RetrievalIntent.NONE:
        return RetrievalDecision(directive, project_id, False, "no_explicit_retrieval_intent")
    if directive.intent is not RetrievalIntent.PROJECT_KNOWLEDGE:
        return RetrievalDecision(directive, project_id, False, "unsupported_retrieval_intent")
    if not directive.query.strip():
        return RetrievalDecision(directive, project_id, False, "empty_retrieval_query")
    if not project_id:
        return RetrievalDecision(directive, project_id, False, "missing_project_scope")
    return RetrievalDecision(directive, project_id, True, "explicit_intent_with_project_scope")
