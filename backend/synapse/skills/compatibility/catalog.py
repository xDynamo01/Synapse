from __future__ import annotations

from typing import Protocol

from synapse.skills.application.errors import (
    SkillApplicationConflict,
    SkillApplicationDependencyUnavailable,
    SkillApplicationError,
    SkillApplicationIncomplete,
    SkillApplicationInvalidInput,
    SkillApplicationNotFound,
)
from synapse.skills.application.queries import (
    GetPublishedSkillVersionQuery,
    ListPublishedSkillVersionsQuery,
)
from synapse.skills.application.results import (
    PublishedSkillVersionListResult,
    PublishedSkillVersionView,
    SkillApplicationCompleteness,
)
from synapse.skills.phase2_errors import SkillPhase2DomainError
from synapse.skills.phase2_models import PublishedSkillVersionId, SkillId, SkillVersion
from synapse.skills.phase3_values import SkillStoreQueryLimit

from .errors import (
    SkillLegacyCompatibilityConflict,
    SkillLegacyCompatibilityIncomplete,
    SkillLegacyCompatibilityInvalidMapping,
    SkillLegacyCompatibilityNotFound,
    SkillLegacyCompatibilityUnavailable,
)
from .models import (
    LegacyLookupOutcome,
    LegacySkillListResult,
    LegacySkillLookup,
    LegacySkillLookupResult,
    LegacySkillView,
)


class _CatalogQueries(Protocol):
    def get(self, query: GetPublishedSkillVersionQuery) -> PublishedSkillVersionView: ...

    def list(
        self, query: ListPublishedSkillVersionsQuery
    ) -> PublishedSkillVersionListResult: ...


class LegacyCatalogAdapter:
    """Read-only Phase 1-shaped catalog access retaining exact Phase 2 identity."""

    def __init__(self, queries: _CatalogQueries) -> None:
        self._queries = queries

    def get_exact(self, identity: PublishedSkillVersionId) -> LegacySkillView:
        """Operational exact lookup; the exact key itself proves uniqueness."""
        try:
            return _view(self._queries.get(GetPublishedSkillVersionQuery(identity)))
        except SkillApplicationError as exc:
            raise _translate(exc) from exc

    def get(self, request: LegacySkillLookup) -> LegacySkillLookupResult:
        """Reduced legacy lookup; requires a complete enumeration."""
        result = self._list(request.skill_id)
        if result.completeness is not SkillApplicationCompleteness.COMPLETE:
            raise SkillLegacyCompatibilityIncomplete()
        version = self._version(request.version)
        candidates = tuple(
            item
            for item in result.versions
            if version is None or item.record.identity.version == version
        )
        if not candidates:
            return LegacySkillLookupResult(LegacyLookupOutcome.NOT_FOUND, None)
        if len(candidates) > 1:
            identities = tuple(item.record.identity for item in candidates)
            return LegacySkillLookupResult(
                LegacyLookupOutcome.AMBIGUOUS,
                None,
                identities,
            )
        return LegacySkillLookupResult(
            LegacyLookupOutcome.FOUND,
            _view(candidates[0]),
        )

    def list(self, skill_id: str) -> LegacySkillListResult:
        result = self._list(skill_id)
        if result.completeness is not SkillApplicationCompleteness.COMPLETE:
            raise SkillLegacyCompatibilityIncomplete()
        return LegacySkillListResult(tuple(_view(item) for item in result.versions), True)

    def _list(self, skill_id: str) -> PublishedSkillVersionListResult:
        try:
            parsed = SkillId.parse(skill_id)
            return self._queries.list(
                ListPublishedSkillVersionsQuery(parsed, SkillStoreQueryLimit(200))
            )
        except (TypeError, ValueError, SkillPhase2DomainError) as exc:
            raise SkillLegacyCompatibilityInvalidMapping() from exc
        except SkillApplicationError as exc:
            raise _translate(exc) from exc

    @staticmethod
    def _version(value: str | None) -> SkillVersion | None:
        if value is None:
            return None
        try:
            return SkillVersion.parse(value)
        except (TypeError, ValueError, SkillPhase2DomainError) as exc:
            raise SkillLegacyCompatibilityInvalidMapping() from exc


def _view(value: PublishedSkillVersionView) -> LegacySkillView:
    record = value.record
    manifest = record.manifest
    return LegacySkillView(
        identity=record.identity,
        skill_id=str(record.identity.skill_id),
        version=str(record.identity.version),
        name=manifest.display_name,
        summary=manifest.summary,
        description=manifest.description,
        status="registered",
        capabilities=tuple(str(item.capability_id) for item in manifest.capabilities),
    )


def _translate(error: SkillApplicationError) -> Exception:
    if isinstance(error, SkillApplicationNotFound):
        return SkillLegacyCompatibilityNotFound()
    if isinstance(error, SkillApplicationDependencyUnavailable):
        return SkillLegacyCompatibilityUnavailable()
    if isinstance(error, SkillApplicationIncomplete):
        return SkillLegacyCompatibilityIncomplete()
    if isinstance(error, SkillApplicationConflict):
        return SkillLegacyCompatibilityConflict()
    if isinstance(error, SkillApplicationInvalidInput):
        return SkillLegacyCompatibilityInvalidMapping()
    return SkillLegacyCompatibilityUnavailable()
