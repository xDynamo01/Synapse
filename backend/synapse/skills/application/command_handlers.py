from __future__ import annotations

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
from synapse.skills.application.errors import (
    SkillApplicationConflict,
    SkillApplicationDependencyUnavailable,
    SkillApplicationError,
    SkillApplicationIncomplete,
    SkillApplicationInvalidInput,
    SkillApplicationNotFound,
)
from synapse.skills.application.results import (
    SkillApplicationMutationOutcome,
    SkillCommandResult,
)
from synapse.skills.phase5_errors import (
    InvalidSkillPublicationRequest,
    PublishedSkillVersionNotFound,
    SkillPublicationCatalogUnavailable,
    SkillPublicationConflict,
    SkillPublicationError,
    SkillPublicationSnapshotMismatch,
)
from synapse.skills.phase5_models import SkillPublicationOutcome
from synapse.skills.phase5_publication import SkillPublicationService
from synapse.skills.phase6_errors import (
    AmbiguousSkillLifecycleOrdering,
    CorruptedSkillLifecycleHistory,
    IncompleteSkillLifecycleHistory,
    InvalidSkillActivationParent,
    InvalidSkillLifecycleRequest,
    InvalidSkillLifecycleTransition,
    InvalidSkillRollbackTarget,
    InvalidSkillSupersessionTarget,
    MissingLifecycleDecisionReference,
    RevokedSkillVersion,
    SkillLifecycleConflict,
    SkillLifecycleError,
    SkillLifecycleStoreUnavailable,
    SkillVersionNotPublished,
)
from synapse.skills.phase6_lifecycle import SkillLifecycleService
from synapse.skills.phase6_models import (
    DeactivateSkillVersionRequest,
    DeprecateSkillVersionRequest,
    ReenableSkillVersionRequest,
    RevokeSkillVersionRequest,
    RollbackSkillVersionRequest,
    SkillLifecycleOutcome,
    SupersedeSkillVersionRequest,
)
from synapse.skills.phase7_errors import (
    ActiveSkillInstallationTerminationForbidden,
    AmbiguousSkillInstallationOrdering,
    CorruptedSkillInstallationHistory,
    IncompleteSkillInstallationHistory,
    InvalidOperationalActivationParent,
    InvalidOperationalActivationTransition,
    InvalidSkillInstallationRequest,
    SkillInstallationConflict,
    SkillInstallationCorrupted,
    SkillInstallationError,
    SkillInstallationNotFound,
    SkillInstallationSnapshotMismatch,
    SkillInstallationStoreUnavailable,
    SkillInstallationTerminated,
    SkillInstallationVersionNotPublished,
)
from synapse.skills.phase7_installation import (
    SkillActivationService,
    SkillInstallationService,
    SkillInstallationTerminationService,
)
from synapse.skills.phase7_models import SkillInstallationOutcome
from synapse.skills.phase8_errors import (
    InconsistentSkillDependencyCatalog,
    InconsistentSkillDependencyGraph,
    InvalidSkillCompatibilityObservation,
    InvalidSkillDependencyAnalysisProfile,
    InvalidSkillDependencyDeclaration,
    InvalidSkillDependencyGraphInput,
    SkillDependencyCatalogUnavailable,
    SkillDependencySubjectNotPublished,
)
from synapse.skills.phase9_errors import (
    InconsistentSkillDependencyAnalysis,
    InconsistentSkillResolutionGraph,
    InvalidSkillDependencyResolutionPolicy,
    InvalidSkillDependencyResolutionRequest,
    SkillDependencyResolutionInvariantError,
)
from synapse.skills.phase10_errors import (
    IncompleteSkillExternalBindingHistory,
    InvalidSkillExternalBindingHistory,
    InvalidSkillExternalBindingRequest,
    InvalidSkillExternalReference,
    SkillExternalBindingCorrespondenceMismatch,
    SkillExternalBindingDivergentDuplicate,
    SkillExternalBindingError,
    SkillExternalBindingStoreUnavailable,
    SkillExternalBindingSubjectNotPublished,
)
from synapse.skills.phase10_governance import SkillGovernanceBindingService
from synapse.skills.phase10_intelligence import SkillIntelligenceBindingService
from synapse.skills.phase10_models import SkillExternalBindingOutcome
from synapse.skills.phase11_bindings import SkillPrivateEvalBindingService
from synapse.skills.phase11_errors import (
    IncompleteSkillPrivateEvalBindingHistory,
    InvalidSkillPrivateEvalBindingHistory,
    InvalidSkillPrivateEvalBindingRequest,
    InvalidSkillPrivateEvalGranularity,
    InvalidSkillPrivateEvalReference,
    InvalidSkillPrivateEvalTemporalRelation,
    SkillPrivateEvalBindingCorrespondenceMismatch,
    SkillPrivateEvalBindingDivergentDuplicate,
    SkillPrivateEvalBindingError,
    SkillPrivateEvalBindingStoreUnavailable,
    SkillPrivateEvalBindingSubjectNotPublished,
)
from synapse.skills.phase11_models import SkillPrivateEvalBindingOutcome
from synapse.skills.phase12_errors import SkillExecutionHandoffError


