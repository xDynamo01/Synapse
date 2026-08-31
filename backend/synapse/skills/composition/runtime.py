from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock

from synapse.skills.application.command_handlers import (
    SkillExternalBindingCommandHandler,
    SkillInstallationCommandHandler,
    SkillLifecycleCommandHandler,
    SkillPublicationCommandHandler,
)
from synapse.skills.application.query_handlers import (
    SkillBindingQueryHandler,
    SkillCatalogQueryHandler,
    SkillDependencyQueryHandler,
    SkillExecutionHandoffQueryHandler,
    SkillStateQueryHandler,
)
from synapse.skills.compatibility import (
    LegacyCatalogAdapter,
    LegacyLifecycleAdapter,
    LegacyLifecycleView,
    LegacySkillListResult,
    LegacySkillLookup,
    LegacySkillLookupResult,
    LegacySkillView,
)
from synapse.skills.persistence import (
    SkillPersistenceIntegrityChecker,
    SkillPersistenceMigrator,
    SkillSQLiteConnectionFactory,
    SQLiteSkillAssignmentStore,
    SQLiteSkillBindingStore,
    SQLiteSkillCatalogStore,
    SQLiteSkillExternalBindingStore,
    SQLiteSkillInstallationStore,
    SQLiteSkillLeaseStore,
    SQLiteSkillLifecycleStore,
    SQLiteSkillPrivateEvalBindingStore,
)
from synapse.skills.persistence.errors import (
    SkillPersistenceDatabaseCorrupt,
    SkillPersistenceMigrationChecksumMismatch,
    SkillPersistenceMigrationFailed,
    SkillPersistenceMigrationRequired,
    SkillPersistenceSchemaUnsupported,
    SkillPersistenceUnavailable,
)
from synapse.skills.phase2_models import PublishedSkillVersionId
from synapse.skills.phase5_publication import SkillPublicationService
from synapse.skills.phase6_lifecycle import SkillLifecycleService
from synapse.skills.phase7_installation import (
    SkillActivationService,
    SkillInstallationParentVerifier,
    SkillInstallationService,
    SkillInstallationTerminationService,
)
from synapse.skills.phase8_analysis import SkillDependencyAnalysisService
from synapse.skills.phase8_graph import SkillDependencyGraphAnalysisService
from synapse.skills.phase9_resolution import SkillDependencyResolutionService
from synapse.skills.phase10_governance import SkillGovernanceBindingService
from synapse.skills.phase10_intelligence import SkillIntelligenceBindingService
from synapse.skills.phase11_bindings import SkillPrivateEvalBindingService
from synapse.skills.phase12_handoff import SkillExecutionHandoffService

from .errors import (
    SkillsCompositionChecksumMismatch,
    SkillsCompositionClosed,
    SkillsCompositionCompatibilityUnavailable,
    SkillsCompositionConstructionFailed,
    SkillsCompositionDatabaseUnavailable,
    SkillsCompositionIntegrityFailed,
    SkillsCompositionMigrationFailed,
    SkillsCompositionMigrationRequired,
    SkillsCompositionSchemaUnsupported,
)
from .gateway import SkillsApplicationGateway
from .models import (
    SkillsCompatibilityMode,
    SkillsHealthResult,
    SkillsHealthStatus,
    SkillsIntegrityPolicy,
    SkillsMigrationPolicy,
    SkillsMigrationStatus,
    SkillsRuntimeConfiguration,
    SkillsRuntimeConfigurationView,
    SkillsRuntimeState,
)


class SkillsCompatibilityGateway:
    def __init__(
        self,
        ensure_open: object,
        catalog: LegacyCatalogAdapter,
        lifecycle: LegacyLifecycleAdapter,
    ) -> None:
        if not callable(ensure_open):
            raise SkillsCompositionConstructionFailed()
        self._ensure_open = ensure_open
        self._catalog = catalog
        self._lifecycle = lifecycle

    def get_exact(self, identity: PublishedSkillVersionId) -> LegacySkillView:
        self._ensure_open()
        return self._catalog.get_exact(identity)

    def get(self, request: LegacySkillLookup) -> LegacySkillLookupResult:
        self._ensure_open()
        return self._catalog.get(request)

    def list(self, skill_id: str) -> LegacySkillListResult:
        self._ensure_open()
        return self._catalog.list(skill_id)

    def state(self, identity: PublishedSkillVersionId) -> LegacyLifecycleView:
        self._ensure_open()
        return self._lifecycle.state(identity)


