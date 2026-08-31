from __future__ import annotations

from typing import Any

from synapse.agent_loop.models import CommitResult
from synapse.attention.models import AttentionItem, Decision
from synapse.core.permissions import PermissionContext


class MemoryCommitPolicy:
    """Conservative, explicit memory commit policy; no regex fact extraction."""

    def __init__(self, memory_runtime: Any | None = None) -> None:
        self.memory_runtime = memory_runtime

    def commit(
        self,
        item: AttentionItem,
        decision: Decision,
        action_result: Any | None,
        *,
        context: PermissionContext,
    ) -> CommitResult:
        metadata = item.metadata
        importance = int(metadata.get("memory_importance", 0))
        persistent = bool(metadata.get("persistent", False))
        novel = bool(metadata.get("novel", False))
        consent = bool(metadata.get("memory_consent", False))
        sensitivity = str(metadata.get("sensitivity", "internal"))
        if self.memory_runtime is None:
            return CommitResult(False, skipped=True, reasons=["memory_runtime_unavailable"])
        reasons = []
        if importance < 60:
            reasons.append("importance_below_threshold")
        if not persistent:
            reasons.append("not_persistent")
        if not novel:
            reasons.append("not_novel")
        if sensitivity in {"sensitive", "restricted"} and not consent:
            reasons.append("sensitive_without_consent")
        if item.confidence < 0.7:
            reasons.append("confidence_below_threshold")
        if reasons:
            return CommitResult(False, skipped=True, reasons=reasons)
        record = self.memory_runtime.create(
            context,
            scope=str(metadata.get("memory_scope", "user")),
            owner_id=str(metadata.get("memory_owner_id", context.actor_id)),
            source="agent_loop",
            content=item.summary,
            confidence=item.confidence,
            importance=importance,
            tags=["agent-loop", item.type],
            metadata={
                "attention_item_id": item.id,
                "decision_id": decision.id,
                "action_status": getattr(action_result, "status", None),
            },
        )
        return CommitResult(True, memory_ids=[record.id])
