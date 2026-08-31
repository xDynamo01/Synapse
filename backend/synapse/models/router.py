from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from synapse.agents.models import AgentConfig
from synapse.core.events import EventBus
from synapse.intelligence_boundary.models import (
    DataClassification,
    EgressRequest,
    InformationAsset,
    InformationOwnership,
    ProcessingBoundary,
    ProcessingPurpose,
    TrainingUsePolicy,
)
from synapse.models.adapters import (
    BaseModelAdapter,
    MockModelAdapter,
    OllamaModelAdapter,
    OpenAICompatibleAdapter,
)
from synapse.models.errors import ModelError
from synapse.models.types import ModelRequest, ModelResponse, ModelSelection

if TYPE_CHECKING:
    from synapse.intelligence_boundary.contracts import IntelligenceEgressPort


@dataclass(frozen=True)
class ModelRoute:
    provider: str
    model: str | None
    base_url: str | None


class ModelRouter:
    def __init__(
        self,
        system_config: dict[str, Any],
        adapters: dict[str, BaseModelAdapter] | None = None,
        events: EventBus | None = None,
    ):
        self.system_config = system_config
        self.events = events
        self.model_capabilities: Any | None = None
        self.egress_gate: IntelligenceEgressPort | None = None
        self.adapters = adapters or {
            "mock": MockModelAdapter(),
            "ollama": OllamaModelAdapter(),
            "openai_compatible": OpenAICompatibleAdapter(),
        }

    def default_route(self) -> ModelRoute:
        models = self.system_config.get("models", {})
        default_provider = models.get("default_provider", "ollama")
        provider_config = models.get("providers", {}).get(default_provider, {})
        return ModelRoute(
            provider=default_provider,
            model=provider_config.get("model"),
            base_url=provider_config.get("base_url"),
        )

    def route_for_agent(self, agent: AgentConfig) -> ModelRoute:
        if agent.preferred_model:
            provider, model = self._parse_preferred_model(agent.preferred_model)
            provider_config = (
                self.system_config.get("models", {}).get("providers", {}).get(provider, {})
            )
            return ModelRoute(
                provider=provider,
                model=model or provider_config.get("model"),
                base_url=provider_config.get("base_url"),
            )
        return self.default_route()

    def generate(
        self,
        agent: AgentConfig,
        user_message: str,
        context: dict[str, Any],
        tools: list[dict[str, Any]],
        provider_override: str | None = None,
        model_override: str | None = None,
    ) -> ModelResponse:
        selection = self.resolve_selection(
            agent,
            provider_override=provider_override,
            model_override=model_override,
        )
        provider_config = (
            self.system_config.get("models", {}).get("providers", {}).get(selection.provider_id, {})
        )
        route = ModelRoute(
            provider=selection.provider_id,
            model=selection.model_id,
            base_url=provider_config.get("base_url") or provider_config.get("endpoint"),
        )

        return self.generate_request(
            ModelRequest(
                agent_id=agent.id,
                provider=route.provider,
                model=route.model,
                base_url=route.base_url,
                user_message=user_message,
                context=context,
                tools=tools,
                timeout_seconds=float(provider_config.get("timeout_seconds", 60)),
                api_key=provider_config.get("api_key"),
                headers=dict(provider_config.get("headers", {})),
                metadata={"selection": selection.__dict__},
            )
        )

    def generate_request(self, request_payload: ModelRequest) -> ModelResponse:
        adapter = self.adapters.get(request_payload.provider)
        if not adapter:
            raise ModelError(
                "provider_not_found",
                f"No model adapter registered for provider: {request_payload.provider}",
                status_code=404,
            )
        manifest_id = None
        asset_id = None
        if self.egress_gate is not None:
            request_payload, asset_id, manifest_id = self._authorize_request(request_payload)
        if self.events:
            self.events.emit(
                "generation_started",
                request_payload.agent_id,
                {"provider_id": request_payload.provider, "model_id": request_payload.model},
            )
        try:
            result = adapter.generate(request_payload)
        except Exception as exc:
            if self.events:
                self.events.emit(
                    "generation_failed",
                    request_payload.agent_id,
                    {
                        "provider_id": request_payload.provider,
                        "model_id": request_payload.model,
                        "error_type": type(exc).__name__,
                    },
                )
            raise
        if self.events:
            self.events.emit(
                "generation_completed",
                request_payload.agent_id,
                {
                    "provider_id": result.provider,
                    "model_id": result.model,
                    "latency_ms": result.latency_ms,
                    "usage": result.usage.__dict__,
                    "finish_reason": result.finish_reason,
                },
            )
        if self.egress_gate is not None and asset_id:
            result_asset = self.egress_gate.register_derived_asset(
                asset_id=f"model-output-{uuid4().hex}",
                input_asset_ids=(asset_id,),
                source_reference=f"model:{request_payload.provider}:{request_payload.model}",
                content_type="text/plain",
                output_checksum=hashlib.sha256(result.content.encode()).hexdigest(),
                purpose=ProcessingPurpose.MODEL_INFERENCE,
                provider_id=request_payload.provider,
                model_id=request_payload.model,
                manifest_id=manifest_id,
            )
            if manifest_id:
                self.egress_gate.complete_egress(
                    manifest_id,
                    result_reference=result_asset.asset_id,
                )
            result = replace(
                result,
                metadata={
                    **result.metadata,
                    "egress_manifest_id": manifest_id,
                    "derived_asset_id": result_asset.asset_id,
                },
            )
        return result

    def _authorize_request(
        self, request_payload: ModelRequest
    ) -> tuple[ModelRequest, str, str | None]:
        assert self.egress_gate is not None
        serialized = json.dumps(
            {
                "user_message": request_payload.user_message,
                "context": request_payload.context,
                "tools": request_payload.tools,
            },
            sort_keys=True,
            default=str,
        )
        payload_checksum = hashlib.sha256(serialized.encode()).hexdigest()
        asset_id = f"model-input-{payload_checksum[:24]}"
        try:
            self.egress_gate.get_asset(asset_id)
        except Exception:
            self.egress_gate.register_asset(
                InformationAsset(
                    asset_id=asset_id,
                    owner=InformationOwnership.USER,
                    project_id=request_payload.metadata.get("project_id"),
                    source_domain="models",
                    source_reference=f"model-request:{request_payload.agent_id}",
                    content_type="application/vnd.synapse.model-request",
                    classification=DataClassification(
                        request_payload.metadata.get("classification", "internal")
                    ),
                    categories=tuple(
                        request_payload.metadata.get("categories", ("tool.input",))
                    ),
                    training_use_policy=TrainingUsePolicy(
                        request_payload.metadata.get("training_use_policy", "prohibited")
                    ),
                    external_processing_policy=str(
                        request_payload.metadata.get(
                            "external_processing_policy", "policy-controlled"
                        )
                    ),
                    metadata={
                        "estimated_tokens": max(1, len(serialized) // 4),
                        "relevant": True,
                    },
                )
            )
        boundary_value = self.egress_gate.provider_boundary(request_payload.provider)
        boundary = ProcessingBoundary(
            boundary_value or ProcessingBoundary.EXTERNAL_PROVIDER.value
        )
        authorization = self.egress_gate.authorize_egress(
            EgressRequest(
                asset_ids=(asset_id,),
                requester=request_payload.agent_id,
                destination=request_payload.base_url or request_payload.provider,
                boundary=boundary,
                provider_id=request_payload.provider,
                purpose=ProcessingPurpose.MODEL_INFERENCE,
                project_id=request_payload.metadata.get("project_id"),
                rfc_id=request_payload.metadata.get("rfc_id"),
                rfc_revision=request_payload.metadata.get("rfc_revision"),
                mission_id=request_payload.metadata.get("mission_id"),
                payload_checksum=payload_checksum,
                estimated_size=len(serialized.encode()),
                estimated_tokens=max(1, len(serialized) // 4),
                correlation_id=request_payload.correlation_id or "",
                actor_type=str(request_payload.metadata.get("actor_type", "agent")),
                approval_reference=request_payload.metadata.get("egress_approval_id"),
                constraints=tuple(request_payload.metadata.get("egress_constraints", ())),
            )
        )
        return (
            replace(
                request_payload,
                metadata={
                    **request_payload.metadata,
                    "egress_decision_id": authorization.decision.decision_id,
                    "egress_manifest_id": (
                        authorization.manifest.manifest_id if authorization.manifest else None
                    ),
                },
            ),
            asset_id,
            authorization.manifest.manifest_id if authorization.manifest else None,
        )

    def resolve_selection(
        self,
        agent: AgentConfig,
        *,
        provider_override: str | None = None,
        model_override: str | None = None,
        conversation_provider: str | None = None,
        conversation_model: str | None = None,
    ) -> ModelSelection:
        route = self.route_for_agent(agent)
        source = "agent" if agent.preferred_model else "global_default"
        override = provider_override is not None or model_override is not None
        if conversation_provider or conversation_model:
            route = ModelRoute(
                conversation_provider or route.provider,
                conversation_model or route.model,
                route.base_url,
            )
            source = "conversation"
        if override:
            route = ModelRoute(
                provider_override or route.provider,
                model_override or route.model,
                route.base_url,
            )
            source = "turn_override"
        if not route.provider:
            raise ModelError(
                "provider_unavailable", "No model provider is configured", status_code=503
            )
        if not route.model:
            raise ModelError("model_not_found", "No model is configured", status_code=404)
        model_id = route.model
        provider_config = (
            self.system_config.get("models", {}).get("providers", {}).get(route.provider, {})
        )
        if provider_config.get("enabled") is False:
            raise ModelError("provider_disabled", f"Provider is disabled: {route.provider}")
        resource_recommendation = None
        if self.model_capabilities is not None and not override and source == "global_default":
            resource_recommendation = self.model_capabilities.recommend_route(
                "chat",
                route.provider,
                model_id,
            )
            if (
                resource_recommendation.model_id
                and resource_recommendation.provider_id in self.adapters
                and (
                    resource_recommendation.model_id != route.model
                    or resource_recommendation.provider_id != route.provider
                )
            ):
                route = ModelRoute(
                    resource_recommendation.provider_id,
                    resource_recommendation.model_id,
                    self.system_config.get("models", {})
                    .get("providers", {})
                    .get(resource_recommendation.provider_id, {})
                    .get("base_url"),
                )
                source = "resource_recommendation"
        if route.provider not in self.adapters:
            fallback = self.system_config.get("models", {}).get("fallback", {})
            if fallback.get("enabled"):
                fallback_provider = str(fallback.get("provider", "")).strip()
                fallback_model = str(fallback.get("model", "")).strip()
                if fallback_provider in self.adapters and fallback_model:
                    selection = ModelSelection(
                        fallback_provider,
                        fallback_model,
                        "policy_fallback",
                        agent_id=agent.id,
                        reason=f"requested provider unavailable: {route.provider}",
                        fallback_applied=True,
                        warnings=["explicit fallback policy applied"],
                    )
                    if self.events:
                        self.events.emit(
                            "model_fallback_applied",
                            agent.id,
                            {
                                "requested_provider": route.provider,
                                "provider_id": selection.provider_id,
                                "model_id": selection.model_id,
                            },
                        )
                    return selection
            raise ModelError(
                "provider_not_found",
                f"No model adapter registered for provider: {route.provider}",
                status_code=404,
            )
        selection = ModelSelection(
            route.provider,
            route.model or model_id,
            source,
            agent_id=agent.id,
            override=override,
            reason=(
                resource_recommendation.reason
                if source == "resource_recommendation" and resource_recommendation is not None
                else f"selected from {source}"
            ),
        )
        if self.events:
            self.events.emit(
                "model_selected",
                agent.id,
                {
                    "provider_id": selection.provider_id,
                    "model_id": selection.model_id,
                    "source": selection.source,
                    "fallback_applied": selection.fallback_applied,
                },
            )
        return selection

    @staticmethod
    def _parse_preferred_model(preferred_model: str) -> tuple[str, str | None]:
        if "/" not in preferred_model:
            return preferred_model, None
        provider, _, model = preferred_model.partition("/")
        return provider, model or None
