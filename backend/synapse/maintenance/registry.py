from __future__ import annotations

from dataclasses import dataclass

from synapse.core.exceptions import NotFound, ValidationError
from synapse.maintenance.contracts import MaintenanceContributor
from synapse.maintenance.models import MaintenanceContributorInfo


@dataclass(frozen=True)
class RegisteredMaintenanceContributor:
    contributor: MaintenanceContributor
    required: bool


class MaintenanceContributorRegistry:
    """Deterministic registry; construction and execution remain external."""

    def __init__(self) -> None:
        self._contributors: dict[str, RegisteredMaintenanceContributor] = {}

    def register(self, contributor: MaintenanceContributor, *, required: bool = True) -> None:
        contributor_id = contributor.contributor_id
        if not contributor_id:
            raise ValidationError("Maintenance contributor ID is required")
        if contributor_id in self._contributors:
            raise ValidationError(f"Maintenance contributor already registered: {contributor_id}")
        if not contributor.capabilities:
            raise ValidationError(
                f"Maintenance contributor must declare capabilities: {contributor_id}"
            )
        self._contributors[contributor_id] = RegisteredMaintenanceContributor(contributor, required)

    def get(self, contributor_id: str) -> RegisteredMaintenanceContributor:
        try:
            return self._contributors[contributor_id]
        except KeyError as exc:
            raise NotFound(f"Maintenance contributor not found: {contributor_id}") from exc

    def list_registered(self) -> tuple[RegisteredMaintenanceContributor, ...]:
        return tuple(self._contributors[key] for key in sorted(self._contributors))

    def list_info(self) -> list[MaintenanceContributorInfo]:
        return [
            MaintenanceContributorInfo(
                contributor_id=item.contributor.contributor_id,
                capabilities=sorted(item.contributor.capabilities),
                categories=sorted(item.contributor.categories),
                required=item.required,
                domain=item.contributor.domain,
            )
            for item in self.list_registered()
        ]

    def has_capability(self, capability: str) -> bool:
        return any(
            capability in item.contributor.capabilities for item in self._contributors.values()
        )

    def has_category(self, category: str) -> bool:
        return any(category in item.contributor.categories for item in self._contributors.values())
