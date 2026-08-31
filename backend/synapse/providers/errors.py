from __future__ import annotations


class ProviderCatalogError(Exception):
    """Base error carrying a stable machine-readable taxonomy code."""

    code = "provider_catalog_error"

    def __init__(self, message: str, *, provider_id: str | None = None) -> None:
        super().__init__(message)
        self.provider_id = provider_id


class CanonicalProviderNotFound(ProviderCatalogError):
    code = "provider_not_found"


class ProviderIdentityConflict(ProviderCatalogError):
    code = "provider_id_conflict"


class InvalidProviderManifest(ProviderCatalogError):
    code = "invalid_provider_manifest"


class ProviderNotConfigured(ProviderCatalogError):
    code = "provider_not_configured"


class ProviderUnavailable(ProviderCatalogError):
    code = "provider_unavailable"


class ProviderMisconfigured(ProviderCatalogError):
    code = "provider_misconfigured"


class CapabilityNotSupported(ProviderCatalogError):
    code = "capability_not_supported"


class ProviderConfigurationInvalid(ProviderCatalogError):
    code = "configuration_invalid"


class ProviderLoadFailed(ProviderCatalogError):
    code = "provider_load_failed"


class ProviderCloseFailed(ProviderCatalogError):
    code = "provider_close_failed"
