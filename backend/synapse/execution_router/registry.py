from __future__ import annotations

from synapse.core.exceptions import NotFound, ValidationError
from synapse.execution_router.models import TARGET_TYPES, ExecutionTarget


class ExecutionTargetRegistry:
    def __init__(self) -> None:
        self._targets: dict[str, ExecutionTarget] = {}

    def register(self, target: ExecutionTarget) -> None:
        if target.target_type not in TARGET_TYPES:
            raise ValidationError(f"Invalid execution target type: {target.target_type}")
        if not target.target_id.strip():
            raise ValidationError("Execution target_id is required")
        self._targets[target.target_id] = target

    def get(self, target_id: str) -> ExecutionTarget:
        try:
            return self._targets[target_id]
        except KeyError as exc:
            raise NotFound(f"Execution target not found: {target_id}") from exc

    def list_targets(self, available: bool | None = None) -> list[ExecutionTarget]:
        targets = list(self._targets.values())
        if available is not None:
            targets = [target for target in targets if target.available is available]
        return sorted(targets, key=lambda target: (-target.priority, target.target_id))
