from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from synapse.project_governance.contracts import RFCEvidenceWritePort
from synapse.project_governance.models import EvidenceRecord

from ..case_evaluation import (
    CaseEvaluationRequest,
    CaseEvaluationResponse,
    CaseEvaluationStatus,
    evaluation_request_fingerprint,
    evaluation_response_fingerprint,
    validate_evaluation_scores,
)
from ..case_evaluation_contracts import EvalCaseEvaluatorPort
from ..execution import (
    CaseExecutionRequest,
    CaseExecutionResponse,
    request_fingerprint,
    validate_execution_response,
)
from ..execution_contracts import EvalCaseExecutionPort
from ..security import EvalSecuritySnapshot, security_snapshot_fingerprint
from ..security_contracts import SecuritySnapshotReadPort
from .errors import (
    AdapterEvaluatorResponseInvalid,
    AdapterEvaluatorUnavailable,
    AdapterExecutionResponseInvalid,
    AdapterExecutionUnavailable,
    AmbiguousExternalWrite,
    GovernanceSubmissionUnavailable,
    SecuritySnapshotMismatch,
    SecuritySnapshotUnavailable,
)

_SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SENSITIVE = re.compile(
    r"(?i)(?:token|secret|password|credential|authorization|bearer|api[_-]?key|sk-)"
)


@dataclass(frozen=True)
class ExternalAdapterConfig:
    """Non-secret adapter metadata.

    ``requested_timeout_seconds`` is declarative.  These bridges cannot enforce
    deadlines or cancellation because the frozen client ports do not accept a
    timeout argument.  A future Composition Root must configure a client that
    enforces an equal or stricter deadline.
    """

    adapter_id: str
    adapter_version: str
    requested_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        for value in (self.adapter_id, self.adapter_version):
            if (
                not isinstance(value, str)
                or not _SAFE_REFERENCE.fullmatch(value)
                or _SENSITIVE.search(value)
                or "/" in value
                or "\\" in value
            ):
                raise ValueError("adapter identity must be a safe reference")
        if (
            isinstance(self.requested_timeout_seconds, bool)
            or not isinstance(self.requested_timeout_seconds, (int, float))
            or not 0.05 <= float(self.requested_timeout_seconds) <= 300.0
        ):
            raise ValueError("adapter timeout is invalid")

    def __repr__(self) -> str:
        return (
            "ExternalAdapterConfig("
            f"adapter_id={self.adapter_id!r}, adapter_version={self.adapter_version!r})"
        )


@dataclass(frozen=True)
class IntelligenceSecuritySnapshotAdapter(SecuritySnapshotReadPort):
    """Validate a preconfigured Intelligence-owned snapshot client; never authorize."""

    _client: SecuritySnapshotReadPort = field(repr=False)
    config: ExternalAdapterConfig

    def __post_init__(self) -> None:
        if not callable(getattr(self._client, "snapshot", None)):
            raise TypeError("security snapshot client is required")
        if not isinstance(self.config, ExternalAdapterConfig):
            raise TypeError("external adapter configuration is required")

    def snapshot(
        self,
        project_id: str,
        asset_ids: tuple[str, ...],
        provider_ids: tuple[str, ...],
    ) -> EvalSecuritySnapshot:
        if (
            not isinstance(project_id, str)
            or not _SAFE_REFERENCE.fullmatch(project_id)
            or not isinstance(asset_ids, tuple)
            or not isinstance(provider_ids, tuple)
            or any(
                not isinstance(item, str) or not _SAFE_REFERENCE.fullmatch(item)
                for item in (*asset_ids, *provider_ids)
            )
            or len(asset_ids) != len(set(asset_ids))
            or len(provider_ids) != len(set(provider_ids))
        ):
            raise SecuritySnapshotMismatch()
        try:
            snapshot = self._client.snapshot(project_id, asset_ids, provider_ids)
        except TimeoutError:
            raise SecuritySnapshotUnavailable() from None
        except Exception:
            raise SecuritySnapshotUnavailable() from None
        if not isinstance(snapshot, EvalSecuritySnapshot):
            raise SecuritySnapshotMismatch()
        try:
            validated = replace(snapshot)
            valid = (
                validated == snapshot
                and tuple(sorted(item.reference.asset_id for item in snapshot.assets))
                == tuple(sorted(asset_ids))
                and tuple(sorted(item.provider_id for item in snapshot.providers))
                == tuple(sorted(provider_ids))
                and snapshot.fingerprint == security_snapshot_fingerprint(snapshot)
            )
        except Exception:
            raise SecuritySnapshotMismatch() from None
        if not valid:
            raise SecuritySnapshotMismatch()
        return snapshot


