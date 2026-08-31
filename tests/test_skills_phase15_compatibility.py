from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from synapse.skills.application.errors import (
    SkillApplicationConflict,
    SkillApplicationDependencyUnavailable,
    SkillApplicationNotFound,
)
from synapse.skills.application.queries import (
    GetPublishedSkillVersionQuery,
    ListPublishedSkillVersionsQuery,
)
from synapse.skills.application.query_handlers import SkillCatalogQueryHandler
from synapse.skills.application.results import (
    PublishedSkillVersionListResult,
    PublishedSkillVersionView,
    SkillApplicationCompleteness,
    SkillLifecycleQueryResult,
)
from synapse.skills.compatibility import (
    LegacyCatalogAdapter,
    LegacyLifecycleAdapter,
    LegacyLookupOutcome,
    LegacySkillLookup,
    SkillLegacyCompatibilityConflict,
    SkillLegacyCompatibilityIncomplete,
    SkillLegacyCompatibilityInvalidMapping,
    SkillLegacyCompatibilityNotFound,
    SkillLegacyCompatibilityUnavailable,
)
from synapse.skills.persistence import (
    SkillPersistenceMigrator,
    SkillSQLiteConfig,
    SkillSQLiteConnectionFactory,
    SQLiteSkillCatalogStore,
)
from synapse.skills.phase2_models import (
    CapabilityRequirement,
    PublishedSkillManifest,
    PublishedSkillVersionId,
    SkillContentFingerprint,
    SkillContentKind,
    SkillContentRef,
    SkillId,
    SkillLogicalPath,
    SkillManifestFormatVersion,
    SkillProvenance,
    SkillPublicationScope,
    SkillRequirementId,
    SkillSemanticReference,
    SkillVersion,
)
from synapse.skills.phase3_records import PublishedSkillVersionRecord
from synapse.skills.phase3_values import SkillStoreRecordId
from synapse.skills.phase5_publication import SkillPublicationService
from synapse.skills.phase6_models import (
    SkillActivationState,
    SkillLifecycleProjection,
    SkillSelectionState,
)

NOW = datetime(2026, 7, 29, tzinfo=UTC)


def publication(
    *,
    version: str = "1.0.0",
    manifest_seed: bytes = b"manifest",
    content_seed: bytes = b"content",
) -> PublishedSkillVersionRecord:
    content = SkillContentRef(
        SkillLogicalPath("SKILL.md"),
        SkillContentFingerprint(hashlib.sha256(content_seed).hexdigest()),
        SkillContentKind.INSTRUCTIONS,
        "text/markdown",
        len(content_seed),
    )
    manifest = PublishedSkillManifest(
        SkillManifestFormatVersion(1),
        SkillId("legacy-skill"),
        SkillVersion.parse(version),
        "Legacy skill",
        "Legacy summary.",
        "Legacy description.",
        SkillProvenance(SkillSemanticReference("publisher:test")),
        (SkillPublicationScope.PROJECT,),
        (content,),
        capabilities=(CapabilityRequirement(SkillRequirementId("text.generate")),),
    )
    identity = PublishedSkillVersionId(
        manifest.skill_id,
        manifest.version,
        manifest.fingerprint(),
        SkillContentFingerprint(hashlib.sha256(manifest_seed + content_seed).hexdigest()),
    )
    return PublishedSkillVersionRecord(
        identity,
        manifest,
        NOW,
        SkillSemanticReference("actor:test"),
        SkillSemanticReference("publication:test"),
    )


class Catalog:
    def __init__(
        self,
        records: tuple[PublishedSkillVersionRecord, ...],
        completeness: SkillApplicationCompleteness = SkillApplicationCompleteness.COMPLETE,
        error: Exception | None = None,
    ) -> None:
        self.records = records
        self.completeness = completeness
        self.error = error
        self.get_calls = 0
        self.list_calls = 0

    def get(self, query: GetPublishedSkillVersionQuery) -> PublishedSkillVersionView:
        self.get_calls += 1
        if self.error is not None:
            raise self.error
        for record in self.records:
            if record.identity == query.identity:
                return PublishedSkillVersionView(record)
        raise SkillApplicationNotFound()

    def list(
        self, _query: ListPublishedSkillVersionsQuery
    ) -> PublishedSkillVersionListResult:
        self.list_calls += 1
        if self.error is not None:
            raise self.error
        return PublishedSkillVersionListResult(
            tuple(PublishedSkillVersionView(item) for item in self.records),
            self.completeness,
        )


