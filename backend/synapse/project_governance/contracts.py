from __future__ import annotations

from typing import Any, Protocol

from synapse.project_governance.models import (
    EvidenceRecord,
    ProjectContext,
    RFCGateRequest,
    RFCGateResult,
    RFCImplementationBinding,
)


class GovernanceRecordStore(Protocol):
    def put(
        self,
        record_id: str,
        payload: dict[str, Any],
        *,
        expected_revision: int | None = None,
        create_only: bool = False,
    ) -> None: ...
    def get(self, record_id: str) -> dict[str, Any]: ...
    def list(self, filters: dict[str, Any] | None = None) -> tuple[dict[str, Any], ...]: ...
    def delete(self, record_id: str) -> None: ...


class ProjectDocumentPort(Protocol):
    def write_project(self, root_reference: str, payload: dict[str, Any]) -> None: ...
    def write_rfc(
        self,
        root_reference: str,
        rfc_id: str,
        manifest: dict[str, Any],
        markdown: str,
        *,
        revision: int,
    ) -> None: ...
    def read_rfc(self, root_reference: str, rfc_id: str) -> tuple[dict[str, Any], str]: ...


class ProjectContextReadPort(Protocol):
    def read_project_context(self, project_id: str, *, budget: int = 8000) -> ProjectContext: ...


class RFCGatePort(Protocol):
    def evaluate_gate(self, request: RFCGateRequest) -> RFCGateResult: ...


class RFCEvidenceWritePort(Protocol):
    def record_evidence(self, evidence: EvidenceRecord) -> EvidenceRecord: ...


class ImplementationBindingPort(Protocol):
    def validate_binding(self, binding: RFCImplementationBinding) -> RFCGateResult: ...


class QualityGateExecutionPort(Protocol):
    def preview(self, tool_reference: str, arguments: dict[str, Any], *, actor_id: str) -> Any: ...
    def execute(
        self,
        tool_reference: str,
        arguments: dict[str, Any],
        *,
        actor_id: str,
        approval_id: str | None = None,
    ) -> Any: ...
