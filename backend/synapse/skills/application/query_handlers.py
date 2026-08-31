from __future__ import annotations

from synapse.skills.application.queries import (
    AnalyzeSkillDependenciesQuery,
    AnalyzeSkillDependencyGraphQuery,
    BuildSkillExecutionHandoffQuery,
    GetPublishedSkillVersionQuery,
    GetSkillGovernanceBindingsQuery,
    GetSkillInstallationProjectionQuery,
    GetSkillIntelligenceBindingsQuery,
    GetSkillLifecycleProjectionQuery,
    GetSkillPrivateEvalBindingsQuery,
    ListPublishedSkillVersionsQuery,
    ResolveSkillDependenciesQuery,
)
from synapse.skills.application.results import (
    PublishedSkillVersionListResult,
    PublishedSkillVersionView,
    SkillApplicationBindingFamily,
    SkillApplicationCompleteness,
    SkillBindingQueryResult,
    SkillDependencyAnalysisQueryResult,
    SkillDependencyGraphQueryResult,
    SkillDependencyResolutionQueryResult,
    SkillExecutionHandoffQueryResult,
    SkillInstallationQueryResult,
    SkillLifecycleQueryResult,
)
from synapse.skills.phase3_records import PublishedSkillVersionRecord
from synapse.skills.phase5_errors import SkillPublicationError
from synapse.skills.phase5_publication import SkillPublicationService
from synapse.skills.phase6_errors import SkillLifecycleError
from synapse.skills.phase6_lifecycle import SkillLifecycleService
from synapse.skills.phase7_errors import SkillInstallationError
from synapse.skills.phase7_installation import SkillInstallationService
from synapse.skills.phase8_analysis import SkillDependencyAnalysisService
from synapse.skills.phase8_errors import SkillDependencyAnalysisError
from synapse.skills.phase8_graph import SkillDependencyGraphAnalysisService
from synapse.skills.phase9_errors import SkillDependencyResolutionError
from synapse.skills.phase9_resolution import SkillDependencyResolutionService
from synapse.skills.phase10_errors import SkillExternalBindingError
from synapse.skills.phase10_governance import SkillGovernanceBindingService
from synapse.skills.phase10_intelligence import SkillIntelligenceBindingService
from synapse.skills.phase10_models import (
    SkillGovernanceBindingProjection,
    SkillIntelligenceBindingProjection,
)
from synapse.skills.phase11_bindings import SkillPrivateEvalBindingService
from synapse.skills.phase11_errors import SkillPrivateEvalBindingError
from synapse.skills.phase11_models import SkillPrivateEvalBindingProjection
from synapse.skills.phase12_errors import SkillExecutionHandoffError
from synapse.skills.phase12_handoff import SkillExecutionHandoffService

from .command_handlers import _translate


class SkillCatalogQueryHandler:
    def __init__(self, service: SkillPublicationService) -> None:
        self._service = service

    def get(self, query: GetPublishedSkillVersionQuery) -> PublishedSkillVersionView:
        try:
            record = self._service.get_exact(query.identity)
        except SkillPublicationError as exc:
            raise _translate(exc) from exc
        return _published_view(record)

    def list(
        self, query: ListPublishedSkillVersionsQuery
    ) -> PublishedSkillVersionListResult:
        try:
            records = self._service.list_versions(query.skill_id, query.limit)
        except SkillPublicationError as exc:
            raise _translate(exc) from exc
        return PublishedSkillVersionListResult(
            tuple(_published_view(record) for record in records),
            SkillApplicationCompleteness.UNKNOWN,
        )


class SkillStateQueryHandler:
    def __init__(
        self,
        lifecycle: SkillLifecycleService,
        installation: SkillInstallationService,
    ) -> None:
        self._lifecycle = lifecycle
        self._installation = installation

    def lifecycle(
        self, query: GetSkillLifecycleProjectionQuery
    ) -> SkillLifecycleQueryResult:
        try:
            value = self._lifecycle.projection(query.identity)
        except SkillLifecycleError as exc:
            raise _translate(exc) from exc
        return SkillLifecycleQueryResult(
            value,
            SkillApplicationCompleteness.COMPLETE,
        )

    def installation(
        self, query: GetSkillInstallationProjectionQuery
    ) -> SkillInstallationQueryResult:
        try:
            value = self._installation.projection(query.identity)
        except SkillInstallationError as exc:
            raise _translate(exc) from exc
        completeness = (
            SkillApplicationCompleteness.COMPLETE
            if value.complete
            else SkillApplicationCompleteness.INCOMPLETE
        )
        return SkillInstallationQueryResult(
            value,
            completeness,
        )


