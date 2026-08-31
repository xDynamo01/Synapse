from __future__ import annotations

from dataclasses import replace
from typing import Any

from synapse.skills.models import SkillScriptDescriptor
from synapse.storage.collection import FileCollection
from synapse.storage.contracts import CollectionQuery
from synapse.tools.contracts import ToolExecutionPort
from synapse.tools.models import ToolExecutionRequest


class SkillRecordStoreAdapter:
    def __init__(self, collection: FileCollection) -> None:
        self.collection = collection

    def put(self, record_id: str, payload: dict[str, Any], *, create_only: bool = False) -> None:
        self.collection.put(record_id, payload, create_only=create_only)

    def delete(self, record_id: str) -> None:
        self.collection.delete(record_id)

    def list(self, filters: dict[str, Any] | None = None) -> tuple[dict[str, Any], ...]:
        page = self.collection.list(CollectionQuery(filters=filters or {}))
        return tuple(dict(item.payload) for item in page.items)


class SkillScriptExecutionAdapter:
    """Route a declared script through one registered Tool; never through shell."""

    def __init__(self, tools: ToolExecutionPort) -> None:
        self.tools = tools

    def preview(
        self, descriptor: SkillScriptDescriptor, inputs: dict[str, Any], *, actor_id: str
    ) -> Any:
        return self.tools.preview(self._request(descriptor, inputs, actor_id, dry_run=True))

    def execute(
        self,
        descriptor: SkillScriptDescriptor,
        inputs: dict[str, Any],
        *,
        actor_id: str,
        approval_id: str | None = None,
    ) -> Any:
        request = self._request(descriptor, inputs, actor_id, dry_run=False)
        return self.tools.execute(replace(request, approval_id=approval_id))

    @staticmethod
    def _request(
        descriptor: SkillScriptDescriptor,
        inputs: dict[str, Any],
        actor_id: str,
        *,
        dry_run: bool,
    ) -> ToolExecutionRequest:
        if len(descriptor.required_tools) != 1:
            raise ValueError("A skill script must bind exactly one registered tool")
        return ToolExecutionRequest(
            tool_id=descriptor.required_tools[0],
            arguments={"script_id": descriptor.script_id, "inputs": inputs},
            caller=actor_id,
            caller_type="agent",
            dry_run=dry_run,
            timeout_seconds=descriptor.timeout,
            metadata={
                "skill_script": True,
                "checksum": descriptor.checksum,
                "sandbox_required": descriptor.sandbox_required,
            },
        )
