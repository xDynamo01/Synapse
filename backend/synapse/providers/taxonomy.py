from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Protocol

from synapse.providers.errors import InvalidProviderManifest

ProviderDomain = Literal[
    "model",
    "speech_to_text",
    "text_to_speech",
    "voice_analysis",
    "vad",
    "vision",
    "capture",
    "desktop_automation",
    "system_insight",
    "notification",
    "integration",
]
ProviderAvailability = Literal[
    "not_configured",
    "configured",
    "available",
    "unavailable",
    "degraded",
    "misconfigured",
]

PROVIDER_DOMAINS = frozenset(
    {
        "model",
        "speech_to_text",
        "text_to_speech",
        "voice_analysis",
        "vad",
        "vision",
        "capture",
        "desktop_automation",
        "system_insight",
        "notification",
        "integration",
    }
)
PROVIDER_AVAILABILITY_STATES = frozenset(
    {"not_configured", "configured", "available", "unavailable", "degraded", "misconfigured"}
)
_SENSITIVE_KEY = re.compile(r"(?:secret|password|token|api[_-]?key|credential)", re.I)
_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|/|\\\\)")


@dataclass(frozen=True)
class ProviderCapability:
    capability_id: str
    version: str = "1"
    supported: bool = True
    mode: str = "native"
    constraints: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.capability_id or not self.mode:
            raise InvalidProviderManifest("Capability id and mode are required")
        _validate_public_metadata(self.constraints, provider_id="capability", path="constraints")
        _validate_public_metadata(self.metadata, provider_id="capability")


@dataclass(frozen=True)
class ProviderConfigurationField:
    name: str
    required: bool = False
    sensitive: bool = False
    restart_required: bool = False
    default: str | bool | int | float | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise InvalidProviderManifest("Configuration field name is required")
        if self.sensitive and self.default not in (None, ""):
            raise InvalidProviderManifest("Sensitive configuration defaults must be empty")


@dataclass(frozen=True)
class ProviderConfigurationDescriptor:
    schema_version: str = "1"
    fields: tuple[ProviderConfigurationField, ...] = ()
    validation_mode: Literal["domain", "factory"] = "domain"

    def __post_init__(self) -> None:
        if not self.schema_version:
            raise InvalidProviderManifest("Configuration schema version is required")
        if self.validation_mode not in {"domain", "factory"}:
            raise InvalidProviderManifest(
                f"Unsupported configuration validation mode: {self.validation_mode}"
            )
        if len({item.name for item in self.fields}) != len(self.fields):
            raise InvalidProviderManifest("Configuration field names must be unique")


@dataclass(frozen=True)
class ProviderLifecycleCapabilities:
    lazy_load: bool = False
    warmup: bool = False
    unload: bool = False
    cancel: bool = False
    streaming: bool = False
    reload: bool = False


@dataclass(frozen=True)
class CanonicalProviderManifest:
    """Neutral discovery contract. It deliberately contains no execution operation."""

    provider_id: str
    display_name: str
    domain: ProviderDomain
    version: str
    capabilities: tuple[ProviderCapability, ...]
    availability: ProviderAvailability
    implementation_id: str | None = None
    health_reference: str | None = None
    local: bool = True
    optional: bool = True
    configuration: ProviderConfigurationDescriptor = field(
        default_factory=ProviderConfigurationDescriptor
    )
    lifecycle: ProviderLifecycleCapabilities = field(default_factory=ProviderLifecycleCapabilities)
    aliases: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provider_id or not self.display_name or not self.version:
            raise InvalidProviderManifest(
                "Provider id, display name, and version are required",
                provider_id=self.provider_id or None,
            )
        if self.domain not in PROVIDER_DOMAINS:
            raise InvalidProviderManifest(
                f"Unsupported provider domain: {self.domain}", provider_id=self.provider_id
            )
        if self.availability not in PROVIDER_AVAILABILITY_STATES:
            raise InvalidProviderManifest(
                f"Unsupported provider availability: {self.availability}",
                provider_id=self.provider_id,
            )
        if len({item.capability_id for item in self.capabilities}) != len(self.capabilities):
            raise InvalidProviderManifest(
                "Provider capabilities must be unique", provider_id=self.provider_id
            )
        _validate_public_metadata(self.metadata, provider_id=self.provider_id)


class ProviderFactory(Protocol):
    """Optional construction boundary; execution remains domain-specific."""

    provider_id: str

    def validate_configuration(self, configuration: Mapping[str, Any]) -> tuple[str, ...]: ...

    def create(self, configuration: Mapping[str, Any]) -> object: ...


def _validate_public_metadata(value: Any, *, provider_id: str, path: str = "metadata") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            if _SENSITIVE_KEY.search(key_text):
                raise InvalidProviderManifest(
                    f"Sensitive metadata key is forbidden: {path}.{key_text}",
                    provider_id=provider_id,
                )
            _validate_public_metadata(nested, provider_id=provider_id, path=f"{path}.{key_text}")
        return
    if isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _validate_public_metadata(nested, provider_id=provider_id, path=f"{path}[{index}]")
        return
    if isinstance(value, str) and _ABSOLUTE_PATH.match(value):
        raise InvalidProviderManifest(
            f"Absolute paths are forbidden in provider metadata: {path}",
            provider_id=provider_id,
        )