class SkillDependencyQueryHandler:
    def __init__(
        self,
        analysis: SkillDependencyAnalysisService,
        graph: SkillDependencyGraphAnalysisService,
        resolution: SkillDependencyResolutionService,
    ) -> None:
        self._analysis = analysis
        self._graph = graph
        self._resolution = resolution

    def analyze(
        self, query: AnalyzeSkillDependenciesQuery
    ) -> SkillDependencyAnalysisQueryResult:
        try:
            return SkillDependencyAnalysisQueryResult(
                self._analysis.analyze(query.request)
            )
        except SkillDependencyAnalysisError as exc:
            raise _translate(exc) from exc

    def graph(
        self, query: AnalyzeSkillDependencyGraphQuery
    ) -> SkillDependencyGraphQueryResult:
        try:
            return SkillDependencyGraphQueryResult(
                self._graph.analyze(query.request)
            )
        except SkillDependencyAnalysisError as exc:
            raise _translate(exc) from exc

    def resolve(
        self, query: ResolveSkillDependenciesQuery
    ) -> SkillDependencyResolutionQueryResult:
        try:
            return SkillDependencyResolutionQueryResult(
                self._resolution.resolve(query.request)
            )
        except SkillDependencyResolutionError as exc:
            raise _translate(exc) from exc


class SkillBindingQueryHandler:
    def __init__(
        self,
        governance: SkillGovernanceBindingService,
        intelligence: SkillIntelligenceBindingService,
        private_evals: SkillPrivateEvalBindingService,
    ) -> None:
        self._governance = governance
        self._intelligence = intelligence
        self._private_evals = private_evals

    def governance(
        self, query: GetSkillGovernanceBindingsQuery
    ) -> SkillBindingQueryResult:
        try:
            value = self._governance.projection(query.identity)
        except SkillExternalBindingError as exc:
            raise _translate(exc) from exc
        return _binding_result(
            SkillApplicationBindingFamily.GOVERNANCE,
            value,
        )

    def intelligence(
        self, query: GetSkillIntelligenceBindingsQuery
    ) -> SkillBindingQueryResult:
        try:
            value = self._intelligence.projection(query.identity)
        except SkillExternalBindingError as exc:
            raise _translate(exc) from exc
        return _binding_result(
            SkillApplicationBindingFamily.INTELLIGENCE,
            value,
        )

    def private_evals(
        self, query: GetSkillPrivateEvalBindingsQuery
    ) -> SkillBindingQueryResult:
        try:
            value = self._private_evals.projection(query.identity)
        except SkillPrivateEvalBindingError as exc:
            raise _translate(exc) from exc
        return _binding_result(
            SkillApplicationBindingFamily.PRIVATE_EVALS,
            value,
        )


class SkillExecutionHandoffQueryHandler:
    def __init__(self, service: SkillExecutionHandoffService) -> None:
        self._service = service

    def build(
        self, query: BuildSkillExecutionHandoffQuery
    ) -> SkillExecutionHandoffQueryResult:
        try:
            return SkillExecutionHandoffQueryResult(
                self._service.build(query.request)
            )
        except SkillExecutionHandoffError as exc:
            raise _translate(exc) from exc


def _published_view(record: PublishedSkillVersionRecord) -> PublishedSkillVersionView:
    return PublishedSkillVersionView(record)


def _binding_result(
    family: SkillApplicationBindingFamily,
    projection: (
        SkillGovernanceBindingProjection
        | SkillIntelligenceBindingProjection
        | SkillPrivateEvalBindingProjection
    ),
) -> SkillBindingQueryResult:
    return SkillBindingQueryResult(
        family,
        projection,
        (
            SkillApplicationCompleteness.COMPLETE
            if projection.complete
            else SkillApplicationCompleteness.INCOMPLETE
        ),
    )
