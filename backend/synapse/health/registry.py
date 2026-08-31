from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from synapse.health.contracts import HealthContributor


@dataclass(frozen=True)
class RegisteredHealthContributor:
    contributor_id: str
    contributor: HealthContributor | None
    optional: bool
    metadata: dict[str, object]


class HealthContributorRegistry:
    """Ordered registry with explicit required/optional contributor slots."""

    def __init__(self) -> None:
        self._contributors: dict[str, RegisteredHealthContributor] = {}

    def register(
        self,
        contributor: HealthContributor | None,
        *,
        contributor_id: str | None = None,
        optional: bool = False,
        metadata: dict[str, object] | None = None,
    ) -> None:
        resolved_id = contributor_id or getattr(contributor, "contributor_id", "")
        if not resolved_id:
            raise ValueError("Health contributor ID is required.")
        if resolved_id in self._contributors:
            raise ValueError(f"Duplicate health contributor ID: {resolved_id}")
        if contributor is not None and contributor.contributor_id != resolved_id:
            raise ValueError(
                f"Contributor ID mismatch: {resolved_id} != {contributor.contributor_id}"
            )
        self._contributors[resolved_id] = RegisteredHealthContributor(
            contributor_id=resolved_id,
            contributor=contributor,
            optional=optional,
            metadata=dict(metadata or {}),
        )

    def register_all(self, contributors: Iterable[HealthContributor]) -> None:
        for contributor in contributors:
            self.register(contributor)

    def list_contributors(self) -> tuple[RegisteredHealthContributor, ...]:
        return tuple(self._contributors.values())

    @property
    def contributor_ids(self) -> tuple[str, ...]:
        return tuple(self._contributors)

    def dependency(self, name: str):
        for registration in self._contributors.values():
            contributor = registration.contributor
            if contributor is not None and hasattr(contributor, name):
                return getattr(contributor, name)
        raise AttributeError(name)

    def replace_dependency(self, name: str, value) -> None:
        for registration in self._contributors.values():
            contributor = registration.contributor
            if contributor is not None and hasattr(contributor, name):
                setattr(contributor, name, value)
                return
        raise AttributeError(name)
