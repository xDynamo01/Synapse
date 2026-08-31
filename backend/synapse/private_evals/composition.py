"""Explicit operational composition for the Private Evals bounded context.

This module constructs approved components.  It does not execute or sequence the
evaluation stages and it never discovers dependencies from process-global state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Generic, TypeVar

from synapse.project_governance.contracts import RFCEvidenceWritePort
from synapse.project_governance.models import EvidenceRecord

from .adapters.boundaries import (
    CaseEvaluatorBoundaryAdapter,
    CaseExecutionBoundaryAdapter,
    ExternalAdapterConfig,
    GovernanceEvidenceWriteAdapter,
    IntelligenceSecuritySnapshotAdapter,
)
from .adapters.queries import (
    EvidenceCoordinationReference,
    SQLiteEvidenceLocalStateReader,
)
from .adapters.resolvers import (
    PrivateEvalsCommandResolverAdapter,
    ResolverRecordCatalog,
)
from .case_evaluation import EvalResultService
from .case_evaluation_contracts import EvalCaseEvaluatorPort
from .catalog_runtime import EvalCatalogRuntime
from .command_contracts import PrivateEvalsCommandDependencies
from .command_handlers import PrivateEvalsCommandHandlers
from .evidence_submission_service import EvalEvidenceSubmissionService
from .execution_contracts import EvalCaseExecutionPort
from .query_handler import PrivateEvalsRunSummaryQuery
from .query_models import (
    EvidenceLocalStateProjection,
    RunSummaryRequest,
    RunSummaryResponse,
)
from .result_materialization import MaterializedOutputService
from .run_finalization_service import EvalRunFinalizationService
from .run_runtime import EvalRunRuntime
from .run_scoring_service import RunScoringService
from .security_contracts import SecuritySnapshotReadPort
from .sqlite_stores import (
    SCHEMA_VERSION,
    PrivateEvalsPersistenceConfig,
    SQLiteEvalAnalysisStore,
    SQLiteEvalCatalogStore,
    SQLiteEvalEvidenceStore,
    SQLiteEvalMaterializationStore,
    SQLiteEvalRunStore,
)
from .store_errors import EvalStoreError
from .values import EvalRunId

_SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SENSITIVE = re.compile(
    r"(?i)(?:token|secret|password|credential|authorization|bearer|api[_-]?key|sk-)"
)
T = TypeVar("T")


class PrivateEvalsCompositionError(RuntimeError):
    """Base class for fixed, non-sensitive composition failures."""

    _message = "Private Evals runtime composition failed"

    def __init__(self, _unsafe_message: str | None = None) -> None:
        super().__init__(self._message)


class PrivateEvalsConfigInvalid(PrivateEvalsCompositionError):
    _message = "Private Evals runtime configuration is invalid"


class PrivateEvalsCapabilityUnavailable(PrivateEvalsCompositionError):
    _message = "Private Evals external capability is unavailable"


class PrivateEvalsRuntimeClosed(PrivateEvalsCompositionError):
    _message = "Private Evals runtime is closed"


class PrivateEvalsRuntimeReadOnly(PrivateEvalsCompositionError):
    _message = "Private Evals runtime is read-only"


class PrivateEvalsConstructionFailed(PrivateEvalsCompositionError):
    _message = "Private Evals runtime construction failed"


class ExternalCapabilityName(StrEnum):
    INTELLIGENCE_SNAPSHOT = "intelligence_snapshot"
    CASE_EXECUTION = "case_execution"
    CASE_EVALUATOR = "case_evaluator"
    GOVERNANCE_WRITE = "governance_write"


class CapabilityBindingStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


class PrivateEvalsLifecycleState(StrEnum):
    LOCALLY_OPERATIONAL = "locally_operational"
    EXTERNALLY_BOUND = "externally_bound"
    DEGRADED = "degraded"
    CLOSED = "closed"


def _validate_safe_reference(value: object) -> None:
    if (
        not isinstance(value, str)
        or not _SAFE_REFERENCE.fullmatch(value)
        or _SENSITIVE.search(value)
        or "/" in value
        or "\\" in value
    ):
        raise PrivateEvalsConfigInvalid()


@dataclass(frozen=True)
class UnavailableExternalCapability:
    capability: ExternalCapabilityName
    binding_identity: str
    binding_version: str
    reason_code: str
    status: CapabilityBindingStatus = CapabilityBindingStatus.UNAVAILABLE

    def __post_init__(self) -> None:
        if self.status not in {
            CapabilityBindingStatus.UNAVAILABLE,
            CapabilityBindingStatus.DISABLED,
        }:
            raise PrivateEvalsConfigInvalid()
        for value in (
            self.binding_identity,
            self.binding_version,
            self.reason_code,
        ):
            _validate_safe_reference(value)


@dataclass(frozen=True)
class ExternalClientBinding(Generic[T]):
    capability: ExternalCapabilityName
    binding_identity: str
    binding_version: str
    client: T = field(repr=False)

    def __post_init__(self) -> None:
        _validate_safe_reference(self.binding_identity)
        _validate_safe_reference(self.binding_version)
        if self.client is None:
            raise PrivateEvalsConfigInvalid()

    def __repr__(self) -> str:
        return (
            "ExternalClientBinding("
            f"capability={self.capability!r}, "
            f"binding_identity={self.binding_identity!r}, "
            f"binding_version={self.binding_version!r}, client=<redacted>)"
        )


SecurityBinding = (
    ExternalClientBinding[SecuritySnapshotReadPort] | UnavailableExternalCapability
)
ExecutionBinding = (
    ExternalClientBinding[EvalCaseExecutionPort] | UnavailableExternalCapability
)
EvaluatorBinding = (
    ExternalClientBinding[EvalCaseEvaluatorPort] | UnavailableExternalCapability
)
GovernanceBinding = (
    ExternalClientBinding[RFCEvidenceWritePort] | UnavailableExternalCapability
)


@dataclass(frozen=True)
class PrivateEvalsExternalBindings:
    intelligence_snapshot: SecurityBinding
    case_execution: ExecutionBinding
    case_evaluator: EvaluatorBinding
    governance_write: GovernanceBinding

    def __post_init__(self) -> None:
        expected = (
            (
                self.intelligence_snapshot,
                ExternalCapabilityName.INTELLIGENCE_SNAPSHOT,
                "snapshot",
            ),
            (
                self.case_execution,
                ExternalCapabilityName.CASE_EXECUTION,
                "execute_case",
            ),
            (
                self.case_evaluator,
                ExternalCapabilityName.CASE_EVALUATOR,
                "evaluate",
            ),
            (
                self.governance_write,
                ExternalCapabilityName.GOVERNANCE_WRITE,
                "record_evidence",
            ),
        )
        for binding, capability, method_name in expected:
            if not isinstance(
                binding, (ExternalClientBinding, UnavailableExternalCapability)
            ):
                raise PrivateEvalsConfigInvalid()
            if binding.capability is not capability:
                raise PrivateEvalsConfigInvalid()
            if isinstance(binding, ExternalClientBinding) and not callable(
                getattr(binding.client, method_name, None)
            ):
                raise PrivateEvalsConfigInvalid()


@dataclass(frozen=True)
class PrivateEvalsRuntimeConfig:
    persistence: PrivateEvalsPersistenceConfig
    runtime_identity: str
    runtime_version: str
    intelligence_adapter: ExternalAdapterConfig
    execution_adapter: ExternalAdapterConfig
    evaluator_adapter: ExternalAdapterConfig
    governance_adapter: ExternalAdapterConfig

    def __post_init__(self) -> None:
        if not isinstance(self.persistence, PrivateEvalsPersistenceConfig):
            raise PrivateEvalsConfigInvalid()
        _validate_safe_reference(self.runtime_identity)
        _validate_safe_reference(self.runtime_version)
        if not all(
            isinstance(item, ExternalAdapterConfig)
            for item in (
                self.intelligence_adapter,
                self.execution_adapter,
                self.evaluator_adapter,
                self.governance_adapter,
            )
        ):
            raise PrivateEvalsConfigInvalid()

    def __repr__(self) -> str:
        return (
            "PrivateEvalsRuntimeConfig("
            f"runtime_identity={self.runtime_identity!r}, "
            f"runtime_version={self.runtime_version!r}, "
            f"read_only={self.persistence.read_only!r}, "
            f"expected_schema_version={self.persistence.expected_schema_version!r}, "
            "persistence=<redacted>, adapter_configs=<redacted>)"
        )


@dataclass(frozen=True)
class CapabilityReadiness:
    capability: ExternalCapabilityName
    status: CapabilityBindingStatus
    binding_identity: str
    binding_version: str
    reason_code: str | None


@dataclass(frozen=True)
class PrivateEvalsReadinessSnapshot:
    runtime_identity: str
    runtime_version: str
    lifecycle_state: PrivateEvalsLifecycleState
    persistence_status: CapabilityBindingStatus
    schema_version: int
    read_only: bool
    intelligence_snapshot: CapabilityReadiness
    case_execution: CapabilityReadiness
    case_evaluator: CapabilityReadiness
    governance_write: CapabilityReadiness
    local_queries_available: bool
    commands_available: bool
    limitations: tuple[str, ...]
    backend_globally_ready: bool = False


@dataclass
class _LifecycleGuard:
    closed: bool = False

    def require_open(self) -> None:
        if self.closed:
            raise PrivateEvalsRuntimeClosed()


@dataclass(frozen=True)
class PrivateEvalsQuerySurface:
    _summary: PrivateEvalsRunSummaryQuery = field(repr=False)
    _evidence: SQLiteEvidenceLocalStateReader = field(repr=False)
    _guard: _LifecycleGuard = field(repr=False)

    def run_summary(self, request: RunSummaryRequest) -> RunSummaryResponse:
        self._guard.require_open()
        return self._summary.execute(request)

    def evidence_local_state(self, run_id: EvalRunId) -> EvidenceLocalStateProjection:
        self._guard.require_open()
        return self._evidence.get_local_evidence_state(run_id)


class _UnavailableGovernanceWritePort(RFCEvidenceWritePort):
    def record_evidence(self, evidence: EvidenceRecord) -> EvidenceRecord:
        raise PrivateEvalsCapabilityUnavailable()


ExternalOperationalBinding = (
    IntelligenceSecuritySnapshotAdapter
    | CaseExecutionBoundaryAdapter
    | CaseEvaluatorBoundaryAdapter
    | GovernanceEvidenceWriteAdapter
    | UnavailableExternalCapability
)


class PrivateEvalsRuntimeHandle:
    """Typed owner for one fully constructed Private Evals runtime."""

    def __init__(
        self,
        *,
        config: PrivateEvalsRuntimeConfig,
        bindings: PrivateEvalsExternalBindings,
        catalog_store: SQLiteEvalCatalogStore,
        run_store: SQLiteEvalRunStore,
        analysis_store: SQLiteEvalAnalysisStore,
        materialization_store: SQLiteEvalMaterializationStore,
        evidence_store: SQLiteEvalEvidenceStore,
        catalog_runtime: EvalCatalogRuntime,
        run_runtime: EvalRunRuntime,
        commands: PrivateEvalsCommandHandlers,
        queries: PrivateEvalsQuerySurface,
        intelligence_snapshot: (
            IntelligenceSecuritySnapshotAdapter | UnavailableExternalCapability
        ),
        case_execution: CaseExecutionBoundaryAdapter | UnavailableExternalCapability,
        case_evaluator: CaseEvaluatorBoundaryAdapter | UnavailableExternalCapability,
        governance_write: GovernanceEvidenceWriteAdapter | UnavailableExternalCapability,
        guard: _LifecycleGuard,
    ) -> None:
        self._config = config
        self._bindings = bindings
        self._catalog_store = catalog_store
        self._run_store = run_store
        self._analysis_store = analysis_store
        self._materialization_store = materialization_store
        self._evidence_store = evidence_store
        self._catalog_runtime = catalog_runtime
        self._run_runtime = run_runtime
        self._commands = commands
        self._queries = queries
        self._intelligence_snapshot = intelligence_snapshot
        self._case_execution = case_execution
        self._case_evaluator = case_evaluator
        self._governance_write = governance_write
        self._guard = guard

    @property
    def commands(self) -> PrivateEvalsCommandHandlers:
        self._require_writable()
        return self._commands

    @property
    def queries(self) -> PrivateEvalsQuerySurface:
        self._guard.require_open()
        return self._queries

    @property
    def catalog(self) -> EvalCatalogRuntime:
        self._require_writable()
        return self._catalog_runtime

    @property
    def runs(self) -> EvalRunRuntime:
        self._require_writable()
        return self._run_runtime

    @property
    def intelligence_snapshot(
        self,
    ) -> SecuritySnapshotReadPort:
        self._guard.require_open()
        if isinstance(self._intelligence_snapshot, UnavailableExternalCapability):
            raise PrivateEvalsCapabilityUnavailable()
        return self._intelligence_snapshot

    @property
    def case_execution(
        self,
    ) -> EvalCaseExecutionPort:
        self._guard.require_open()
        if isinstance(self._case_execution, UnavailableExternalCapability):
            raise PrivateEvalsCapabilityUnavailable()
        return self._case_execution

    @property
    def case_evaluator(
        self,
    ) -> EvalCaseEvaluatorPort:
        self._guard.require_open()
        if isinstance(self._case_evaluator, UnavailableExternalCapability):
            raise PrivateEvalsCapabilityUnavailable()
        return self._case_evaluator

    @property
    def governance_write(
        self,
    ) -> RFCEvidenceWritePort:
        self._guard.require_open()
        if isinstance(self._governance_write, UnavailableExternalCapability):
            raise PrivateEvalsCapabilityUnavailable()
        return self._governance_write

    @property
    def readiness(self) -> PrivateEvalsReadinessSnapshot:
        capabilities = tuple(
            _capability_readiness(item)
            for item in (
                self._bindings.intelligence_snapshot,
                self._bindings.case_execution,
                self._bindings.case_evaluator,
                self._bindings.governance_write,
            )
        )
        unavailable = tuple(
            item
            for item in capabilities
            if item.status is CapabilityBindingStatus.UNAVAILABLE
        )
        non_available = tuple(
            item
            for item in capabilities
            if item.status is not CapabilityBindingStatus.AVAILABLE
        )
        limitations = tuple(
            f"{item.capability.value}:{item.reason_code}" for item in non_available
        )
        if self._config.persistence.read_only:
            limitations = (*limitations, "commands:read_only")
        if self._guard.closed:
            state = PrivateEvalsLifecycleState.CLOSED
            limitations = (*limitations, "runtime:closed")
        elif unavailable:
            state = PrivateEvalsLifecycleState.DEGRADED
        elif non_available:
            state = PrivateEvalsLifecycleState.LOCALLY_OPERATIONAL
        else:
            state = PrivateEvalsLifecycleState.EXTERNALLY_BOUND
        return PrivateEvalsReadinessSnapshot(
            runtime_identity=self._config.runtime_identity,
            runtime_version=self._config.runtime_version,
            lifecycle_state=state,
            persistence_status=(
                CapabilityBindingStatus.UNAVAILABLE
                if self._guard.closed
                else CapabilityBindingStatus.AVAILABLE
            ),
            schema_version=SCHEMA_VERSION,
            read_only=self._config.persistence.read_only,
            intelligence_snapshot=capabilities[0],
            case_execution=capabilities[1],
            case_evaluator=capabilities[2],
            governance_write=capabilities[3],
            local_queries_available=not self._guard.closed,
            commands_available=(
                not self._guard.closed and not self._config.persistence.read_only
            ),
            limitations=limitations,
        )

    def close(self) -> None:
        if self._guard.closed:
            return
        self._guard.closed = True
        for store in (
            self._evidence_store,
            self._materialization_store,
            self._analysis_store,
            self._run_store,
            self._catalog_store,
        ):
            store.close()

    def __enter__(self) -> PrivateEvalsRuntimeHandle:
        self._guard.require_open()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()

    def _require_writable(self) -> None:
        self._guard.require_open()
        if self._config.persistence.read_only:
            raise PrivateEvalsRuntimeReadOnly()


def _capability_readiness(
    binding: (
        ExternalClientBinding[SecuritySnapshotReadPort]
        | ExternalClientBinding[EvalCaseExecutionPort]
        | ExternalClientBinding[EvalCaseEvaluatorPort]
        | ExternalClientBinding[RFCEvidenceWritePort]
        | UnavailableExternalCapability
    ),
) -> CapabilityReadiness:
    if isinstance(binding, ExternalClientBinding):
        return CapabilityReadiness(
            binding.capability,
            CapabilityBindingStatus.AVAILABLE,
            binding.binding_identity,
            binding.binding_version,
            None,
        )
    return CapabilityReadiness(
        binding.capability,
        binding.status,
        binding.binding_identity,
        binding.binding_version,
        binding.reason_code,
    )


def compose_private_evals(
    config: PrivateEvalsRuntimeConfig,
    bindings: PrivateEvalsExternalBindings,
    *,
    resolver_records: ResolverRecordCatalog = ResolverRecordCatalog(),
    evidence_coordination: tuple[EvidenceCoordinationReference, ...] = (),
) -> PrivateEvalsRuntimeHandle:
    """Construct a runtime in dependency order and clean up partial construction."""

    if not isinstance(config, PrivateEvalsRuntimeConfig) or not isinstance(
        bindings, PrivateEvalsExternalBindings
    ):
        raise PrivateEvalsConfigInvalid()
    if not isinstance(resolver_records, ResolverRecordCatalog) or not isinstance(
        evidence_coordination, tuple
    ):
        raise PrivateEvalsConfigInvalid()

    opened: list[
        SQLiteEvalCatalogStore
        | SQLiteEvalRunStore
        | SQLiteEvalAnalysisStore
        | SQLiteEvalMaterializationStore
        | SQLiteEvalEvidenceStore
    ] = []
    try:
        catalog_store = SQLiteEvalCatalogStore(config.persistence)
        opened.append(catalog_store)
        run_store = SQLiteEvalRunStore(config.persistence)
        opened.append(run_store)
        analysis_store = SQLiteEvalAnalysisStore(config.persistence)
        opened.append(analysis_store)
        materialization_store = SQLiteEvalMaterializationStore(config.persistence)
        opened.append(materialization_store)
        evidence_store = SQLiteEvalEvidenceStore(config.persistence)
        opened.append(evidence_store)

        resolver = PrivateEvalsCommandResolverAdapter(
            catalog_store,
            run_store,
            analysis_store,
            materialization_store,
            resolver_records,
        )
        evidence_reader = SQLiteEvidenceLocalStateReader(
            evidence_store, evidence_coordination
        )

        intelligence = _bind_intelligence(config, bindings.intelligence_snapshot)
        execution = _bind_execution(config, bindings.case_execution)
        evaluator = _bind_evaluator(config, bindings.case_evaluator)
        governance = _bind_governance(config, bindings.governance_write)
        governance_port: RFCEvidenceWritePort = (
            governance
            if isinstance(governance, GovernanceEvidenceWriteAdapter)
            else _UnavailableGovernanceWritePort()
        )

        catalog_runtime = EvalCatalogRuntime(catalog_store)
        run_runtime = EvalRunRuntime(run_store, catalog_store)
        dependencies = PrivateEvalsCommandDependencies(
            run_runtime=run_runtime,
            materialization_service=MaterializedOutputService(materialization_store),
            result_service=EvalResultService(run_store),
            scoring_service=RunScoringService(analysis_store),
            finalization_service=EvalRunFinalizationService(run_store, run_runtime),
            evidence_submission_service=EvalEvidenceSubmissionService(
                evidence_store, governance_port
            ),
            manifest_resolver=resolver,
            materialization_resolver=resolver,
            evaluation_resolver=resolver,
            scoring_resolver=resolver,
            finalization_resolver=resolver,
            evidence_submission_resolver=resolver,
        )
        commands = PrivateEvalsCommandHandlers(dependencies)
        summary = PrivateEvalsRunSummaryQuery(
            run_runtime, run_store, analysis_store, evidence_reader
        )
        guard = _LifecycleGuard()
        queries = PrivateEvalsQuerySurface(summary, evidence_reader, guard)
        return PrivateEvalsRuntimeHandle(
            config=config,
            bindings=bindings,
            catalog_store=catalog_store,
            run_store=run_store,
            analysis_store=analysis_store,
            materialization_store=materialization_store,
            evidence_store=evidence_store,
            catalog_runtime=catalog_runtime,
            run_runtime=run_runtime,
            commands=commands,
            queries=queries,
            intelligence_snapshot=intelligence,
            case_execution=execution,
            case_evaluator=evaluator,
            governance_write=governance,
            guard=guard,
        )
    except Exception as exc:
        for store in reversed(opened):
            store.close()
        if isinstance(
            exc,
            (
                PrivateEvalsCompositionError,
                EvalStoreError,
            ),
        ):
            raise
        raise PrivateEvalsConstructionFailed() from None


def _bind_intelligence(
    config: PrivateEvalsRuntimeConfig, binding: SecurityBinding
) -> IntelligenceSecuritySnapshotAdapter | UnavailableExternalCapability:
    if isinstance(binding, UnavailableExternalCapability):
        return binding
    return IntelligenceSecuritySnapshotAdapter(
        binding.client, config.intelligence_adapter
    )


def _bind_execution(
    config: PrivateEvalsRuntimeConfig, binding: ExecutionBinding
) -> CaseExecutionBoundaryAdapter | UnavailableExternalCapability:
    if isinstance(binding, UnavailableExternalCapability):
        return binding
    return CaseExecutionBoundaryAdapter(binding.client, config.execution_adapter)


def _bind_evaluator(
    config: PrivateEvalsRuntimeConfig, binding: EvaluatorBinding
) -> CaseEvaluatorBoundaryAdapter | UnavailableExternalCapability:
    if isinstance(binding, UnavailableExternalCapability):
        return binding
    return CaseEvaluatorBoundaryAdapter(binding.client, config.evaluator_adapter)


def _bind_governance(
    config: PrivateEvalsRuntimeConfig, binding: GovernanceBinding
) -> GovernanceEvidenceWriteAdapter | UnavailableExternalCapability:
    if isinstance(binding, UnavailableExternalCapability):
        return binding
    return GovernanceEvidenceWriteAdapter(binding.client, config.governance_adapter)


__all__ = [
    "CapabilityBindingStatus",
    "CapabilityReadiness",
    "ExternalCapabilityName",
    "ExternalClientBinding",
    "PrivateEvalsCapabilityUnavailable",
    "PrivateEvalsCompositionError",
    "PrivateEvalsConfigInvalid",
    "PrivateEvalsConstructionFailed",
    "PrivateEvalsExternalBindings",
    "PrivateEvalsLifecycleState",
    "PrivateEvalsReadinessSnapshot",
    "PrivateEvalsRuntimeClosed",
    "PrivateEvalsRuntimeConfig",
    "PrivateEvalsRuntimeHandle",
    "PrivateEvalsRuntimeReadOnly",
    "UnavailableExternalCapability",
    "compose_private_evals",
]
