from __future__ import annotations

from collections.abc import Callable

from synapse.skills.application.command_handlers import (
    SkillExternalBindingCommandHandler,
    SkillInstallationCommandHandler,
    SkillLifecycleCommandHandler,
    SkillPublicationCommandHandler,
)
from synapse.skills.application.commands import (
    ActivateSkillVersionCommand,
    ApplySkillLifecycleTransitionCommand,
    BindSkillGovernanceDecisionCommand,
    BindSkillIntelligenceFactCommand,
    BindSkillPrivateEvalResultCommand,
    DeactivateSkillVersionCommand,
    InstallSkillVersionCommand,
    PublishSkillVersionCommand,
    TerminateSkillInstallationCommand,
)
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
from synapse.skills.application.query_handlers import (
    SkillBindingQueryHandler,
    SkillCatalogQueryHandler,
    SkillDependencyQueryHandler,
    SkillExecutionHandoffQueryHandler,
    SkillStateQueryHandler,
)
from synapse.skills.application.results import (
    PublishedSkillVersionListResult,
    PublishedSkillVersionView,
    SkillBindingQueryResult,
    SkillCommandResult,
    SkillDependencyAnalysisQueryResult,
    SkillDependencyGraphQueryResult,
    SkillDependencyResolutionQueryResult,
    SkillExecutionHandoffQueryResult,
    SkillInstallationQueryResult,
    SkillLifecycleQueryResult,
)


class SkillsApplicationGateway:
    """Typed synchronous local delivery; it has no transport semantics."""

    def __init__(
        self,
        *,
        ensure_open: Callable[[], None],
        publication: SkillPublicationCommandHandler,
        lifecycle: SkillLifecycleCommandHandler,
        installation: SkillInstallationCommandHandler,
        external_bindings: SkillExternalBindingCommandHandler,
        catalog: SkillCatalogQueryHandler,
        state: SkillStateQueryHandler,
        dependencies: SkillDependencyQueryHandler,
        bindings: SkillBindingQueryHandler,
        handoff: SkillExecutionHandoffQueryHandler,
    ) -> None:
        self._ensure_open = ensure_open
        self._publication = publication
        self._lifecycle = lifecycle
        self._installation = installation
        self._external_bindings = external_bindings
        self._catalog = catalog
        self._state = state
        self._dependencies = dependencies
        self._bindings = bindings
        self._handoff = handoff

    def publish(self, command: PublishSkillVersionCommand) -> SkillCommandResult:
        self._ensure_open()
        return self._publication.handle(command)

    def apply_lifecycle(
        self, command: ApplySkillLifecycleTransitionCommand
    ) -> SkillCommandResult:
        self._ensure_open()
        return self._lifecycle.handle(command)

    def install(self, command: InstallSkillVersionCommand) -> SkillCommandResult:
        self._ensure_open()
        return self._installation.handle_install(command)

    def terminate(
        self, command: TerminateSkillInstallationCommand
    ) -> SkillCommandResult:
        self._ensure_open()
        return self._installation.handle_termination(command)

    def activate(self, command: ActivateSkillVersionCommand) -> SkillCommandResult:
        self._ensure_open()
        return self._installation.handle_activation(command)

    def deactivate(self, command: DeactivateSkillVersionCommand) -> SkillCommandResult:
        self._ensure_open()
        return self._installation.handle_deactivation(command)

    def bind_governance(
        self, command: BindSkillGovernanceDecisionCommand
    ) -> SkillCommandResult:
        self._ensure_open()
        return self._external_bindings.handle_governance(command)

    def bind_intelligence(
        self, command: BindSkillIntelligenceFactCommand
    ) -> SkillCommandResult:
        self._ensure_open()
        return self._external_bindings.handle_intelligence(command)

    def bind_private_eval(
        self, command: BindSkillPrivateEvalResultCommand
    ) -> SkillCommandResult:
        self._ensure_open()
        return self._external_bindings.handle_private_eval(command)

    def get(self, query: GetPublishedSkillVersionQuery) -> PublishedSkillVersionView:
        self._ensure_open()
        return self._catalog.get(query)

    def list(
        self, query: ListPublishedSkillVersionsQuery
    ) -> PublishedSkillVersionListResult:
        self._ensure_open()
        return self._catalog.list(query)

    def lifecycle(
        self, query: GetSkillLifecycleProjectionQuery
    ) -> SkillLifecycleQueryResult:
        self._ensure_open()
        return self._state.lifecycle(query)

    def installation(
        self, query: GetSkillInstallationProjectionQuery
    ) -> SkillInstallationQueryResult:
        self._ensure_open()
        return self._state.installation(query)

    def analyze(
        self, query: AnalyzeSkillDependenciesQuery
    ) -> SkillDependencyAnalysisQueryResult:
        self._ensure_open()
        return self._dependencies.analyze(query)

    def graph(
        self, query: AnalyzeSkillDependencyGraphQuery
    ) -> SkillDependencyGraphQueryResult:
        self._ensure_open()
        return self._dependencies.graph(query)

    def resolve(
        self, query: ResolveSkillDependenciesQuery
    ) -> SkillDependencyResolutionQueryResult:
        self._ensure_open()
        return self._dependencies.resolve(query)

    def governance(
        self, query: GetSkillGovernanceBindingsQuery
    ) -> SkillBindingQueryResult:
        self._ensure_open()
        return self._bindings.governance(query)

    def intelligence(
        self, query: GetSkillIntelligenceBindingsQuery
    ) -> SkillBindingQueryResult:
        self._ensure_open()
        return self._bindings.intelligence(query)

    def private_evals(
        self, query: GetSkillPrivateEvalBindingsQuery
    ) -> SkillBindingQueryResult:
        self._ensure_open()
        return self._bindings.private_evals(query)

    def build_handoff(
        self, query: BuildSkillExecutionHandoffQuery
    ) -> SkillExecutionHandoffQueryResult:
        self._ensure_open()
        return self._handoff.build(query)
