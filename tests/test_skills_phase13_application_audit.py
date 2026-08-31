from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest

from synapse.skills.application import (
    ActivateSkillVersionCommand,
    AnalyzeSkillDependenciesQuery,
    AnalyzeSkillDependencyGraphQuery,
    ApplySkillLifecycleTransitionCommand,
    BindSkillGovernanceDecisionCommand,
    BindSkillIntelligenceFactCommand,
    BindSkillPrivateEvalResultCommand,
    BuildSkillExecutionHandoffQuery,
    DeactivateSkillVersionCommand,
    GetSkillGovernanceBindingsQuery,
    GetSkillInstallationProjectionQuery,
    GetSkillIntelligenceBindingsQuery,
    GetSkillLifecycleProjectionQuery,
    GetSkillPrivateEvalBindingsQuery,
    InstallSkillVersionCommand,
    ResolveSkillDependenciesQuery,
    SkillApplicationCompleteness,
    SkillApplicationConflict,
    SkillApplicationDependencyUnavailable,
    SkillApplicationIncomplete,
    SkillApplicationInvalidInput,
    SkillApplicationMutationOutcome,
    SkillApplicationNotFound,
    SkillBindingQueryHandler,
    SkillDependencyQueryHandler,
    SkillExecutionHandoffQueryHandler,
    SkillExternalBindingCommandHandler,
    SkillInstallationCommandHandler,
    SkillLifecycleCommandHandler,
    SkillStateQueryHandler,
    TerminateSkillInstallationCommand,
)
from synapse.skills.application.command_handlers import _translate
from synapse.skills.phase2_models import PublishedSkillVersionId
from synapse.skills.phase5_errors import (
    PublishedSkillVersionNotFound,
    SkillPublicationCatalogUnavailable,
    SkillPublicationConflict,
    SkillPublicationSnapshotMismatch,
)
from synapse.skills.phase6_errors import (
    CorruptedSkillLifecycleHistory,
    IncompleteSkillLifecycleHistory,
    InvalidSkillActivationParent,
    InvalidSkillLifecycleTransition,
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
    CorruptedSkillInstallationHistory,
    SkillInstallationVersionNotPublished,
)
from synapse.skills.phase7_installation import (
    SkillActivationService,
    SkillInstallationService,
    SkillInstallationTerminationService,
)
from synapse.skills.phase7_models import SkillInstallationOutcome
from synapse.skills.phase8_analysis import SkillDependencyAnalysisService
from synapse.skills.phase8_errors import (
    InconsistentSkillDependencyCatalog,
    InvalidSkillDependencyDeclaration,
    SkillDependencyCatalogUnavailable,
    SkillDependencySubjectNotPublished,
)
from synapse.skills.phase8_graph import SkillDependencyGraphAnalysisService
from synapse.skills.phase9_errors import (
    InconsistentSkillDependencyAnalysis,
    InvalidSkillDependencyResolutionRequest,
)
from synapse.skills.phase9_resolution import SkillDependencyResolutionService
from synapse.skills.phase10_errors import (
    SkillExternalBindingCorrespondenceMismatch,
    SkillExternalBindingDivergentDuplicate,
    SkillExternalBindingSubjectNotPublished,
)
from synapse.skills.phase10_governance import SkillGovernanceBindingService
from synapse.skills.phase10_intelligence import SkillIntelligenceBindingService
from synapse.skills.phase10_models import SkillExternalBindingOutcome
from synapse.skills.phase11_bindings import SkillPrivateEvalBindingService
from synapse.skills.phase11_errors import (
    SkillPrivateEvalBindingDivergentDuplicate,
    SkillPrivateEvalBindingSubjectNotPublished,
)
from synapse.skills.phase11_models import SkillPrivateEvalBindingOutcome
from synapse.skills.phase12_errors import CorruptSkillExecutionInputProjection
from synapse.skills.phase12_handoff import SkillExecutionHandoffService

IDENTITY = cast(PublishedSkillVersionId, object())


@pytest.mark.parametrize(
    ("request_type", "method"),
    [
        (DeactivateSkillVersionRequest, "deactivate"),
        (DeprecateSkillVersionRequest, "deprecate"),
        (ReenableSkillVersionRequest, "reenable"),
        (SupersedeSkillVersionRequest, "supersede"),
        (RollbackSkillVersionRequest, "rollback"),
        (RevokeSkillVersionRequest, "revoke"),
    ],
)
@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (SkillLifecycleOutcome.CREATED, SkillApplicationMutationOutcome.CREATED),
        (
            SkillLifecycleOutcome.IDEMPOTENT_REPLAY,
            SkillApplicationMutationOutcome.REPLAYED,
        ),
    ],
)
def test_every_lifecycle_command_delegates_once_and_preserves_replay(
    request_type: type[object],
    method: str,
    outcome: SkillLifecycleOutcome,
    expected: SkillApplicationMutationOutcome,
) -> None:
    service = Mock(spec=SkillLifecycleService)
    request = object.__new__(request_type)
    getattr(service, method).return_value = SimpleNamespace(
        identity=IDENTITY, outcome=outcome
    )

    result = SkillLifecycleCommandHandler(service).handle(
        ApplySkillLifecycleTransitionCommand(request)  # type: ignore[arg-type]
    )

    getattr(service, method).assert_called_once_with(request)
    assert result.outcome is expected


