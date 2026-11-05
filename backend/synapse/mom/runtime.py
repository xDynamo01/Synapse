from __future__ import annotations

from uuid import uuid4

from synapse.core.events import EventBus
from synapse.core.exceptions import PermissionDenied, ValidationError
from synapse.core.execution_policy import ResourcePolicy
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.mom.contracts import (
    Configuration,
    ConfigurationPort,
    InferencePort,
    Operation,
    PrimaryPort,
    ResourcePolicyPort,
    Result,
    Route,
)
from synapse.mom.selection import classify_operation


class MoMRuntime:
    def __init__(self, primary: PrimaryPort, configurations: ConfigurationPort,
                 inference: InferencePort, permissions: PermissionManager, events: EventBus):
        self.primary = primary
        self.configurations = configurations
        self.inference = inference
        self.permissions = permissions
        self.events = events
        self.resources: ResourcePolicyPort | None = None

    def select_for_chat(self, context: PermissionContext, agent_id: str | None,
                        message: str, workspace_id: str,
                        recent_intent: str | None = None) -> tuple[str, Route, int] | None:
        # Routing is always available. Missing routes use the configured generalist;
        # invalid saved routes still fail visibly. Workers never acquire MoM routing.
        configuration = self.configurations.read(workspace_id)
        if configuration is None:
            return None
        primary_id = self.primary.current_agent(workspace_id)
        if agent_id is not None and agent_id != primary_id:
            return None
        self._admit(context, workspace_id)
        if configuration.primary_agent_id != primary_id:
            raise ValidationError("O Primary mudou. Salve novamente a configuração do MoM.")
        operation = classify_operation(message, recent_intent)
        route = next((route for route in configuration.routes if route.operation == operation), None)
        if route is None:
            if operation != Operation.CONVERSATION and configuration.routes:
                raise ValidationError(f"Configure o modelo de {operation.value} em Settings > MoM.")
            self.events.emit("mom.chat.generalist", primary_id, {
                "workspace_id": workspace_id, "operation": operation.value,
                "reason": "route_not_configured", "selection_policy": "contextual-intent-v2",
            })
            return None
        self.inference.validate_route(route)
        self.events.emit("mom.chat.selected", primary_id, {
            "workspace_id": workspace_id, "agent_id": primary_id,
            "operation": operation.value, "provider_id": route.provider,
            "model_id": route.model, "configuration_revision": configuration.revision,
            "selection_policy": "contextual-intent-v2",
        })
        return primary_id, route, configuration.revision

    def _admit(self, context: PermissionContext, workspace_id: str) -> str:
        primary_id = self.primary.current_agent(workspace_id)
        if context.actor_type == "agent":
            if context.actor_id != primary_id:
                raise PermissionDenied("MoM is reserved for the current Primary Agent.")
        elif context.actor_type != "user":
            raise PermissionDenied("MoM requires a user or the current Primary Agent.")
        self.permissions.require(context, "filesystem.read")
        return primary_id

    def get_configuration(self, context: PermissionContext,
                          workspace_id: str = "default") -> Configuration:
        primary_id = self._admit(context, workspace_id)
        return self.configurations.read(workspace_id) or Configuration(
            workspace_id=workspace_id, primary_agent_id=primary_id,
        )

    def configure(self, context: PermissionContext, workspace_id: str,
                  enabled: bool, routes: tuple[Route, ...], expected_revision: int,
                  resource_policy: ResourcePolicy | None = None) -> Configuration:
        if context.actor_type != "user":
            raise PermissionDenied("Only the user can configure Primary MoM routes.")
        primary_id = self._admit(context, workspace_id)
        self.permissions.require(context, "filesystem.write")
        current = self.configurations.read(workspace_id)
        configuration = Configuration(
            workspace_id=workspace_id, primary_agent_id=primary_id, enabled=enabled,
            revision=expected_revision + 1, routes=routes,
            resource_policy=resource_policy or (
                current.resource_policy if current else ResourcePolicy.RESPONSIVE
            ),
        )
        if enabled:
            for route in routes:
                self.inference.validate_route(route)
        self.configurations.write(configuration, expected_revision)
        if self.resources is not None:
            self.resources.apply(configuration.resource_policy)
        self.events.emit("mom.configured", context.actor_id, {
            "workspace_id": workspace_id, "agent_id": primary_id,
            "revision": configuration.revision, "enabled": enabled,
            "resource_policy": configuration.resource_policy,
        })
        return configuration

    def resource_status(self, context: PermissionContext, workspace_id: str = "default") -> dict[str, object]:
        configuration = self.get_configuration(context, workspace_id)
        return {"selected_policy": configuration.resource_policy,
                **(self.resources.status() if self.resources else {"available": False})}

    def execute(self, context: PermissionContext, operation: Operation, message: str,
                workspace_id: str = "default") -> Result:
        if not message.strip() or len(message) > 32000:
            raise ValidationError("MoM input must contain between 1 and 32000 characters.")
        primary_id = self._admit(context, workspace_id)
        configuration = self.get_configuration(context, workspace_id)
        if not configuration.enabled:
            raise ValidationError("Primary MoM is not enabled.")
        if configuration.primary_agent_id != primary_id:
            raise ValidationError("Primary Agent changed. Reconfigure MoM routes for this Primary.")
        route = next((item for item in configuration.routes if item.operation == operation), None)
        if route is None:
            raise ValidationError(f"No Primary MoM route configured for {operation}.")
        self.inference.validate_route(route)
        if self._admit(context, workspace_id) != primary_id:
            raise ValidationError("Primary Agent changed before MoM admission.")
        operation_id = str(uuid4())
        activity = {
            "operation_id": operation_id, "operation": operation.value,
            "workspace_id": workspace_id, "agent_id": primary_id,
            "provider_id": route.provider, "model_id": route.model,
            "configuration_revision": configuration.revision,
        }
        self.events.emit("mom.operation.started", primary_id, activity)
        try:
            output = self.inference.generate(context, primary_id, route, message, operation_id)
            if output.provider != route.provider or output.model != route.model:
                raise ValidationError("MoM response did not match the selected route.")
        except Exception as exc:
            self.events.emit("mom.operation.failed", primary_id, {
                **activity, "error_type": type(exc).__name__,
            })
            raise
        self.events.emit("mom.operation.completed", primary_id, activity)
        return Result(**output.model_dump(), operation_id=operation_id,
                      operation=operation, primary_agent_id=primary_id,
                      configuration_revision=configuration.revision)