class SkillsRuntimeComposition:
    def __init__(
        self,
        configuration: SkillsRuntimeConfiguration,
        gateway: SkillsApplicationGateway,
        integrity: SkillPersistenceIntegrityChecker,
        connections: SkillSQLiteConnectionFactory,
        compatibility: SkillsCompatibilityGateway | None,
        migration: SkillsMigrationStatus,
        resources: tuple[object, ...],
    ) -> None:
        self._configuration = configuration
        self._gateway = gateway
        self._integrity = integrity
        self._connections = connections
        self._compatibility = compatibility
        self._migration = migration
        self._integrity_checked = (
            configuration.integrity is SkillsIntegrityPolicy.FULL
        )
        self._resources = resources
        self._state = SkillsRuntimeState.READY
        self._lock = Lock()

    @property
    def configuration(self) -> SkillsRuntimeConfigurationView:
        self._ensure_open()
        return SkillsRuntimeConfigurationView(
            self._configuration.migration,
            self._configuration.integrity,
            self._configuration.compatibility,
            self._configuration.binding_history_limit,
        )

    @property
    def state(self) -> SkillsRuntimeState:
        with self._lock:
            return self._state

    @property
    def gateway(self) -> SkillsApplicationGateway:
        self._ensure_open()
        return self._gateway

    @property
    def compatibility(self) -> SkillsCompatibilityGateway:
        self._ensure_open()
        if self._compatibility is None:
            raise SkillsCompositionCompatibilityUnavailable()
        return self._compatibility

    def health(self) -> SkillsHealthResult:
        if self.state is SkillsRuntimeState.CLOSED:
            return self._health(SkillsHealthStatus.CLOSED, SkillsHealthStatus.NOT_CHECKED)
        try:
            with self._connections.connection() as connection:
                connection.execute("SELECT 1").fetchone()
        except Exception:
            return SkillsHealthResult(
                status=SkillsHealthStatus.UNAVAILABLE,
                configuration_valid=True,
                schema_current=False,
                migration=self._migration,
                database_reachable=False,
                integrity=SkillsHealthStatus.NOT_CHECKED,
                foreign_keys=SkillsHealthStatus.NOT_CHECKED,
                application_constructed=True,
                compatibility_enabled=self._compatibility is not None,
                runtime_state=self.state,
            )
        integrity = (
            SkillsHealthStatus.HEALTHY
            if self._integrity_checked
            else SkillsHealthStatus.NOT_CHECKED
        )
        return self._health(SkillsHealthStatus.HEALTHY, integrity)

    def verify_integrity(self) -> SkillsHealthResult:
        self._ensure_open()
        try:
            self._integrity.check()
        except Exception as exc:
            raise SkillsCompositionIntegrityFailed() from exc
        with self._lock:
            self._integrity_checked = True
        return self._health(SkillsHealthStatus.HEALTHY, SkillsHealthStatus.HEALTHY)

    def close(self) -> None:
        with self._lock:
            self._state = SkillsRuntimeState.CLOSED

    def __enter__(self) -> SkillsRuntimeComposition:
        self._ensure_open()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _ensure_open(self) -> None:
        if self.state is SkillsRuntimeState.CLOSED:
            raise SkillsCompositionClosed()

    def _health(
        self,
        status: SkillsHealthStatus,
        integrity: SkillsHealthStatus,
    ) -> SkillsHealthResult:
        ready = self.state is SkillsRuntimeState.READY
        return SkillsHealthResult(
            status=status,
            configuration_valid=True,
            schema_current=ready,
            migration=self._migration,
            database_reachable=ready,
            integrity=integrity,
            foreign_keys=integrity,
            application_constructed=ready,
            compatibility_enabled=self._compatibility is not None,
            runtime_state=self.state,
        )