@pytest.mark.parametrize(
    ("handler_method", "command_type", "service_index", "service_method"),
    [
        ("handle_install", InstallSkillVersionCommand, 0, "install"),
        (
            "handle_termination",
            TerminateSkillInstallationCommand,
            1,
            "terminate",
        ),
        ("handle_activation", ActivateSkillVersionCommand, 2, "activate"),
        ("handle_deactivation", DeactivateSkillVersionCommand, 2, "deactivate"),
    ],
)
@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (SkillInstallationOutcome.CREATED, SkillApplicationMutationOutcome.CREATED),
        (
            SkillInstallationOutcome.IDEMPOTENT_REPLAY,
            SkillApplicationMutationOutcome.REPLAYED,
        ),
    ],
)
def test_every_installation_command_delegates_only_to_its_authority(
    handler_method: str,
    command_type: type[object],
    service_index: int,
    service_method: str,
    outcome: SkillInstallationOutcome,
    expected: SkillApplicationMutationOutcome,
) -> None:
    services = [
        Mock(spec=SkillInstallationService),
        Mock(spec=SkillInstallationTerminationService),
        Mock(spec=SkillActivationService),
    ]
    request = object()
    getattr(services[service_index], service_method).return_value = SimpleNamespace(
        identity=IDENTITY,
        outcome=(
            SkillLifecycleOutcome(outcome.value)
            if service_index == 2
            else outcome
        ),
    )
    handler = SkillInstallationCommandHandler(*services)

    result = getattr(handler, handler_method)(command_type(request))

    getattr(services[service_index], service_method).assert_called_once_with(request)
    assert result.outcome is expected


@pytest.mark.parametrize(
    ("handler_method", "command_type", "service_index", "outcome"),
    [
        (
            "handle_governance",
            BindSkillGovernanceDecisionCommand,
            0,
            SkillExternalBindingOutcome.IDEMPOTENT_REPLAY,
        ),
        (
            "handle_intelligence",
            BindSkillIntelligenceFactCommand,
            1,
            SkillExternalBindingOutcome.CREATED,
        ),
        (
            "handle_private_eval",
            BindSkillPrivateEvalResultCommand,
            2,
            SkillPrivateEvalBindingOutcome.IDEMPOTENT_REPLAY,
        ),
    ],
)
def test_binding_commands_delegate_without_interpreting_external_facts(
    handler_method: str,
    command_type: type[object],
    service_index: int,
    outcome: SkillExternalBindingOutcome | SkillPrivateEvalBindingOutcome,
) -> None:
    services = [
        Mock(spec=SkillGovernanceBindingService),
        Mock(spec=SkillIntelligenceBindingService),
        Mock(spec=SkillPrivateEvalBindingService),
    ]
    request = object()
    services[service_index].bind.return_value = SimpleNamespace(
        identity=IDENTITY, outcome=outcome
    )

    result = getattr(
        SkillExternalBindingCommandHandler(*services), handler_method
    )(command_type(request))

    services[service_index].bind.assert_called_once_with(request)
    assert result.outcome is (
        SkillApplicationMutationOutcome.REPLAYED
        if "replay" in outcome.value
        else SkillApplicationMutationOutcome.CREATED
    )


@pytest.mark.parametrize(
    ("error", "translated"),
    [
        (PublishedSkillVersionNotFound(), SkillApplicationNotFound),
        (SkillInstallationVersionNotPublished(), SkillApplicationNotFound),
        (SkillDependencySubjectNotPublished(), SkillApplicationNotFound),
        (SkillExternalBindingSubjectNotPublished(), SkillApplicationNotFound),
        (SkillPrivateEvalBindingSubjectNotPublished(), SkillApplicationNotFound),
        (SkillPublicationCatalogUnavailable(), SkillApplicationDependencyUnavailable),
        (SkillDependencyCatalogUnavailable(), SkillApplicationDependencyUnavailable),
        (IncompleteSkillLifecycleHistory(), SkillApplicationIncomplete),
        (SkillPublicationConflict(), SkillApplicationConflict),
        (CorruptedSkillLifecycleHistory(), SkillApplicationConflict),
        (CorruptedSkillInstallationHistory(), SkillApplicationConflict),
        (InconsistentSkillDependencyCatalog(), SkillApplicationConflict),
        (InconsistentSkillDependencyAnalysis(), SkillApplicationConflict),
        (SkillExternalBindingDivergentDuplicate(), SkillApplicationConflict),
        (SkillPrivateEvalBindingDivergentDuplicate(), SkillApplicationConflict),
        (SkillPublicationSnapshotMismatch(), SkillApplicationInvalidInput),
        (InvalidSkillLifecycleTransition(), SkillApplicationInvalidInput),
        (InvalidSkillActivationParent(), SkillApplicationInvalidInput),
        (InvalidSkillDependencyDeclaration(), SkillApplicationInvalidInput),
        (InvalidSkillDependencyResolutionRequest(), SkillApplicationInvalidInput),
        (SkillExternalBindingCorrespondenceMismatch(), SkillApplicationInvalidInput),
        (CorruptSkillExecutionInputProjection(), SkillApplicationInvalidInput),
    ],
)
def test_domain_errors_have_safe_stable_application_categories(
    error: Exception, translated: type[Exception]
) -> None:
    result = _translate(error)
    assert isinstance(result, translated)
    assert str(result).startswith("skill application")
    assert str(error) not in str(result)


