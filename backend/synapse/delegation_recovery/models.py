from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

RecoveryRecommendation = str
RecoveryRiskLevel = str

RECOVERY_RECOMMENDATIONS: set[RecoveryRecommendation] = {
    "continue_processing",
    "retry_task",
    "manual_review",
    "move_to_dead_letter",
    "restore_from_dead_letter",
    "cancel_task",
    "unknown",
}

RECOVERY_RISK_LEVELS: set[RecoveryRiskLevel] = {"low", "medium", "high", "critical"}


@dataclass(frozen=True)
class RecoveryDecision:
    task_id: str
    recommendation: RecoveryRecommendation
    risk_level: RecoveryRiskLevel
    reasons: list[str]
    recommended_actions: list[str]
    execution_count: int
    failed_execution_count: int
    timeout_detected: bool
    dlq_present: bool
    retry_allowed: bool
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)
