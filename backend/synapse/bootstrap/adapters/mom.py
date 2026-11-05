from __future__ import annotations

from collections.abc import Mapping

from synapse.agents.admin import AgentAdminRuntime
from synapse.chat.routing import ChatModelSelection
from synapse.context.loader import ContextLoader
from synapse.core.data_dir import DataDir
from synapse.core.exceptions import ValidationError
from synapse.core.permissions import PermissionContext
from synapse.memory.store import MemoryStore
from synapse.models.router import ModelRouter
from synapse.models.types import ModelRequest
from synapse.mom.contracts import Configuration, Output, Route
from synapse.mom.runtime import MoMRuntime
from synapse.primary_agent.runtime import PrimaryAgentRuntime
from synapse.storage.collection import FileCollection
from synapse.storage.errors import StorageRecordNotFound


def validate_configuration(payload: Mapping[str, object]) -> None:
    Configuration.model_validate(payload)


class PrimaryBinding:
    def __init__(self, primary: PrimaryAgentRuntime, admin: AgentAdminRuntime):
        self.primary = primary
        self.admin = admin

    def current_agent(self, workspace_id: str) -> str:
        profile = self.primary.get_primary(workspace_id)
        if profile.status != "active":
            raise ValidationError("Primary Agent must be active to use MoM.")
        self.admin.assert_agent_runnable(profile.agent_id)
        return profile.agent_id


class PrimaryChatRouting:
    def __init__(self, mom: MoMRuntime):
        self.mom = mom

    def select(self, context: PermissionContext, agent_id: str | None,
               message: str, workspace_id: str,
               recent_intent: str | None = None) -> ChatModelSelection | None:
        selected = self.mom.select_for_chat(context, agent_id, message, workspace_id, recent_intent)
        if selected is None:
            return None
        primary_id, route, revision = selected
        return ChatModelSelection(primary_id, route.provider, route.model, route.operation.value, revision)


class MoMConfigurations:
    def __init__(self, data_dir: DataDir):
        self.collection = FileCollection(
            collection_id="primary_mom", root=data_dir.resolve("mom/configurations"),
            current_schema_version=1, recovery_policy="fail_closed",
            validator=validate_configuration,
        )

    def read(self, workspace_id: str) -> Configuration | None:
        try:
            record = self.collection.get(workspace_id)
        except StorageRecordNotFound:
            return None
        configuration = Configuration.model_validate(record.payload)
        if configuration.workspace_id != workspace_id:
            raise ValidationError("MoM configuration workspace mismatch.")
        return configuration

    def write(self, configuration: Configuration, expected_revision: int) -> None:
        self.collection.put(
            configuration.workspace_id, configuration.model_dump(mode="json"),
            expected_revision=expected_revision if expected_revision else None,
            create_only=expected_revision == 0,
        )


class PrimaryInference:
    def __init__(self, models: ModelRouter, loader: ContextLoader, memory: MemoryStore):
        self.models = models
        self.loader = loader
        self.memory = memory

    def validate_route(self, route: Route) -> None:
        if route.provider == "lmstudio_local":
            raise ValidationError("Use the canonical lmstudio provider for MoM routes.")
        if route.provider not in self.models.adapters:
            raise ValidationError("MoM provider is not registered.")
        provider = self.models.system_config.get("models", {}).get("providers", {}).get(route.provider, {})
        if provider.get("enabled") is False:
            raise ValidationError("MoM provider is disabled.")

    def generate(self, context: PermissionContext, primary_agent_id: str,
                 route: Route, message: str, operation_id: str, *, max_tokens: int = 1024) -> Output:
        self.validate_route(route)
        loaded = self.loader.load(context, primary_agent_id).to_dict()
        style = self.memory.response_style(context, "")
        if style:
            loaded["memory"].insert(0, {"name": "response_style", "content": style})
        provider = self.models.system_config.get("models", {}).get("providers", {}).get(route.provider, {})
        response = self.models.generate_request(ModelRequest(
            agent_id=primary_agent_id, provider=route.provider, model=route.model,
            user_message=message, context=loaded, tools=[], max_tokens=max_tokens,
            base_url=provider.get("base_url") or provider.get("endpoint"),
            api_key=provider.get("api_key"), headers=dict(provider.get("headers", {})),
            timeout_seconds=180 if route.provider == "synapse_local" else 60,
            metadata={"mom_operation_id": operation_id, "mom_operation": route.operation.value,
                      "actor_type": context.actor_type},
        ))
        return Output(content=response.content, provider=response.provider, model=response.model or "")