def test_state_queries_preserve_full_projection_and_completeness() -> None:
    lifecycle = Mock(spec=SkillLifecycleService)
    installation = Mock(spec=SkillInstallationService)
    lifecycle_projection = SimpleNamespace(identity=IDENTITY)
    incomplete_installation = SimpleNamespace(identity=IDENTITY, complete=False)
    lifecycle.projection.return_value = lifecycle_projection
    installation.projection.return_value = incomplete_installation
    handler = SkillStateQueryHandler(lifecycle, installation)

    lifecycle_result = handler.lifecycle(GetSkillLifecycleProjectionQuery(IDENTITY))
    installation_result = handler.installation(
        GetSkillInstallationProjectionQuery(IDENTITY)
    )

    assert lifecycle_result.projection is lifecycle_projection
    assert lifecycle_result.completeness is SkillApplicationCompleteness.COMPLETE
    assert installation_result.projection is incomplete_installation
    assert installation_result.completeness is SkillApplicationCompleteness.INCOMPLETE


@pytest.mark.parametrize(
    ("method", "query_type", "service_index"),
    [
        ("analyze", AnalyzeSkillDependenciesQuery, 0),
        ("graph", AnalyzeSkillDependencyGraphQuery, 1),
        ("resolve", ResolveSkillDependenciesQuery, 2),
    ],
)
def test_dependency_queries_are_read_only_single_service_delegations(
    method: str, query_type: type[object], service_index: int
) -> None:
    services = [
        Mock(spec=SkillDependencyAnalysisService),
        Mock(spec=SkillDependencyGraphAnalysisService),
        Mock(spec=SkillDependencyResolutionService),
    ]
    request = object()
    service_method = "resolve" if method == "resolve" else "analyze"
    sentinel = object()
    getattr(services[service_index], service_method).return_value = sentinel

    result = getattr(SkillDependencyQueryHandler(*services), method)(
        query_type(request)
    )

    getattr(services[service_index], service_method).assert_called_once_with(request)
    assert next(iter(vars(result).values())) is sentinel


@pytest.mark.parametrize(
    ("method", "query_type", "service_index"),
    [
        ("governance", GetSkillGovernanceBindingsQuery, 0),
        ("intelligence", GetSkillIntelligenceBindingsQuery, 1),
        ("private_evals", GetSkillPrivateEvalBindingsQuery, 2),
    ],
)
@pytest.mark.parametrize("complete", [True, False])
def test_binding_queries_preserve_projection_diagnostics_and_completeness(
    method: str, query_type: type[object], service_index: int, complete: bool
) -> None:
    services = [
        Mock(spec=SkillGovernanceBindingService),
        Mock(spec=SkillIntelligenceBindingService),
        Mock(spec=SkillPrivateEvalBindingService),
    ]
    diagnostics = (object(),)
    projection = SimpleNamespace(
        identity=IDENTITY, complete=complete, diagnostics=diagnostics
    )
    services[service_index].projection.return_value = projection

    result = getattr(SkillBindingQueryHandler(*services), method)(
        query_type(IDENTITY)
    )

    services[service_index].projection.assert_called_once_with(IDENTITY)
    assert result.projection is projection
    assert result.projection.diagnostics is diagnostics
    assert result.completeness is (
        SkillApplicationCompleteness.COMPLETE
        if complete
        else SkillApplicationCompleteness.INCOMPLETE
    )


def test_handoff_query_preserves_domain_diagnostics_without_execution() -> None:
    service = Mock(spec=SkillExecutionHandoffService)
    request = object()
    result_with_diagnostics = SimpleNamespace(draft=object(), readiness=object())
    service.build.return_value = result_with_diagnostics

    result = SkillExecutionHandoffQueryHandler(service).build(
        BuildSkillExecutionHandoffQuery(request)
    )

    service.build.assert_called_once_with(request)
    assert result.result is result_with_diagnostics
