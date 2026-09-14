from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib import request

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound, ValidationError
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.model_hub.models import (
    ModelCatalogEntry,
    ModelFolder,
    ModelHubDefaults,
    ModelHubRefreshResult,
    ModelProviderInfo,
)
from synapse.model_hub.registry import ModelHubRegistry
from synapse.model_providers.lmstudio import LMStudioProviderRuntime
from synapse.models.router import ModelRouter
from synapse.provider_plugins.runtime import ProviderPluginRuntime
from synapse.providers.runtime import ProviderRuntime

PROVIDER_NAMES = {
    "synapse_local": "Synapse Local Models",
    "lmstudio": "LM Studio",
    "ollama": "Ollama",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "gemini": "Gemini",
    "groq": "Groq",
    "openrouter": "OpenRouter",
    "openai_compatible": "OpenAI Compatible",
}
MODEL_EXTENSIONS = {".gguf", ".ggml", ".bin", ".safetensors"}


class ModelHubRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        event_bus: EventBus,
        lmstudio: LMStudioProviderRuntime,
        providers: ProviderRuntime,
        provider_plugins: ProviderPluginRuntime,
        model_router: ModelRouter,
        registry: ModelHubRegistry | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.event_bus = event_bus
        self.lmstudio = lmstudio
        self.providers = providers
        self.provider_plugins = provider_plugins
        self.model_router = model_router
        self.registry = registry or ModelHubRegistry()
        self.provider_settings: Any | None = None
        self.provider_catalog: Any | None = None
        self.root = data_dir.resolve("model_hub")
        self.root.mkdir(parents=True, exist_ok=True)
        self._initialized = False
        self._load_snapshot()

    def list_catalog(self) -> list[ModelCatalogEntry]:
        if not self._initialized:
            self.refresh()
        return self.registry.list_models()

    def live_available_models(self) -> list[ModelCatalogEntry]:
        errors: list[str] = []
        ollama_models, ollama_error = self._ollama_models()
        if ollama_error:
            errors.append(f"Ollama live probe failed: {ollama_error}")
        models = [
            *ollama_models,
            *self._lmstudio_live_models(errors),
        ]
        return self._deduplicate_models(models)

    def live_discovered_models(self) -> list[ModelCatalogEntry]:
        errors: list[str] = []
        models = [
            *self._synapse_local_models(errors),
            *self._folder_models(errors),
        ]
        return self._deduplicate_models(models)

    def live_providers(self) -> list[ModelProviderInfo]:
        refreshed_at = _now()
        providers: list[ModelProviderInfo] = []
        lmstudio_config = self.lmstudio.load_config()
        lmstudio_models, lmstudio_message = self._lmstudio_live_models_with_status()
        ollama_models, ollama_message = self._ollama_models()
        providers.append(
            ModelProviderInfo(
                provider_id="lmstudio",
                display_name="LM Studio",
                status="available" if lmstudio_models else "unavailable",
                endpoint=lmstudio_config.base_url,
                active=bool(lmstudio_models),
                default_model=None,
                model_count=len(lmstudio_models),
                last_refreshed_at=refreshed_at,
                metadata={"message": lmstudio_message} if lmstudio_message else {},
            )
        )
        providers.append(
            ModelProviderInfo(
                provider_id="ollama",
                display_name="Ollama",
                status="available" if ollama_models else "unavailable",
                endpoint="http://127.0.0.1:11434",
                active=bool(ollama_models),
                default_model=None,
                model_count=len(ollama_models),
                last_refreshed_at=refreshed_at,
                metadata={"message": ollama_message} if ollama_message else {},
            )
        )
        return providers

    def list_providers(self) -> list[ModelProviderInfo]:
        if not self._initialized:
            self.refresh()
        return self.registry.list_providers()

    def discover_provider_manifests(self) -> tuple[Any, ...]:
        """Neutral discovery view; model execution remains owned by model registries."""
        if self.provider_catalog is None:
            return ()
        return self.provider_catalog.list(domain="model")

    def get_defaults(self) -> ModelHubDefaults:
        path = self.root / "defaults.yaml"
        raw = load_structured_file(path) if path.exists() else {}
        if not raw:
            route = self.model_router.default_route()
            return ModelHubDefaults(
                default_chat_model=route.model,
                default_provider=route.provider,
                preferred_runtime=route.provider,
            )
        return ModelHubDefaults(
            default_chat_model=raw.get("default_chat_model"),
            default_provider=raw.get("default_provider"),
            preferred_runtime=raw.get("preferred_runtime"),
            updated_at=raw.get("updated_at"),
        )

    def update_defaults(
        self,
        default_chat_model: str | None = None,
        default_provider: str | None = None,
        preferred_runtime: str | None = None,
    ) -> ModelHubDefaults:
        current = self.get_defaults()
        provider = default_provider if default_provider is not None else current.default_provider
        model = default_chat_model if default_chat_model is not None else current.default_chat_model
        runtime = preferred_runtime if preferred_runtime is not None else current.preferred_runtime
        known_providers = {item.provider_id for item in self.list_providers()}
        if provider and provider not in known_providers:
            raise ValidationError(f"Unknown model provider: {provider}")
        defaults = ModelHubDefaults(model, provider, runtime, _now())
        dump_structured_file(self.root / "defaults.yaml", asdict(defaults))
        self._sync_local_chat_contract(defaults)
        self._apply_default_flags(defaults)
        self._persist_snapshot()
        self.event_bus.emit("model_hub.defaults_updated", "model_hub", asdict(defaults))
        return defaults

    def list_folders(self) -> list[ModelFolder]:
        raw = load_structured_file(self.root / "folders.yaml")
        folders = raw.get("folders", [])
        return [ModelFolder(**item) for item in folders if isinstance(item, dict)]

    def add_folder(self, path: str) -> ModelFolder:
        folder_path = Path(path).expanduser().resolve()
        if not folder_path.exists() or not folder_path.is_dir():
            raise ValidationError(
                f"Model folder does not exist or is not a directory: {folder_path}"
            )
        folder_id = hashlib.sha256(str(folder_path).lower().encode("utf-8")).hexdigest()[:16]
        folders = self.list_folders()
        existing = next((item for item in folders if item.folder_id == folder_id), None)
        if existing:
            return existing
        folder = ModelFolder(folder_id=folder_id, path=str(folder_path), added_at=_now())
        self._write_folders([*folders, folder])
        self.event_bus.emit("model_hub.folder_added", "model_hub", asdict(folder))
        return folder

    def remove_folder(self, folder_id: str) -> ModelFolder:
        folders = self.list_folders()
        removed = next((item for item in folders if item.folder_id == folder_id), None)
        if not removed:
            raise NotFound(f"Model folder not found: {folder_id}")
        self._write_folders([item for item in folders if item.folder_id != folder_id])
        self.event_bus.emit("model_hub.folder_removed", "model_hub", asdict(removed))
        return removed

    def refresh(self) -> ModelHubRefreshResult:
        refreshed_at = _now()
        errors: list[str] = []
        providers, provider_models = self._collect_providers(refreshed_at, errors)
        models = [
            *provider_models,
            *self._configured_models(),
            *self._synapse_local_models(errors),
            *self._folder_models(errors),
        ]
        models = self._deduplicate_models(models)
        defaults = self.get_defaults()
        models = [
            replace(
                model,
                is_default=(
                    model.name == defaults.default_chat_model
                    and model.provider == defaults.default_provider
                ),
            )
            for model in models
        ]
        model_counts: dict[str, int] = {}
        for model in models:
            model_counts[model.provider] = model_counts.get(model.provider, 0) + 1
        providers = [
            replace(item, model_count=model_counts.get(item.provider_id, 0)) for item in providers
        ]
        self.registry.replace_models(models)
        self.registry.replace_providers(providers)
        self._initialized = True
        self._update_folder_counts(models, refreshed_at)
        self._persist_snapshot()
        result = ModelHubRefreshResult(
            refreshed_at=refreshed_at,
            catalog_size=len(models),
            provider_count=len(providers),
            folder_count=len(self.list_folders()),
            errors=errors,
        )
        self.event_bus.emit("model_hub.refreshed", "model_hub", asdict(result))
        return result

    def test_provider(self, provider_id: str) -> ModelProviderInfo:
        provider = next(
            (item for item in self.list_providers() if item.provider_id == provider_id),
            None,
        )
        if not provider:
            raise NotFound(f"Model provider not found: {provider_id}")
        checked_at = _now()
        if provider_id == "lmstudio":
            health = self.lmstudio.health()
            tested = replace(
                provider,
                status="available" if health.available else "unavailable",
                active=health.available,
                model_count=health.model_count,
                last_refreshed_at=checked_at,
                metadata={**provider.metadata, "message": health.message},
            )
        elif provider_id == "ollama" and provider.endpoint:
            tested = self._test_ollama(provider, checked_at)
        else:
            tested = replace(provider, last_refreshed_at=checked_at)
        current = [item for item in self.list_providers() if item.provider_id != provider_id]
        self.registry.replace_providers([*current, tested])
        self._persist_snapshot()
        self.event_bus.emit("model_hub.provider_tested", "model_hub", asdict(tested))
        return tested

    def summary(self) -> dict[str, Any]:
        return {
            "available": True,
            "catalog_size": len(self.list_catalog()),
            "provider_count": len(self.list_providers()),
            "folder_count": len(self.list_folders()),
            "defaults": asdict(self.get_defaults()),
        }

    def _collect_providers(
        self,
        refreshed_at: str,
        errors: list[str],
    ) -> tuple[list[ModelProviderInfo], list[ModelCatalogEntry]]:
        system_models = self.model_router.system_config.get("models", {})
        configured = system_models.get("providers", {})
        default_provider = system_models.get("default_provider")
        registered = {item.provider_id: item for item in self.providers.list_providers()}
        plugins = self.provider_plugins.list_by_type("model")
        plugin_provider_ids = {provider for plugin in plugins for provider in plugin.providers}
        results: list[ModelProviderInfo] = []
        provider_models: list[ModelCatalogEntry] = []
        for provider_id, display_name in PROVIDER_NAMES.items():
            config_key = "lmstudio" if provider_id == "lmstudio" else provider_id
            config = configured.get(config_key, {}) if isinstance(configured, dict) else {}
            endpoint = config.get("base_url")
            default_model = config.get("model")
            settings_id = {
                "lmstudio": "lmstudio_local",
                "ollama": "ollama_local",
                "gemini": "google_gemini",
            }.get(provider_id, provider_id)
            setting = (
                self.provider_settings.get_setting(settings_id)
                if self.provider_settings is not None
                else None
            )
            if setting is not None:
                endpoint = setting.endpoint or endpoint
                default_model = setting.default_model or default_model
            status = "unconfigured"
            active = False
            model_count = 0
            metadata: dict[str, Any] = {}
            if provider_id == "lmstudio":
                lm_config = self.lmstudio.load_config()
                endpoint = lm_config.base_url
                default_model = lm_config.default_model
                try:
                    health = self.lmstudio.health()
                    status = "available" if health.available else "unavailable"
                    active = health.available
                    metadata["message"] = health.message
                    for model in self.lmstudio.list_models() if health.available else []:
                        provider_models.append(
                            ModelCatalogEntry(
                                id=f"lmstudio:{model.model_id}",
                                name=model.model_id,
                                provider="lmstudio",
                                runtime="lmstudio",
                                origin=endpoint or "LM Studio",
                                type="chat",
                                availability_state="loaded/server-ready",
                                chat_usable=True,
                                status="available",
                                metadata=model.metadata or {},
                            )
                        )
                    model_count = len(
                        [model for model in provider_models if model.provider == "lmstudio"]
                    )
                except Exception as exc:
                    errors.append(f"LM Studio refresh failed: {exc}")
                    status = "unavailable"
            elif provider_id == "ollama":
                endpoint = endpoint or "http://127.0.0.1:11434"
                ollama_models, ollama_error = self._ollama_models()
                provider_models.extend(ollama_models)
                model_count = len(ollama_models)
                active = ollama_error is None
                status = "available" if active else "unavailable"
                if ollama_error:
                    metadata["message"] = ollama_error
            else:
                registered_id = provider_id if provider_id in registered else f"{provider_id}_local"
                is_registered = registered_id in registered or provider_id in plugin_provider_ids
                is_configured = bool(config) or bool(
                    setting and setting.enabled and setting.status in {"configured", "available"}
                )
                active = is_registered and bool(
                    registered.get(registered_id, None) and registered[registered_id].enabled
                )
                status = (
                    "configured"
                    if is_configured
                    else "registered"
                    if is_registered
                    else "unconfigured"
                )
                metadata["registered"] = is_registered
                if setting is not None:
                    active = setting.enabled
                    status = setting.status
                    metadata["configured_from_provider_settings"] = True
            results.append(
                ModelProviderInfo(
                    provider_id=provider_id,
                    display_name=display_name,
                    status=status,
                    endpoint=endpoint,
                    active=active,
                    default_model=default_model
                    if provider_id != default_provider
                    else default_model,
                    model_count=model_count,
                    last_refreshed_at=refreshed_at,
                    metadata=metadata,
                )
            )
        synapse_models = self._synapse_local_models(errors)
        if synapse_models:
            provider_models.extend(synapse_models)
            roots = [str(path) for path in self._synapse_runtime_model_roots()]
            synapse_index = next(
                (index for index, item in enumerate(results) if item.provider_id == "synapse_local"),
                None,
            )
            metadata = {
                "model_roots": roots,
                "execution": "installed-files-only",
                "runtime_required": "synapse-managed-llama-server",
            }
            if synapse_index is not None:
                current = results[synapse_index]
                results[synapse_index] = replace(
                    current,
                    status="available",
                    endpoint=current.endpoint or (roots[0] if roots else None),
                    active=True,
                    model_count=len(synapse_models),
                    metadata={**current.metadata, **metadata},
                )
        server_models, server_error = self._lmstudio_server_models()
        provider_models.extend(server_models)
        lmstudio_index = next(
            (index for index, item in enumerate(results) if item.provider_id == "lmstudio"),
            None,
        )
        if lmstudio_index is not None and server_models:
            current = results[lmstudio_index]
            results[lmstudio_index] = replace(
                current,
                status="available",
                active=True,
                model_count=len(
                    [model for model in provider_models if model.provider == "lmstudio"]
                ),
            )
        elif lmstudio_index is not None and server_error:
            current = results[lmstudio_index]
            results[lmstudio_index] = replace(
                current,
                metadata={**current.metadata, "server_message": server_error},
            )
        return results, provider_models

    def _configured_models(self) -> list[ModelCatalogEntry]:
        models: list[ModelCatalogEntry] = []
        configured = self.model_router.system_config.get("models", {}).get("providers", {})
        if not isinstance(configured, dict):
            return models
        for provider_id, config in configured.items():
            if not isinstance(config, dict) or not config.get("model"):
                continue
            model_name = str(config["model"])
            models.append(
                ModelCatalogEntry(
                    id=f"{provider_id}:{model_name}",
                    name=model_name,
                    provider=provider_id,
                    runtime=provider_id,
                    origin="system.yaml",
                    type="chat",
                    availability_state="unavailable",
                    chat_usable=True,
                    status="configured",
                    metadata={"endpoint": config.get("base_url")},
                )
            )
        return models

    def _synapse_local_models(self, errors: list[str]) -> list[ModelCatalogEntry]:
        models: list[ModelCatalogEntry] = []
        for root in self._synapse_runtime_model_roots():
            if not root.is_dir():
                continue
            models.extend(
                self._scan_model_folder(
                    root,
                    provider="synapse_local",
                    origin="Synapse Runtime Models",
                    id_prefix="synapse-local",
                    errors=errors,
                    metadata={
                        "library_path": str(root),
                        "execution": "installed-files-only",
                        "runtime_required": "synapse-managed-llama-server",
                    },
                )
            )
        return models

    def _synapse_runtime_model_roots(self) -> list[Path]:
        roots: list[Path] = []
        configured = os.environ.get("SYNAPSE_MODELS_DIR")
        if configured:
            roots.append(Path(configured).expanduser())
        settings_path = self.data_dir.resolve("config/provider_settings.yaml")
        settings = load_structured_file(settings_path) if settings_path.exists() else {}
        providers = settings.get("providers", {}) if isinstance(settings, dict) else {}
        synapse_local = providers.get("synapse_local") if isinstance(providers, dict) else None
        if isinstance(synapse_local, dict) and synapse_local.get("enabled", False):
            endpoint = str(synapse_local.get("endpoint") or "").strip()
            if endpoint:
                roots.append(Path(endpoint).expanduser())

        unique: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            key = str(root).lower()
            if key not in seen:
                unique.append(root)
                seen.add(key)
        return unique

    def _folder_models(self, errors: list[str]) -> list[ModelCatalogEntry]:
        models: list[ModelCatalogEntry] = []
        for folder in self.list_folders():
            if not folder.enabled:
                continue
            root = Path(folder.path)
            if not root.exists():
                errors.append(f"Model folder is unavailable: {root}")
                continue
            models.extend(
                self._scan_model_folder(
                    root,
                    provider="local_folder",
                    origin="Local Folder",
                    id_prefix=f"folder:{folder.folder_id}",
                    errors=errors,
                    metadata={"folder_id": folder.folder_id},
                )
            )
        return models

    def _lmstudio_library_models(self, errors: list[str]) -> list[ModelCatalogEntry]:
        user_home = Path(os.environ.get("USERPROFILE") or Path.home())
        library = user_home / ".lmstudio" / "models"
        if not library.is_dir():
            return []
        return self._scan_model_folder(
            library,
            provider="lmstudio",
            origin="LM Studio Library",
            id_prefix="lmstudio-library",
            errors=errors,
            metadata={"library_path": str(library)},
        )

    def _scan_model_folder(
        self,
        root: Path,
        *,
        provider: str,
        origin: str,
        id_prefix: str,
        errors: list[str],
        metadata: dict[str, Any],
    ) -> list[ModelCatalogEntry]:
        try:
            paths = [
                path
                for path in root.rglob("*")
                if path.is_file() and path.suffix.lower() in MODEL_EXTENSIONS
            ]
        except OSError as exc:
            errors.append(f"Model folder scan failed for {root}: {exc}")
            return []
        models: list[ModelCatalogEntry] = []
        for path in paths:
            try:
                size = path.stat().st_size
            except OSError as exc:
                errors.append(f"Model file unavailable: {path}: {exc}")
                continue
            model_type = path.suffix.lower().lstrip(".")
            relative = path.relative_to(root)
            models.append(
                ModelCatalogEntry(
                    id=f"{id_prefix}:{relative.as_posix()}",
                    name=path.stem,
                    provider=provider,
                    runtime="llama.cpp" if model_type in {"gguf", "ggml", "bin"} else "local",
                    origin=origin,
                    type=model_type,
                    availability_state="installed"
                    if provider != "lmstudio"
                    else "library-only/not-installed",
                    chat_usable=provider == "synapse_local" and model_type in {"gguf", "ggml", "bin"},
                    quantization=_quantization(path.name),
                    size_bytes=size,
                    estimated_ram_gb=round(size * 1.2 / (1024**3), 2),
                    estimated_vram_gb=round(size / (1024**3), 2),
                    cpu_compatible=model_type in {"gguf", "ggml", "bin"},
                    gpu_compatible=True,
                    status="available",
                    metadata={**metadata, "path": str(path), "extension": path.suffix.lower()},
                )
            )
        return models

    def _ollama_models(self) -> tuple[list[ModelCatalogEntry], str | None]:
        endpoint = "http://127.0.0.1:11434"
        if self.provider_settings is not None:
            try:
                endpoint = self.provider_settings.get_setting("ollama_local").endpoint
            except Exception:
                pass
        payload, error = _get_json(endpoint.rstrip("/") + "/api/tags")
        if error:
            return [], error
        models = payload.get("models", []) if isinstance(payload, dict) else []
        results: list[ModelCatalogEntry] = []
        for item in models if isinstance(models, list) else []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("model") or "").strip()
            if not name:
                continue
            details_value = item.get("details")
            details = details_value if isinstance(details_value, dict) else {}
            results.append(
                ModelCatalogEntry(
                    id=f"ollama:{name}",
                    name=name,
                    provider="ollama",
                    runtime="ollama",
                    origin="Ollama",
                    type="chat",
                    availability_state="loaded/server-ready",
                    chat_usable=True,
                    quantization=details.get("quantization_level"),
                    size_bytes=item.get("size") if isinstance(item.get("size"), int) else None,
                    status="available",
                    metadata={"modified_at": item.get("modified_at"), "details": details},
                )
            )
        return results, None

    def _lmstudio_server_models(self) -> tuple[list[ModelCatalogEntry], str | None]:
        config = self.lmstudio.load_config()
        payload, error = _get_json(config.base_url.rstrip("/") + "/models")
        if error:
            return [], error
        models = payload.get("data", []) if isinstance(payload, dict) else []
        results: list[ModelCatalogEntry] = []
        for item in models if isinstance(models, list) else []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("id") or "").strip()
            if name:
                results.append(
                    ModelCatalogEntry(
                        id=f"lmstudio:{name}",
                        name=name,
                        provider="lmstudio",
                        runtime="lmstudio",
                        origin="LM Studio Server",
                        type="chat",
                        availability_state="loaded/server-ready",
                        chat_usable=True,
                        status="available",
                        metadata={key: value for key, value in item.items() if key != "id"},
                    )
                )
        return results, None

    def _lmstudio_live_models(self, errors: list[str]) -> list[ModelCatalogEntry]:
        models, error = self._lmstudio_live_models_with_status()
        if error:
            errors.append(f"LM Studio live probe failed: {error}")
        return models

    def _lmstudio_live_models_with_status(self) -> tuple[list[ModelCatalogEntry], str | None]:
        config = self.lmstudio.load_config()
        payload, error = _get_json(config.base_url.rstrip("/") + "/models")
        if error:
            return [], error
        models = payload.get("data", []) if isinstance(payload, dict) else []
        results: list[ModelCatalogEntry] = []
        for item in models if isinstance(models, list) else []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("id") or "").strip()
            if name:
                results.append(
                    ModelCatalogEntry(
                        id=f"lmstudio:{name}",
                        name=name,
                        provider="lmstudio",
                        runtime="lmstudio",
                        origin="LM Studio Server",
                        type="chat",
                        availability_state="loaded/server-ready",
                        chat_usable=True,
                        status="available",
                        metadata={key: value for key, value in item.items() if key != "id"},
                    )
                )
        return results, None

    def _test_ollama(self, provider: ModelProviderInfo, checked_at: str) -> ModelProviderInfo:
        try:
            http_request = request.Request(
                cast(str, provider.endpoint).rstrip("/") + "/api/tags",
                headers={"Accept": "application/json"},
                method="GET",
            )
            with request.urlopen(http_request, timeout=3) as response:
                available = 200 <= response.status < 300
        except Exception as exc:
            return replace(
                provider,
                status="unavailable",
                active=False,
                last_refreshed_at=checked_at,
                metadata={**provider.metadata, "message": str(exc)},
            )
        return replace(
            provider,
            status="available" if available else "unavailable",
            active=available,
            last_refreshed_at=checked_at,
        )

    def _deduplicate_models(self, models: list[ModelCatalogEntry]) -> list[ModelCatalogEntry]:
        unique: dict[tuple[str, str], ModelCatalogEntry] = {}
        for model in models:
            unique.setdefault((model.provider, model.name), model)
        return list(unique.values())

    def _apply_default_flags(self, defaults: ModelHubDefaults) -> None:
        self.registry.replace_models(
            [
                replace(
                    item,
                    is_default=(
                        item.name == defaults.default_chat_model
                        and item.provider == defaults.default_provider
                    ),
                )
                for item in self.registry.list_models()
            ]
        )

    def _sync_local_chat_contract(self, defaults: ModelHubDefaults) -> None:
        runtime = (defaults.preferred_runtime or defaults.default_provider or "").strip().lower()
        provider = (defaults.default_provider or "").strip().lower()
        is_lmstudio = runtime in {"lmstudio", "lmstudio_local"} or provider in {
            "lmstudio",
            "lmstudio_local",
        }
        policy_provider = provider or runtime or None
        if policy_provider == "lmstudio":
            policy_provider = "lmstudio_local"

        local_chat_path = self.data_dir.resolve("config/local_chat_policy.yaml")
        local_chat_raw = load_structured_file(local_chat_path) if local_chat_path.exists() else {}
        local_chat_policy = dict(local_chat_raw.get("local_chat", local_chat_raw))
        local_chat_policy.setdefault("require_explicit_provider", True)
        local_chat_policy.setdefault("persist_conversations", True)
        local_chat_policy.setdefault("max_context_messages", 10)
        local_chat_policy.setdefault("include_conversation_summary", True)
        local_chat_policy.setdefault("include_multimodal_context", False)
        local_chat_policy["enabled"] = bool(defaults.default_chat_model and policy_provider)
        local_chat_policy["provider_id"] = policy_provider
        dump_structured_file(local_chat_path, {"local_chat": local_chat_policy})

        self.event_bus.emit(
            "model_hub.local_chat_policy_synced",
            "model_hub",
            {
                "enabled": local_chat_policy["enabled"],
                "provider_id": local_chat_policy["provider_id"],
                "default_chat_model": defaults.default_chat_model,
                "default_provider": defaults.default_provider,
                "preferred_runtime": defaults.preferred_runtime,
            },
        )

        if self.provider_settings is not None and hasattr(self.provider_settings, "update_setting"):
            try:
                endpoint = self.provider_settings.get_setting("lmstudio_local").endpoint
            except Exception:
                endpoint = "http://127.0.0.1:1234/v1"
            self.provider_settings.update_setting(
                "lmstudio_local",
                enabled=bool(local_chat_policy["enabled"]),
                endpoint=endpoint,
                default_model=defaults.default_chat_model if is_lmstudio else None,
            )
            self.event_bus.emit(
                "model_hub.provider_settings_synced",
                "model_hub",
                {
                    "provider_id": "lmstudio_local",
                    "enabled": bool(local_chat_policy["enabled"]),
                    "default_model": defaults.default_chat_model if is_lmstudio else None,
                    "endpoint": endpoint,
                },
            )

    def _update_folder_counts(self, models: list[ModelCatalogEntry], refreshed_at: str) -> None:
        counts: dict[str, int] = {}
        for model in models:
            folder_id = model.metadata.get("folder_id")
            if folder_id:
                counts[str(folder_id)] = counts.get(str(folder_id), 0) + 1
        self._write_folders(
            [
                replace(
                    folder,
                    last_refreshed_at=refreshed_at,
                    model_count=counts.get(folder.folder_id, 0),
                )
                for folder in self.list_folders()
            ]
        )

    def _write_folders(self, folders: list[ModelFolder]) -> None:
        dump_structured_file(
            self.root / "folders.yaml",
            {"folders": [asdict(item) for item in folders]},
        )

    def _persist_snapshot(self) -> None:
        dump_structured_file(
            self.root / "catalog.yaml",
            {
                "models": [asdict(item) for item in self.registry.list_models()],
                "providers": [asdict(item) for item in self.registry.list_providers()],
                "updated_at": _now(),
            },
        )

    def _load_snapshot(self) -> None:
        raw = load_structured_file(self.root / "catalog.yaml")
        try:
            self.registry.replace_models(
                [ModelCatalogEntry(**item) for item in raw.get("models", [])]
            )
            self.registry.replace_providers(
                [ModelProviderInfo(**item) for item in raw.get("providers", [])]
            )
            self._initialized = bool(raw)
        except (TypeError, ValueError):
            self.registry.replace_models([])
            self.registry.replace_providers([])
            self._initialized = False


def _quantization(filename: str) -> str | None:
    match = re.search(r"(?:^|[-_.])(Q\d(?:_[A-Z0-9]+)*)", filename.upper())
    return match.group(1) if match else None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _get_json(url: str, timeout: float = 1.0) -> tuple[Any, str | None]:
    try:
        http_request = request.Request(url, headers={"Accept": "application/json"}, method="GET")
        with request.urlopen(http_request, timeout=timeout) as response:
            if not 200 <= response.status < 300:
                return {}, f"{url} returned HTTP {response.status}"
            return json.loads(response.read().decode("utf-8")), None
    except Exception as exc:
        return {}, str(exc)
