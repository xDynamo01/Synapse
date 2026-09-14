from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from synapse.api.common import api_error, context_from, runtime_from
from synapse.core.exceptions import NotFound
from synapse.models.types import ModelRequest

router = APIRouter()


class LMStudioChatPayload(BaseModel):
    messages: list[dict[str, Any]]
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_seconds: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelHubDefaultsPayload(BaseModel):
    default_chat_model: str | None = None
    default_provider: str | None = None
    preferred_runtime: str | None = None


class ModelHubFolderPayload(BaseModel):
    path: str


class ModelResolvePayload(BaseModel):
    agent_id: str
    provider_override: str | None = None
    model_override: str | None = None
    conversation_provider: str | None = None
    conversation_model: str | None = None


class ProviderSettingPayload(BaseModel):
    enabled: bool | None = None
    endpoint: str | None = None
    default_model: str | None = None
    api_key: str | None = None


@router.get("/speech-adapters")
def list_speech_adapters(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(adapter) for adapter in runtime.speech_adapters.list_adapters()]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/speech-adapters/health")
def speech_adapter_health(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(item) for item in runtime.speech_adapters.list_adapter_health()]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/speech-adapters/resolve/{capability_id}")
def resolve_speech_adapter(capability_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.speech_adapters.resolve_adapter_for_capability(capability_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/speech-adapters/{adapter_id}")
def get_speech_adapter(adapter_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.speech_adapters.get_adapter(adapter_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/providers")
def list_providers(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(provider) for provider in runtime.providers.list_providers()]


@router.get("/providers/health")
def list_provider_health(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(health) for health in runtime.providers.list_provider_health()]


@router.get("/providers/resolve/{capability_id}")
def resolve_provider(capability_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return runtime.providers.explain_provider_resolution(capability_id)
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/providers/{provider_id}")
def get_provider(provider_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.providers.get_provider(provider_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/providers/lmstudio/status")
def lmstudio_status(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return runtime.lmstudio.explain_status()
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/providers/synapse-local/status")
def synapse_local_status(request: Request, model: str | None = None) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        adapter = runtime.models.adapters.get("synapse_local")
        if adapter is None or not hasattr(adapter, "explain_status"):
            raise NotFound("Synapse Local Models runtime is unavailable.")
        return adapter.explain_status(model=model)
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/providers/lmstudio/models")
def lmstudio_models(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(model) for model in runtime.lmstudio.list_models()]
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/providers/lmstudio/chat")
def lmstudio_chat(payload: LMStudioChatPayload, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        config = runtime.lmstudio.load_config()
        user_message = next(
            (
                str(item.get("content", ""))
                for item in reversed(payload.messages)
                if item.get("role") == "user"
            ),
            "",
        )
        return asdict(
            runtime.models.generate_request(
                ModelRequest(
                    agent_id="api-user",
                    provider="lmstudio",
                    model=payload.model or config.default_model,
                    base_url=config.base_url,
                    user_message=user_message,
                    context={"history": payload.messages[:-1]},
                    temperature=payload.temperature,
                    max_tokens=payload.max_tokens,
                    timeout_seconds=float(payload.timeout_seconds or config.timeout_seconds),
                    metadata=payload.metadata,
                )
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/models/catalog")
def model_hub_catalog(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(model) for model in runtime.model_hub.list_catalog()]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/models/available")
def model_hub_available(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(model) for model in runtime.model_hub.live_available_models()]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/models/discovered")
def model_hub_discovered(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(model) for model in runtime.model_hub.live_discovered_models()]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/models/providers")
def model_hub_providers(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(provider) for provider in runtime.model_hub.list_providers()]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/models/default")
def model_hub_defaults(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.model_hub.get_defaults())
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/models/default")
def update_model_hub_defaults(
    payload: ModelHubDefaultsPayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.model_hub.update_defaults(
                default_chat_model=payload.default_chat_model,
                default_provider=payload.default_provider,
                preferred_runtime=payload.preferred_runtime,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/models/folders")
def model_hub_folders(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(folder) for folder in runtime.model_hub.list_folders()]
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/models/folders")
def add_model_hub_folder(
    payload: ModelHubFolderPayload,
    request: Request,
) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.model_hub.add_folder(payload.path))
    except Exception as exc:
        raise api_error(exc) from exc


@router.delete("/models/folders/{folder_id}")
def remove_model_hub_folder(folder_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.model_hub.remove_folder(folder_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/models/refresh")
def refresh_model_hub(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.model_hub.refresh())
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/models/resolve")
def resolve_model(payload: ModelResolvePayload, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(
            runtime.models.resolve_selection(
                runtime.agents.get(payload.agent_id),
                provider_override=payload.provider_override,
                model_override=payload.model_override,
                conversation_provider=payload.conversation_provider,
                conversation_model=payload.conversation_model,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/models/providers/{provider_id}/capabilities")
def model_provider_capabilities(provider_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        adapter = runtime.models.adapters.get(provider_id)
        if not adapter:
            raise NotFound(f"Model provider not found: {provider_id}")
        resolver = getattr(adapter, "capabilities", None)
        capabilities = sorted(resolver()) if callable(resolver) else ["text_generation"]
        return {"provider_id": provider_id, "capabilities": capabilities}
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/models/providers/{provider_id}/models/{model_id}/validate")
def validate_provider_model(provider_id: str, model_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        matches = [
            item
            for item in runtime.model_hub.list_catalog()
            if item.provider == provider_id and item.name == model_id
        ]
        return {
            "provider_id": provider_id,
            "model_id": model_id,
            "valid": bool(matches and matches[0].status == "available"),
            "status": matches[0].status if matches else "not_found",
        }
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/models/providers/{provider_id}/test")
def test_model_hub_provider(provider_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.model_hub.test_provider(provider_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/provider-settings")
def list_provider_settings(request: Request) -> list[dict[str, Any]]:
    return [asdict(item) for item in runtime_from(request).provider_settings.list_settings()]


@router.get("/provider-settings/{provider_id}")
def get_provider_setting(provider_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).provider_settings.get_setting(provider_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.patch("/provider-settings/{provider_id}")
def update_provider_setting(
    provider_id: str,
    payload: ProviderSettingPayload,
    request: Request,
) -> dict[str, Any]:
    try:
        return asdict(
            runtime_from(request).provider_settings.update_setting(
                provider_id,
                enabled=payload.enabled,
                endpoint=payload.endpoint,
                default_model=payload.default_model,
                api_key=payload.api_key,
            )
        )
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/provider-settings/{provider_id}/test")
def test_provider_setting(provider_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).provider_settings.test_connection(provider_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/provider-settings/{provider_id}/clear-key")
def clear_provider_setting_key(provider_id: str, request: Request) -> dict[str, Any]:
    try:
        return asdict(runtime_from(request).provider_settings.clear_key(provider_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/provider-plugins")
def list_provider_plugins(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(plugin) for plugin in runtime.provider_plugins.list_plugins()]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/provider-plugins/health")
def list_provider_plugin_health(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    try:
        return [asdict(item) for item in runtime.provider_plugins.list_plugin_health()]
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/provider-plugins/summary")
def provider_plugin_summary(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.provider_plugins.summarize_plugins())
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/provider-plugins/{plugin_id}")
def get_provider_plugin(plugin_id: str, request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    try:
        return asdict(runtime.provider_plugins.get_plugin(plugin_id))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/provider-plugins/{plugin_id}/enable")
def enable_provider_plugin(
    plugin_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.provider_plugins.enable_plugin(plugin_id, context))
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/provider-plugins/{plugin_id}/disable")
def disable_provider_plugin(
    plugin_id: str,
    request: Request,
    x_actor_id: str | None = Header(default=None),
    x_actor_type: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
) -> dict[str, Any]:
    runtime = runtime_from(request)
    context = context_from(runtime, x_actor_id, x_actor_type, x_device_id)
    try:
        return asdict(runtime.provider_plugins.disable_plugin(plugin_id, context))
    except Exception as exc:
        raise api_error(exc) from exc