def build_skills_runtime(
    configuration: SkillsRuntimeConfiguration,
) -> SkillsRuntimeComposition:
    try:
        connections = SkillSQLiteConnectionFactory(configuration.database)
        migrator = SkillPersistenceMigrator(
            connections, lambda: datetime.now(UTC)
        )
        if configuration.migration is SkillsMigrationPolicy.MIGRATE_IF_NEEDED:
            try:
                migrator.verify()
                migration = SkillsMigrationStatus.CURRENT_VERIFIED
            except SkillPersistenceMigrationRequired:
                migrator.migrate()
                migration = SkillsMigrationStatus.APPLIED
        else:
            migrator.verify()
            migration = SkillsMigrationStatus.CURRENT_VERIFIED
        integrity = SkillPersistenceIntegrityChecker(connections)
    except SkillPersistenceMigrationRequired as exc:
        raise SkillsCompositionMigrationRequired() from exc
    except SkillPersistenceSchemaUnsupported as exc:
        raise SkillsCompositionSchemaUnsupported() from exc
    except SkillPersistenceMigrationChecksumMismatch as exc:
        raise SkillsCompositionChecksumMismatch() from exc
    except SkillPersistenceUnavailable as exc:
        raise SkillsCompositionDatabaseUnavailable() from exc
    except SkillPersistenceDatabaseCorrupt as exc:
        raise SkillsCompositionIntegrityFailed() from exc
    except SkillPersistenceMigrationFailed as exc:
        raise SkillsCompositionMigrationFailed() from exc
    except Exception as exc:
        raise SkillsCompositionMigrationFailed() from exc
    if configuration.integrity is SkillsIntegrityPolicy.FULL:
        try:
            integrity.check()
        except Exception as exc:
            raise SkillsCompositionIntegrityFailed() from exc

    try:
        catalog_store = SQLiteSkillCatalogStore(connections)
        lifecycle_store = SQLiteSkillLifecycleStore(connections)
        installation_store = SQLiteSkillInstallationStore(connections)
        assignment_store = SQLiteSkillAssignmentStore(connections)
        lease_store = SQLiteSkillLeaseStore(connections)
        legacy_binding_store = SQLiteSkillBindingStore(connections)
        external_store = SQLiteSkillExternalBindingStore(connections)
        private_eval_store = SQLiteSkillPrivateEvalBindingStore(connections)

        publication = SkillPublicationService(catalog_store)
        installation = SkillInstallationService(catalog_store, installation_store)
        installation_parent = SkillInstallationParentVerifier(installation)
        lifecycle = SkillLifecycleService(
            catalog_store, lifecycle_store, installation_parent
        )
        termination = SkillInstallationTerminationService(
            installation, installation_store, lifecycle
        )
        activation = SkillActivationService(installation, installation_parent, lifecycle)
        dependency_analysis = SkillDependencyAnalysisService(catalog_store, lifecycle)
        dependency_graph = SkillDependencyGraphAnalysisService()
        dependency_resolution = SkillDependencyResolutionService()
        governance = SkillGovernanceBindingService(
            catalog_store, external_store, configuration.binding_history_limit
        )
        intelligence = SkillIntelligenceBindingService(
            catalog_store, external_store, configuration.binding_history_limit
        )
        private_evals = SkillPrivateEvalBindingService(
            catalog_store, private_eval_store, configuration.binding_history_limit
        )
        handoff = SkillExecutionHandoffService()

        publication_commands = SkillPublicationCommandHandler(publication)
        lifecycle_commands = SkillLifecycleCommandHandler(lifecycle)
        installation_commands = SkillInstallationCommandHandler(
            installation, termination, activation
        )
        binding_commands = SkillExternalBindingCommandHandler(
            governance, intelligence, private_evals
        )
        catalog_queries = SkillCatalogQueryHandler(publication)
        state_queries = SkillStateQueryHandler(lifecycle, installation)
        dependency_queries = SkillDependencyQueryHandler(
            dependency_analysis, dependency_graph, dependency_resolution
        )
        binding_queries = SkillBindingQueryHandler(
            governance, intelligence, private_evals
        )
        handoff_queries = SkillExecutionHandoffQueryHandler(handoff)
    except Exception as exc:
        raise SkillsCompositionConstructionFailed() from exc

    holder: list[SkillsRuntimeComposition] = []

    def ensure_open() -> None:
        if not holder:
            raise SkillsCompositionConstructionFailed()
        holder[0]._ensure_open()

    try:
        gateway = SkillsApplicationGateway(
            ensure_open=ensure_open,
            publication=publication_commands,
            lifecycle=lifecycle_commands,
            installation=installation_commands,
            external_bindings=binding_commands,
            catalog=catalog_queries,
            state=state_queries,
            dependencies=dependency_queries,
            bindings=binding_queries,
            handoff=handoff_queries,
        )
        compatibility = (
            SkillsCompatibilityGateway(
                ensure_open,
                LegacyCatalogAdapter(catalog_queries),
                LegacyLifecycleAdapter(state_queries),
            )
            if configuration.compatibility is SkillsCompatibilityMode.READ_ONLY
            else None
        )
    except Exception as exc:
        raise SkillsCompositionConstructionFailed() from exc
    composition = SkillsRuntimeComposition(
        configuration,
        gateway,
        integrity,
        connections,
        compatibility,
        migration,
        (
            connections,
            catalog_store,
            lifecycle_store,
            installation_store,
            assignment_store,
            lease_store,
            legacy_binding_store,
            external_store,
            private_eval_store,
        ),
    )
    holder.append(composition)
    return composition
