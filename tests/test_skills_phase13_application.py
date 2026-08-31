from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest

import synapse.skills.application as application
from synapse.skills.application import (
    GetPublishedSkillVersionQuery,
    ListPublishedSkillVersionsQuery,
    PublishSkillVersionCommand,
    SkillApplicationCompleteness,
    SkillApplicationMutationOutcome,
    SkillCatalogQueryHandler,
    SkillPublicationCommandHandler,
)
from synapse.skills.phase2_models import PublishedSkillVersionId, SkillId
from synapse.skills.phase3_errors import InvalidSkillStoreRecord
from synapse.skills.phase3_values import SkillStoreQueryLimit
from synapse.skills.phase5_models import PublishVerifiedSkillVersionRequest, SkillPublicationOutcome
from synapse.skills.phase5_publication import SkillPublicationService

COMMAND_NAMES = {
    "ActivateSkillVersionCommand",
    "ApplySkillLifecycleTransitionCommand",
    "BindSkillGovernanceDecisionCommand",
    "BindSkillIntelligenceFactCommand",
    "BindSkillPrivateEvalResultCommand",
    "DeactivateSkillVersionCommand",
    "InstallSkillVersionCommand",
    "PublishSkillVersionCommand",
    "TerminateSkillInstallationCommand",
}
QUERY_NAMES = {
    "AnalyzeSkillDependenciesQuery",
    "AnalyzeSkillDependencyGraphQuery",
    "BuildSkillExecutionHandoffQuery",
    "GetPublishedSkillVersionQuery",
    "GetSkillGovernanceBindingsQuery",
    "GetSkillInstallationProjectionQuery",
    "GetSkillIntelligenceBindingsQuery",
    "GetSkillLifecycleProjectionQuery",
    "GetSkillPrivateEvalBindingsQuery",
    "ListPublishedSkillVersionsQuery",
    "ResolveSkillDependenciesQuery",
}


def _record() -> SimpleNamespace:
    identity = SimpleNamespace(skill_id=cast(SkillId, object()))
    manifest = SimpleNamespace(
        display_name="Application skill",
        summary="Typed application test subject.",
        scopes=(),
    )
    return SimpleNamespace(identity=identity, manifest=manifest)


@pytest.mark.parametrize("name", sorted(COMMAND_NAMES | QUERY_NAMES))
def test_application_requests_are_explicit_frozen_dataclasses(name: str) -> None:
    request_type = getattr(application, name)
    assert is_dataclass(request_type)
    assert request_type.__dataclass_params__.frozen
    assert {field.name for field in fields(request_type)} <= {
        "identity",
        "limit",
        "request",
        "skill_id",
    }


def test_application_public_surface_is_explicit_and_does_not_grow_root_facade() -> None:
    assert COMMAND_NAMES | QUERY_NAMES <= set(application.__all__)
    import synapse.skills as skills

    assert not (COMMAND_NAMES | QUERY_NAMES) & set(skills.__all__)


@pytest.mark.parametrize(
    ("domain_outcome", "expected"),
    [
        (SkillPublicationOutcome.CREATED, SkillApplicationMutationOutcome.CREATED),
        (
            SkillPublicationOutcome.IDEMPOTENT_REPLAY,
            SkillApplicationMutationOutcome.REPLAYED,
        ),
    ],
)
def test_publication_command_delegates_once_and_preserves_replay(
    domain_outcome: SkillPublicationOutcome,
    expected: SkillApplicationMutationOutcome,
) -> None:
    record = _record()
    service = Mock(spec=SkillPublicationService)
    service.publish.return_value = SimpleNamespace(
        record=record, identity=record.identity, outcome=domain_outcome
    )
    request = cast(PublishVerifiedSkillVersionRequest, object())
    command = PublishSkillVersionCommand(request)

    result = SkillPublicationCommandHandler(service).handle(command)

    service.publish.assert_called_once_with(request)
    assert result.identity == record.identity
    assert result.outcome is expected


def test_catalog_queries_delegate_and_expose_bounded_completeness() -> None:
    record = _record()
    service = Mock(spec=SkillPublicationService)
    service.get_exact.return_value = record
    service.list_versions.return_value = (record,)
    handler = SkillCatalogQueryHandler(service)
    limit = SkillStoreQueryLimit(10)

    exact = handler.get(GetPublishedSkillVersionQuery(record.identity))
    listed = handler.list(
        ListPublishedSkillVersionsQuery(record.identity.skill_id, limit)
    )

    service.get_exact.assert_called_once_with(record.identity)
    service.list_versions.assert_called_once_with(record.identity.skill_id, limit)
    assert exact.record.identity == record.identity
    assert listed.versions == (exact,)
    assert listed.completeness is SkillApplicationCompleteness.UNKNOWN


def test_application_results_and_queries_are_immutable() -> None:
    record = _record()
    query = GetPublishedSkillVersionQuery(record.identity)
    with pytest.raises(FrozenInstanceError):
        query.identity = cast(PublishedSkillVersionId, SimpleNamespace())  # type: ignore[misc]


def test_list_query_rejects_untyped_limit_at_value_boundary() -> None:
    with pytest.raises(InvalidSkillStoreRecord):
        SkillStoreQueryLimit(cast(int, True))


def test_query_identity_is_a_stable_domain_identifier() -> None:
    record = _record()
    query = ListPublishedSkillVersionsQuery(
        cast(SkillId, record.identity.skill_id), SkillStoreQueryLimit(1)
    )
    assert query.skill_id == record.identity.skill_id