def test_exact_lookup_uses_exact_query_and_preserves_full_identity() -> None:
    record = publication(version="1.2.3-beta.1+build.7")
    catalog = Catalog((record,), SkillApplicationCompleteness.UNKNOWN)
    view = LegacyCatalogAdapter(catalog).get_exact(record.identity)
    assert view.identity == record.identity
    assert view.version == "1.2.3-beta.1+build.7"
    assert view.capabilities == ("text.generate",)
    assert catalog.get_calls == 1
    assert catalog.list_calls == 0


def test_exact_not_found_is_proven_and_translated() -> None:
    wanted = publication().identity
    with pytest.raises(SkillLegacyCompatibilityNotFound):
        LegacyCatalogAdapter(Catalog(())).get_exact(wanted)


def test_reduced_lookup_retains_exact_identity_when_enumeration_is_complete() -> None:
    record = publication(version="1.2.3-beta.1+build.7")
    result = LegacyCatalogAdapter(Catalog((record,))).get(
        LegacySkillLookup("legacy-skill", "1.2.3-beta.1+build.7")
    )
    assert result.outcome is LegacyLookupOutcome.FOUND
    assert result.skill is not None
    assert result.skill.identity == record.identity


def test_reduced_lookup_never_selects_distinct_exact_identities() -> None:
    first = publication(manifest_seed=b"one")
    second = publication(manifest_seed=b"two")
    result = LegacyCatalogAdapter(Catalog((first, second))).get(
        LegacySkillLookup("legacy-skill", "1.0.0")
    )
    assert result.outcome is LegacyLookupOutcome.AMBIGUOUS
    assert result.skill is None
    assert result.candidates == (first.identity, second.identity)


@pytest.mark.parametrize(
    ("records", "completeness"),
    [
        ((), SkillApplicationCompleteness.INCOMPLETE),
        ((), SkillApplicationCompleteness.UNKNOWN),
        ((publication(),), SkillApplicationCompleteness.INCOMPLETE),
        ((publication(),), SkillApplicationCompleteness.UNKNOWN),
    ],
)
def test_reduced_lookup_never_claims_result_or_absence_without_completeness(
    records: tuple[PublishedSkillVersionRecord, ...],
    completeness: SkillApplicationCompleteness,
) -> None:
    with pytest.raises(SkillLegacyCompatibilityIncomplete):
        LegacyCatalogAdapter(Catalog(records, completeness)).get(
            LegacySkillLookup("legacy-skill")
        )


def test_empty_complete_lookup_is_proven_not_found() -> None:
    result = LegacyCatalogAdapter(Catalog(())).get(LegacySkillLookup("legacy-skill"))
    assert result.outcome is LegacyLookupOutcome.NOT_FOUND


def test_invalid_reduced_identity_is_a_mapping_error() -> None:
    with pytest.raises(SkillLegacyCompatibilityInvalidMapping):
        LegacyCatalogAdapter(Catalog(())).get(LegacySkillLookup("Legacy Skill"))


def test_complete_list_preserves_all_exact_identities() -> None:
    records = (publication(version="1.0.0"), publication(version="2.0.0"))
    result = LegacyCatalogAdapter(Catalog(records)).list("legacy-skill")
    assert result.complete
    assert tuple(item.identity for item in result.skills) == tuple(
        item.identity for item in records
    )


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (SkillApplicationDependencyUnavailable(), SkillLegacyCompatibilityUnavailable),
        (SkillApplicationConflict(), SkillLegacyCompatibilityConflict),
    ],
)
def test_application_errors_are_safe_and_keep_their_family(
    source: Exception, target: type[Exception]
) -> None:
    with pytest.raises(target) as raised:
        LegacyCatalogAdapter(Catalog((), error=source)).list("legacy-skill")
    message = str(raised.value)
    assert "C:\\" not in message
    assert "SELECT " not in message
    assert "sha256" not in message


class State:
    def __init__(
        self,
        projection: SkillLifecycleProjection,
        completeness: SkillApplicationCompleteness = SkillApplicationCompleteness.COMPLETE,
    ) -> None:
        self.projection = projection
        self.completeness = completeness

    def lifecycle(self, _query) -> SkillLifecycleQueryResult:
        return SkillLifecycleQueryResult(self.projection, self.completeness)


