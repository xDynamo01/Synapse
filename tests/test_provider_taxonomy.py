from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.core.app import create_runtime
from synapse.core.config import Settings
from synapse.providers.catalog import ProviderCatalog
from synapse.providers.errors import (
    CanonicalProviderNotFound,
    InvalidProviderManifest,
    ProviderIdentityConflict,
)
from synapse.providers.taxonomy import (
    CanonicalProviderManifest,
    ProviderCapability,
    ProviderConfigurationDescriptor,
    ProviderConfigurationField,
)


def manifest(provider_id: str = "alpha") -> CanonicalProviderManifest:
    return CanonicalProviderManifest(
        provider_id=provider_id,
        display_name="Alpha",
        domain="model",
        version="1.0.0",
        capabilities=(ProviderCapability("model.chat"),),
        availability="configured",
    )


def test_catalog_is_deterministic_and_filters_without_executing() -> None:
    catalog = ProviderCatalog()
    catalog.register(manifest("zeta"))
    catalog.register(manifest("alpha"))

    assert [item.provider_id for item in catalog.list()] == ["alpha", "zeta"]
    assert [item.provider_id for item in catalog.list(domain="model")] == ["alpha", "zeta"]
    assert [item.provider_id for item in catalog.list(capability_id="model.chat")] == [
        "alpha",
        "zeta",
    ]


def test_catalog_rejects_identity_conflicts_and_has_structured_not_found() -> None:
    catalog = ProviderCatalog()
    catalog.register(manifest())
    catalog.register(manifest())  # idempotent projection is safe
    with pytest.raises(ProviderIdentityConflict) as conflict:
        catalog.register(
            CanonicalProviderManifest(
                provider_id="alpha",
                display_name="Different",
                domain="vision",
                version="2.0.0",
                capabilities=(ProviderCapability("image.analyze"),),
                availability="available",
            )
        )
    assert conflict.value.code == "provider_id_conflict"
    with pytest.raises(CanonicalProviderNotFound) as missing:
        catalog.get("missing")
    assert missing.value.code == "provider_not_found"


def test_manifest_forbids_secrets_paths_and_sensitive_defaults() -> None:
    with pytest.raises(InvalidProviderManifest):
        CanonicalProviderManifest(
            provider_id="unsafe",
            display_name="Unsafe",
            domain="integration",
            version="1",
            capabilities=(),
            availability="misconfigured",
            metadata={"api_key": "secret"},
        )
    with pytest.raises(InvalidProviderManifest):
        CanonicalProviderManifest(
            provider_id="unsafe",
            display_name="Unsafe",
            domain="integration",
            version="1",
            capabilities=(),
            availability="misconfigured",
            metadata={"root": r"C:\private\provider"},
        )
    with pytest.raises(InvalidProviderManifest):
        ProviderConfigurationDescriptor(
            fields=(ProviderConfigurationField("token", sensitive=True, default="x"),)
        )
    with pytest.raises(InvalidProviderManifest):
        ProviderConfigurationDescriptor(validation_mode="implicit")


def test_bootstrap_catalog_contains_real_providers_but_no_placeholders() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runtime = create_runtime(
            Settings(
                project_root=PROJECT_ROOT,
                data_dir=Path(directory) / "data",
                host="127.0.0.1",
                port=8717,
                default_actor_id="local_owner",
            )
        )
        ids = {item.provider_id for item in runtime.provider_catalog.list()}
        model_ids = {
            item.provider_id for item in runtime.model_hub.discover_provider_manifests()
        }

    assert {"lmstudio_local", "piper", "faster_whisper", "local_image_metadata"} <= ids
    assert {"mss_local", "windows_uia", "windows_input", "windows", "local"} <= ids
    assert not {"mock_stt", "mock_tts", "mock_voice_analysis"} & ids
    assert "not_configured" not in ids
    assert "lmstudio_local" in model_ids


def test_model_aliases_and_optional_availability_are_explicit() -> None:
    with tempfile.TemporaryDirectory() as directory:
        runtime = create_runtime(
            Settings(
                project_root=PROJECT_ROOT,
                data_dir=Path(directory) / "data",
                host="127.0.0.1",
                port=8717,
                default_actor_id="local_owner",
            )
        )
        lmstudio = runtime.provider_catalog.get("lmstudio_local")
        ollama = runtime.provider_catalog.get("ollama_local")
        vision = runtime.provider_catalog.get("local_image_metadata")

    assert lmstudio.aliases == ("lmstudio",)
    assert ollama.aliases == ("ollama",)
    assert lmstudio.availability == "configured"
    assert vision.lifecycle.cancel is False
