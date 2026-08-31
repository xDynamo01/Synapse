from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from synapse.providers.errors import CanonicalProviderNotFound, ProviderIdentityConflict
from synapse.providers.taxonomy import (
    CanonicalProviderManifest,
    ProviderAvailability,
    ProviderDomain,
)


class ProviderCatalog:
    """Deterministic, read-only discovery index over canonical provider projections."""

    def __init__(self) -> None:
        self._manifests: dict[str, CanonicalProviderManifest] = {}

    def register(self, manifest: CanonicalProviderManifest) -> CanonicalProviderManifest:
        existing = self._manifests.get(manifest.provider_id)
        if existing is not None and existing != manifest:
            raise ProviderIdentityConflict(
                f"Provider id already registered: {manifest.provider_id}",
                provider_id=manifest.provider_id,
            )
        self._manifests[manifest.provider_id] = manifest
        return manifest

    def get(self, provider_id: str) -> CanonicalProviderManifest:
        try:
            return self._manifests[provider_id]
        except KeyError as exc:
            raise CanonicalProviderNotFound(
                f"Provider not found: {provider_id}", provider_id=provider_id
            ) from exc

    def list(
        self,
        *,
        domain: ProviderDomain | None = None,
        capability_id: str | None = None,
        availability: ProviderAvailability | None = None,
    ) -> tuple[CanonicalProviderManifest, ...]:
        manifests: Iterable[CanonicalProviderManifest] = self._manifests.values()
        if domain is not None:
            manifests = (item for item in manifests if item.domain == domain)
        if capability_id is not None:
            manifests = (
                item
                for item in manifests
                if capability_id in {capability.capability_id for capability in item.capabilities}
            )
        if availability is not None:
            manifests = (item for item in manifests if item.availability == availability)
        return tuple(sorted(manifests, key=lambda item: item.provider_id))

    def set_availability(
        self, provider_id: str, availability: ProviderAvailability
    ) -> CanonicalProviderManifest:
        updated = replace(self.get(provider_id), availability=availability)
        self._manifests[provider_id] = updated
        return updated

    def __len__(self) -> int:
        return len(self._manifests)