def lifecycle_projection(
    *,
    activation: SkillActivationState = SkillActivationState.INACTIVE,
    selection: SkillSelectionState = SkillSelectionState.REVOKED,
    deprecated: bool = True,
    revoked: bool = True,
) -> SkillLifecycleProjection:
    identity = publication().identity
    return SkillLifecycleProjection(
        identity,
        activation,
        selection,
        deprecated,
        revoked,
        False,
        not revoked,
        not revoked,
        activation is SkillActivationState.ACTIVE,
        False,
        SkillStoreRecordId("installation:test")
        if activation is SkillActivationState.ACTIVE
        else None,
        None,
        None,
        None,
        SkillStoreRecordId("lifecycle:test"),
    )


def test_lifecycle_view_exposes_phase2_vocabulary_without_enabled_or_available() -> None:
    projection = lifecycle_projection()
    view = LegacyLifecycleAdapter(State(projection)).state(projection.identity)
    assert view.activation_state == "inactive"
    assert view.selection_state == "revoked"
    assert not view.active
    assert view.revoked
    assert view.deprecated
    assert not hasattr(view, "enabled")
    assert not hasattr(view, "available")


def test_active_lifecycle_retains_exact_installation_identity() -> None:
    projection = lifecycle_projection(
        activation=SkillActivationState.ACTIVE,
        selection=SkillSelectionState.ELIGIBLE,
        deprecated=False,
        revoked=False,
    )
    view = LegacyLifecycleAdapter(State(projection)).state(projection.identity)
    assert view.active
    assert view.installation_id == "installation:test"


def test_incomplete_lifecycle_fails_closed() -> None:
    projection = lifecycle_projection()
    with pytest.raises(SkillLegacyCompatibilityIncomplete):
        LegacyLifecycleAdapter(
            State(projection, SkillApplicationCompleteness.INCOMPLETE)
        ).state(projection.identity)


def test_no_automatic_phase1_fallback_after_dependency_failure() -> None:
    catalog = Catalog((), error=SkillApplicationDependencyUnavailable())
    with pytest.raises(SkillLegacyCompatibilityUnavailable):
        LegacyCatalogAdapter(catalog).get_exact(publication().identity)
    assert catalog.get_calls == 1
    assert catalog.list_calls == 0


def test_current_slice13_handler_supports_exact_but_reduced_lookup_fails_closed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "skills.sqlite3"
    factory = SkillSQLiteConnectionFactory(SkillSQLiteConfig(path))
    SkillPersistenceMigrator(factory, lambda: NOW).migrate()
    record = publication()
    SQLiteSkillCatalogStore(factory).save_version(record)
    handler = SkillCatalogQueryHandler(
        SkillPublicationService(SQLiteSkillCatalogStore(factory))
    )
    adapter = LegacyCatalogAdapter(handler)

    assert adapter.get_exact(record.identity).identity == record.identity
    with pytest.raises(SkillLegacyCompatibilityIncomplete):
        adapter.get(LegacySkillLookup("legacy-skill", "1.0.0"))
    with pytest.raises(SkillLegacyCompatibilityIncomplete):
        adapter.list("legacy-skill")

    reopened = SkillSQLiteConnectionFactory(SkillSQLiteConfig(path))
    restarted = LegacyCatalogAdapter(
        SkillCatalogQueryHandler(
            SkillPublicationService(SQLiteSkillCatalogStore(reopened))
        )
    )
    assert restarted.get_exact(record.identity).identity == record.identity


def test_public_facade_is_the_closed_read_only_surface() -> None:
    import synapse.skills.compatibility as compatibility

    assert set(compatibility.__all__) == {
        "LegacyCatalogAdapter",
        "LegacyLifecycleAdapter",
        "LegacyLifecycleView",
        "LegacyLookupOutcome",
        "LegacySkillListResult",
        "LegacySkillLookup",
        "LegacySkillLookupResult",
        "LegacySkillView",
        "SkillLegacyCompatibilityConflict",
        "SkillLegacyCompatibilityError",
        "SkillLegacyCompatibilityIncomplete",
        "SkillLegacyCompatibilityInvalidMapping",
        "SkillLegacyCompatibilityNotFound",
        "SkillLegacyCompatibilityUnavailable",
    }
    assert not hasattr(compatibility, "LegacyMutationOutcome")
    assert not hasattr(compatibility, "legacy_publication_decision")