@dataclass(frozen=True)
class CaseExecutionBoundaryAdapter(EvalCaseExecutionPort):
    _backend: EvalCaseExecutionPort = field(repr=False)
    config: ExternalAdapterConfig

    def __post_init__(self) -> None:
        if not callable(getattr(self._backend, "execute_case", None)):
            raise TypeError("case execution backend is required")
        if not isinstance(self.config, ExternalAdapterConfig):
            raise TypeError("external adapter configuration is required")

    def execute_case(self, request: CaseExecutionRequest) -> CaseExecutionResponse:
        try:
            valid_request = (
                isinstance(request, CaseExecutionRequest)
                and request.fingerprint == request_fingerprint(request)
            )
        except Exception:
            valid_request = False
        if not valid_request:
            raise AdapterExecutionResponseInvalid()
        try:
            response = self._backend.execute_case(request)
        except TimeoutError:
            raise AdapterExecutionUnavailable() from None
        except Exception:
            raise AdapterExecutionUnavailable() from None
        if not isinstance(response, CaseExecutionResponse):
            raise AdapterExecutionResponseInvalid()
        try:
            if replace(response) != response:
                raise AdapterExecutionResponseInvalid()
            validate_execution_response(request, response)
        except AdapterExecutionResponseInvalid:
            raise
        except Exception:
            raise AdapterExecutionResponseInvalid() from None
        return response


@dataclass(frozen=True)
class CaseEvaluatorBoundaryAdapter(EvalCaseEvaluatorPort):
    _backend: EvalCaseEvaluatorPort = field(repr=False)
    config: ExternalAdapterConfig

    def __post_init__(self) -> None:
        if not callable(getattr(self._backend, "evaluate", None)):
            raise TypeError("case evaluator backend is required")
        if not isinstance(self.config, ExternalAdapterConfig):
            raise TypeError("external adapter configuration is required")

    async def evaluate(self, request: CaseEvaluationRequest) -> CaseEvaluationResponse:
        try:
            valid_request = (
                isinstance(request, CaseEvaluationRequest)
                and request.fingerprint == evaluation_request_fingerprint(request)
            )
        except Exception:
            valid_request = False
        if not valid_request:
            raise AdapterEvaluatorResponseInvalid()
        try:
            response = await self._backend.evaluate(request)
        except TimeoutError:
            raise AdapterEvaluatorUnavailable() from None
        except Exception:
            raise AdapterEvaluatorUnavailable() from None
        if not isinstance(response, CaseEvaluationResponse):
            raise AdapterEvaluatorResponseInvalid()
        try:
            if (
                replace(response) != response
                or response.event_identity != request.event_identity
                or response.evaluator != request.evaluator
                or response.fingerprint != evaluation_response_fingerprint(response)
            ):
                raise AdapterEvaluatorResponseInvalid()
            if response.status is CaseEvaluationStatus.SUCCEEDED:
                validate_evaluation_scores(request, response.scores)
        except AdapterEvaluatorResponseInvalid:
            raise
        except Exception:
            raise AdapterEvaluatorResponseInvalid() from None
        return response


@dataclass(frozen=True)
class GovernanceEvidenceWriteAdapter(RFCEvidenceWritePort):
    _client: RFCEvidenceWritePort = field(repr=False)
    config: ExternalAdapterConfig

    def __post_init__(self) -> None:
        if not callable(getattr(self._client, "record_evidence", None)):
            raise TypeError("Governance Evidence client is required")
        if not isinstance(self.config, ExternalAdapterConfig):
            raise TypeError("external adapter configuration is required")

    def record_evidence(self, evidence: EvidenceRecord) -> EvidenceRecord:
        try:
            valid_input = isinstance(evidence, EvidenceRecord) and replace(evidence) == evidence
        except Exception:
            valid_input = False
        if not valid_input:
            raise GovernanceSubmissionUnavailable()
        try:
            recorded = self._client.record_evidence(evidence)
        except ConnectionRefusedError:
            # Refusal occurs before a connection is established, so absence of
            # the write is provable and reconciliation is not required.
            raise GovernanceSubmissionUnavailable() from None
        except Exception:
            # Once a connection existed, acceptance cannot be disproved through
            # this write-only contract.  Never retry automatically.
            raise AmbiguousExternalWrite() from None
        if not isinstance(recorded, EvidenceRecord) or recorded != evidence:
            # A response is observed only after the write call.  A corrupt or
            # divergent receipt cannot prove that Governance rejected the write.
            raise AmbiguousExternalWrite()
        return recorded