class SkillPublicationCommandHandler:
    def __init__(self, service: SkillPublicationService) -> None:
        self._service = service

    def handle(self, command: PublishSkillVersionCommand) -> SkillCommandResult:
        try:
            result = self._service.publish(command.request)
        except SkillPublicationError as exc:
            raise _translate(exc) from exc
        return SkillCommandResult(result.identity, _outcome(result.outcome))


class SkillLifecycleCommandHandler:
    def __init__(self, service: SkillLifecycleService) -> None:
        self._service = service

    def handle(
        self, command: ApplySkillLifecycleTransitionCommand
    ) -> SkillCommandResult:
        request = command.request
        try:
            if isinstance(request, DeactivateSkillVersionRequest):
                result = self._service.deactivate(request)
            elif isinstance(request, DeprecateSkillVersionRequest):
                result = self._service.deprecate(request)
            elif isinstance(request, ReenableSkillVersionRequest):
                result = self._service.reenable(request)
            elif isinstance(request, SupersedeSkillVersionRequest):
                result = self._service.supersede(request)
            elif isinstance(request, RollbackSkillVersionRequest):
                result = self._service.rollback(request)
            elif isinstance(request, RevokeSkillVersionRequest):
                result = self._service.revoke(request)
            else:
                raise SkillApplicationInvalidInput()
        except SkillLifecycleError as exc:
            raise _translate(exc) from exc
        return SkillCommandResult(result.identity, _outcome(result.outcome))


class SkillInstallationCommandHandler:
    def __init__(
        self,
        installation: SkillInstallationService,
        termination: SkillInstallationTerminationService,
        activation: SkillActivationService,
    ) -> None:
        self._installation = installation
        self._termination = termination
        self._activation = activation

    def handle_install(self, command: InstallSkillVersionCommand) -> SkillCommandResult:
        try:
            result = self._installation.install(command.request)
        except SkillInstallationError as exc:
            raise _translate(exc) from exc
        return SkillCommandResult(result.identity, _outcome(result.outcome))

    def handle_termination(
        self, command: TerminateSkillInstallationCommand
    ) -> SkillCommandResult:
        try:
            result = self._termination.terminate(command.request)
        except SkillInstallationError as exc:
            raise _translate(exc) from exc
        return SkillCommandResult(result.identity, _outcome(result.outcome))

    def handle_activation(
        self, command: ActivateSkillVersionCommand
    ) -> SkillCommandResult:
        try:
            result = self._activation.activate(command.request)
        except (SkillInstallationError, SkillLifecycleError) as exc:
            raise _translate(exc) from exc
        return SkillCommandResult(result.identity, _outcome(result.outcome))

    def handle_deactivation(
        self, command: DeactivateSkillVersionCommand
    ) -> SkillCommandResult:
        try:
            result = self._activation.deactivate(command.request)
        except (SkillInstallationError, SkillLifecycleError) as exc:
            raise _translate(exc) from exc
        return SkillCommandResult(result.identity, _outcome(result.outcome))


class SkillExternalBindingCommandHandler:
    def __init__(
        self,
        governance: SkillGovernanceBindingService,
        intelligence: SkillIntelligenceBindingService,
        private_evals: SkillPrivateEvalBindingService,
    ) -> None:
        self._governance = governance
        self._intelligence = intelligence
        self._private_evals = private_evals

    def handle_governance(
        self, command: BindSkillGovernanceDecisionCommand
    ) -> SkillCommandResult:
        try:
            result = self._governance.bind(command.request)
        except SkillExternalBindingError as exc:
            raise _translate(exc) from exc
        return SkillCommandResult(result.identity, _outcome(result.outcome))

    def handle_intelligence(
        self, command: BindSkillIntelligenceFactCommand
    ) -> SkillCommandResult:
        try:
            result = self._intelligence.bind(command.request)
        except SkillExternalBindingError as exc:
            raise _translate(exc) from exc
        return SkillCommandResult(result.identity, _outcome(result.outcome))

    def handle_private_eval(
        self, command: BindSkillPrivateEvalResultCommand
    ) -> SkillCommandResult:
        try:
            result = self._private_evals.bind(command.request)
        except SkillPrivateEvalBindingError as exc:
            raise _translate(exc) from exc
        return SkillCommandResult(result.identity, _outcome(result.outcome))


