from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.storage.atomic import atomic_write_text
from synapse.storage.collection import FileCollection
from synapse.storage.contracts import CollectionQuery
from synapse.tools.contracts import ToolExecutionPort
from synapse.tools.models import ToolExecutionRequest


class GovernanceRecordStoreAdapter:
    def __init__(self, collection: FileCollection) -> None:
        self.collection = collection

    def put(
        self,
        record_id: str,
        payload: dict[str, Any],
        *,
        expected_revision: int | None = None,
        create_only: bool = False,
    ) -> None:
        self.collection.put(
            record_id,
            payload,
            expected_revision=expected_revision,
            create_only=create_only,
        )

    def get(self, record_id: str) -> dict[str, Any]:
        return dict(self.collection.get(record_id).payload)

    def list(self, filters: dict[str, Any] | None = None) -> tuple[dict[str, Any], ...]:
        items: list[dict[str, Any]] = []
        cursor = None
        while True:
            page = self.collection.list(
                CollectionQuery(filters=filters or {}, cursor=cursor, limit=500)
            )
            items.extend(dict(item.payload) for item in page.items)
            if page.next_cursor is None:
                return tuple(items)
            cursor = page.next_cursor

    def delete(self, record_id: str) -> None:
        self.collection.delete(record_id)


class FileProjectDocumentAdapter:
    """Human-editable project documents below an authorized DataDir root."""

    def __init__(self, projects_root: Path) -> None:
        self.projects_root = projects_root.resolve(strict=False)
        self.projects_root.mkdir(parents=True, exist_ok=True)

    def write_project(self, root_reference: str, payload: dict[str, Any]) -> None:
        root = self._root(root_reference)
        governance = root / ".synapse"
        governance.mkdir(parents=True, exist_ok=True)
        for directory in ("rfcs", "adrs", "plans", "evidence", "evals", "policies"):
            (governance / directory).mkdir(parents=True, exist_ok=True)
        dump_structured_file(governance / "project.yaml", payload)

    def write_rfc(
        self,
        root_reference: str,
        rfc_id: str,
        manifest: dict[str, Any],
        markdown: str,
        *,
        revision: int,
    ) -> None:
        directory = self._root(root_reference) / ".synapse" / "rfcs" / rfc_id
        revision_dir = directory / "revisions" / str(revision)
        for child in (
            revision_dir,
            directory / "reviews",
            directory / "evidence",
            directory / "attachments",
        ):
            child.mkdir(parents=True, exist_ok=True)
        dump_structured_file(revision_dir / "manifest.yaml", manifest)
        atomic_write_text(revision_dir / "RFC.md", markdown)
        dump_structured_file(directory / "manifest.yaml", manifest)
        atomic_write_text(directory / "RFC.md", markdown)

    def read_rfc(self, root_reference: str, rfc_id: str) -> tuple[dict[str, Any], str]:
        directory = self._root(root_reference) / ".synapse" / "rfcs" / rfc_id
        return (
            load_structured_file(directory / "manifest.yaml"),
            (directory / "RFC.md").read_text(encoding="utf-8"),
        )

    def _root(self, root_reference: str) -> Path:
        candidate = (self.projects_root / root_reference).resolve(strict=False)
        if not candidate.is_relative_to(self.projects_root):
            raise ValueError("Project root reference escapes the authorized root")
        return candidate


class QualityGateExecutionAdapter:
    """Routes declared quality gates through ToolExecutionPort; never shell."""

    def __init__(self, tools: ToolExecutionPort) -> None:
        self.tools = tools

    def preview(self, tool_reference: str, arguments: dict[str, Any], *, actor_id: str) -> Any:
        return self.tools.preview(self._request(tool_reference, arguments, actor_id, True))

    def execute(
        self,
        tool_reference: str,
        arguments: dict[str, Any],
        *,
        actor_id: str,
        approval_id: str | None = None,
    ) -> Any:
        request = self._request(tool_reference, arguments, actor_id, False)
        return self.tools.execute(replace(request, approval_id=approval_id))

    @staticmethod
    def _request(
        tool_reference: str,
        arguments: dict[str, Any],
        actor_id: str,
        dry_run: bool,
    ) -> ToolExecutionRequest:
        return ToolExecutionRequest(
            tool_id=tool_reference,
            arguments=arguments,
            caller=actor_id,
            caller_type="agent",
            dry_run=dry_run,
            metadata={"project_governance_quality_gate": True},
        )