_DomainMutationOutcome = (
    SkillPublicationOutcome
    | SkillLifecycleOutcome
    | SkillInstallationOutcome
    | SkillExternalBindingOutcome
    | SkillPrivateEvalBindingOutcome
)


def _outcome(value: _DomainMutationOutcome) -> SkillApplicationMutationOutcome:
    if value in {
        SkillPublicationOutcome.IDEMPOTENT_REPLAY,
        SkillLifecycleOutcome.IDEMPOTENT_REPLAY,
        SkillInstallationOutcome.IDEMPOTENT_REPLAY,
        SkillExternalBindingOutcome.IDEMPOTENT_REPLAY,
        SkillPrivateEvalBindingOutcome.IDEMPOTENT_REPLAY,
    }:
        return SkillApplicationMutationOutcome.REPLAYED
    return SkillApplicationMutationOutcome.CREATED


def _translate(error: Exception) -> SkillApplicationError:
    if isinstance(
        error,
        (
            PublishedSkillVersionNotFound,
            SkillVersionNotPublished,
            SkillInstallationNotFound,
            SkillInstallationVersionNotPublished,
            SkillDependencySubjectNotPublished,
            SkillExternalBindingSubjectNotPublished,
            SkillPrivateEvalBindingSubjectNotPublished,
        ),
    ):
        return SkillApplicationNotFound()
    if isinstance(
        error,
        (
            SkillPublicationCatalogUnavailable,
            SkillLifecycleStoreUnavailable,
            SkillInstallationStoreUnavailable,
            SkillExternalBindingStoreUnavailable,
            SkillPrivateEvalBindingStoreUnavailable,
            SkillDependencyCatalogUnavailable,
        ),
    ):
        return SkillApplicationDependencyUnavailable()
    if isinstance(
        error,
        (
            IncompleteSkillLifecycleHistory,
            IncompleteSkillInstallationHistory,
            IncompleteSkillExternalBindingHistory,
            IncompleteSkillPrivateEvalBindingHistory,
        ),
    ):
        return SkillApplicationIncomplete()
    if isinstance(
        error,
        (
            SkillPublicationConflict,
            SkillLifecycleConflict,
            SkillInstallationConflict,
            SkillExternalBindingDivergentDuplicate,
            SkillPrivateEvalBindingDivergentDuplicate,
            CorruptedSkillLifecycleHistory,
            AmbiguousSkillLifecycleOrdering,
            CorruptedSkillInstallationHistory,
            AmbiguousSkillInstallationOrdering,
            InvalidSkillExternalBindingHistory,
            InvalidSkillPrivateEvalBindingHistory,
            InconsistentSkillDependencyCatalog,
            InconsistentSkillDependencyGraph,
            InconsistentSkillDependencyAnalysis,
            InconsistentSkillResolutionGraph,
            SkillDependencyResolutionInvariantError,
        ),
    ):
        return SkillApplicationConflict()
    if isinstance(
        error,
        (
            InvalidSkillPublicationRequest,
            SkillPublicationSnapshotMismatch,
            InvalidSkillLifecycleRequest,
            InvalidSkillLifecycleTransition,
            MissingLifecycleDecisionReference,
            RevokedSkillVersion,
            InvalidSkillSupersessionTarget,
            InvalidSkillRollbackTarget,
            InvalidSkillActivationParent,
            InvalidSkillInstallationRequest,
            SkillInstallationSnapshotMismatch,
            SkillInstallationTerminated,
            SkillInstallationCorrupted,
            ActiveSkillInstallationTerminationForbidden,
            InvalidOperationalActivationParent,
            InvalidOperationalActivationTransition,
            InvalidSkillExternalBindingRequest,
            InvalidSkillExternalReference,
            SkillExternalBindingCorrespondenceMismatch,
            InvalidSkillPrivateEvalBindingRequest,
            InvalidSkillPrivateEvalReference,
            InvalidSkillPrivateEvalGranularity,
            InvalidSkillPrivateEvalTemporalRelation,
            SkillPrivateEvalBindingCorrespondenceMismatch,
            InvalidSkillDependencyDeclaration,
            InvalidSkillCompatibilityObservation,
            InvalidSkillDependencyGraphInput,
            InvalidSkillDependencyAnalysisProfile,
            InvalidSkillDependencyResolutionRequest,
            InvalidSkillDependencyResolutionPolicy,
            SkillExecutionHandoffError,
        ),
    ):
        return SkillApplicationInvalidInput()
    return SkillApplicationError()
