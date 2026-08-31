from __future__ import annotations

import shlex
from dataclasses import asdict

from synapse.commands.context import CommandContext, CommandInvocation, CommandResult
from synapse.commands.errors import UnknownCommandError
from synapse.commands.handlers.base import BaseCommandHandler
from synapse.commands.registry import CommandMetadata
from synapse.core.permissions import PermissionContext
from synapse.models.types import ModelRequest


class ModelsProvidersCommandHandler(BaseCommandHandler):
    metadata = (
        CommandMetadata(
            name="/capabilities",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="9a4d55fb195ec137876c0eb74ee8242308025551933fec58121a55b1cc7c7711",
        ),
        CommandMetadata(
            name="/capability",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="70185bf967e902616010af70d6a2232494b4d01fa0a6ba51d654c77a38e9f096",
        ),
        CommandMetadata(
            name="/agent-capabilities",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="8215476bd94b4b5e1da7c8a4b266dd444d9f7b5b7c6d00eab87920a7dae03763",
        ),
        CommandMetadata(
            name="/providers",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="3ed26dfea3fd292554511de3f45731fd63deeeab86f73c9a75e75f7f7a8e15ac",
        ),
        CommandMetadata(
            name="/provider",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="03cd8efd8b2a666278bfb12219d59366f60a21ef3e8248f3753f8023797d26b5",
        ),
        CommandMetadata(
            name="/provider-health",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="a28d82830518d0f57e0db665c2b1790a15b5755003e9ff01846aecea44e2ceff",
        ),
        CommandMetadata(
            name="/provider-list",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="05a66f60ca1e85642dc123a4cb20b6167808e2f818b36adb512d2000dc7c0849",
        ),
        CommandMetadata(
            name="/model-list",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="1609ffb5ea3d3ab08926a23bd15b40c3db335f595f169ba67587c78e88f7fb09",
        ),
        CommandMetadata(
            name="/model-refresh",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="42b4968431347625fe801f2308eb71dee1c5fc38ded39618399517770d813eb5",
        ),
        CommandMetadata(
            name="/model-default",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="c60127acb2cfc5dca26316c09c601a57b1a942342d88628389fd6a9e12b2f155",
        ),
        CommandMetadata(
            name="/model-resolve",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="1ff5bfe9923302acaa853e71700e1fe19d7678a3413cc73ea56bb7a8582be21d",
        ),
        CommandMetadata(
            name="/model-capabilities",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="2aad7d5fa197655f60966804b19f299d9328fd39fce6f0d74d63014bbaefacc7",
        ),
        CommandMetadata(
            name="/provider-resolve",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="cbd6d54f717b74ec337f0c3fbf18c548dae26a6c0a86c1ed898b9073a3cba2fc",
        ),
        CommandMetadata(
            name="/provider-plugins",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="6ba49b8e1feba8e310abac2035ff9b0fd61a73e405fb70dd5b2f8cdab00224c5",
        ),
        CommandMetadata(
            name="/provider-plugin",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="cacdedad1aaed5a267bc71f7ae7bba6aaa81c87c0459cce840da71812eb18160",
        ),
        CommandMetadata(
            name="/provider-plugin-health",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="0c5ef45a86d285954c0d0a04f3a72c3efbc8dbdc2dced374d73b910566edab51",
        ),
        CommandMetadata(
            name="/enable-provider-plugin",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="2904181c1c1add44b2bbb198e00ec3d5c0e6dd04a558c401e27046195041b202",
        ),
        CommandMetadata(
            name="/disable-provider-plugin",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="37fc45c73e86d020dfe7200cf518a76dbe97fb15d67c9b9be8152dcc8e316b6e",
        ),
        CommandMetadata(
            name="/lmstudio-status",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="373c77c10bd4024b7e3453d655dbf098d9dc8ec07d49f1fc021473733050d2f1",
        ),
        CommandMetadata(
            name="/lmstudio-models",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="baa4b59e8e22b1caa6bb639b3ed9dfeb3a0f6b86c770beaa4109fe4cea5505ac",
        ),
        CommandMetadata(
            name="/lmstudio-chat",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="300c065b3d24469345083b2e9a53be4e7d2fbc38644f2b207c0179202b23655a",
        ),
        CommandMetadata(
            name="/local-chat",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="98eeab9f9d9655060a7fbd91e1407cfe5ac1ebbdc8acd61732f4ebbe259d5aed",
        ),
        CommandMetadata(
            name="/local-chat-agent",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="a5d8ad9401461dc22ae0a97fce926b1365b8f858b12d336c283f4c33d9f8dade",
        ),
        CommandMetadata(
            name="/local-chat-conversation",
            aliases=(),
            domain="models_providers",
            handler="ModelsProvidersCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="94e542e85436d80e8155beee54103f8cc48729923228c2a98ae470729edf9509",
        ),
    )

    def execute(
        self,
        command_context: CommandContext,
        invocation: CommandInvocation,
    ) -> CommandResult:
        command = invocation.command_name
        argument_text = invocation.argument_text
        context = command_context.permission
        if command == "/capabilities":
            return self._capabilities()
        if command == "/capability":
            return self._capability(argument_text)
        if command == "/agent-capabilities":
            return self._agent_capabilities(context, argument_text)
        if command == "/providers":
            return self._providers()
        if command == "/provider":
            return self._provider(argument_text)
        if command == "/provider-health":
            return self._provider_health()
        if command == "/provider-list":
            return self._providers()
        if command == "/model-list":
            return self._model_list()
        if command == "/model-refresh":
            return self._model_refresh()
        if command == "/model-default":
            return self._model_default(argument_text)
        if command == "/model-resolve":
            return self._model_resolve(argument_text)
        if command == "/model-capabilities":
            return self._model_capabilities(argument_text)
        if command == "/provider-resolve":
            return self._provider_resolve(argument_text)
        if command == "/provider-plugins":
            return self._provider_plugins()
        if command == "/provider-plugin":
            return self._provider_plugin(argument_text)
        if command == "/provider-plugin-health":
            return self._provider_plugin_health()
        if command == "/enable-provider-plugin":
            return self._enable_provider_plugin(context, argument_text)
        if command == "/disable-provider-plugin":
            return self._disable_provider_plugin(context, argument_text)
        if command == "/lmstudio-status":
            return self._lmstudio_status()
        if command == "/lmstudio-models":
            return self._lmstudio_models()
        if command == "/lmstudio-chat":
            return self._lmstudio_chat(argument_text)
        if command == "/local-chat":
            return self._local_chat(context, argument_text)
        if command == "/local-chat-agent":
            return self._local_chat_agent(context, argument_text)
        if command == "/local-chat-conversation":
            return self._local_chat_conversation(context, argument_text)
        raise UnknownCommandError(command)

    def _capabilities(self) -> CommandResult:
        capabilities = [asdict(item) for item in self.capabilities.list_capabilities()]
        return CommandResult(
            command="/capabilities",
            status="ok",
            output=f"{len(capabilities)} capability(ies).",
            data={"capabilities": capabilities},
        )

    def _capability(self, argument_text: str) -> CommandResult:
        capability_id = argument_text.strip()
        if not capability_id:
            return CommandResult(
                command="/capability",
                status="error",
                output="Usage: /capability <capability_id>",
            )
        capability = self.capabilities.get_capability(capability_id)
        return CommandResult(
            command="/capability",
            status="ok",
            output=f"Capability {capability.capability_id}.",
            data={"capability": asdict(capability)},
        )

    def _agent_capabilities(
        self,
        context: PermissionContext,
        argument_text: str,
    ) -> CommandResult:
        agent_id = argument_text.strip().lower()
        if not agent_id:
            return CommandResult(
                command="/agent-capabilities",
                status="error",
                output="Usage: /agent-capabilities <agent_id>",
            )
        capabilities = [
            asdict(item) for item in self.capabilities.agent_capabilities(agent_id, context=context)
        ]
        return CommandResult(
            command="/agent-capabilities",
            status="ok",
            output=f"{len(capabilities)} capability(ies) for {agent_id}.",
            data={"capabilities": capabilities},
        )

    def _providers(self) -> CommandResult:
        providers = [asdict(item) for item in self.providers.list_providers()]
        return CommandResult(
            command="/providers",
            status="ok",
            output=f"{len(providers)} provider(s).",
            data={"providers": providers},
        )

    def _provider(self, argument_text: str) -> CommandResult:
        provider_id = argument_text.strip()
        if not provider_id:
            return CommandResult(
                command="/provider",
                status="error",
                output="Usage: /provider <provider_id>",
            )
        provider = self.providers.get_provider(provider_id)
        return CommandResult(
            command="/provider",
            status="ok",
            output=f"Provider {provider.provider_id}.",
            data={"provider": asdict(provider)},
        )

    def _provider_health(self) -> CommandResult:
        health = [asdict(item) for item in self.providers.list_provider_health()]
        return CommandResult(
            command="/provider-health",
            status="ok",
            output=f"{len(health)} provider health record(s).",
            data={"provider_health": health},
        )

    def _model_list(self) -> CommandResult:
        models = [asdict(item) for item in self.chat.model_hub.list_catalog()]
        return CommandResult("/model-list", "ok", f"{len(models)} model(s).", {"models": models})

    def _model_refresh(self) -> CommandResult:
        result = self.chat.model_hub.refresh()
        return CommandResult(
            "/model-refresh", "ok", "Model catalog refreshed.", {"result": asdict(result)}
        )

    def _model_default(self, argument_text: str) -> CommandResult:
        if not argument_text.strip():
            defaults = self.chat.model_hub.get_defaults()
            return CommandResult(
                "/model-default", "ok", "Loaded model defaults.", {"defaults": asdict(defaults)}
            )
        provider, _, model = argument_text.strip().partition(" ")
        if not model:
            return CommandResult(
                "/model-default", "error", "Usage: /model-default <provider> <model>"
            )
        defaults = self.chat.model_hub.update_defaults(model, provider, provider)
        return CommandResult(
            "/model-default", "ok", "Updated model defaults.", {"defaults": asdict(defaults)}
        )

    def _model_resolve(self, argument_text: str) -> CommandResult:
        agent_id, _, override = argument_text.strip().partition(" ")
        if not agent_id:
            return CommandResult(
                "/model-resolve", "error", "Usage: /model-resolve <agent> [provider/model]"
            )
        provider_override = model_override = None
        if override:
            provider_override, _, model_override = override.partition("/")
        selection = self.chat.agent_runtime.models.resolve_selection(
            self.agents.get(agent_id),
            provider_override=provider_override or None,
            model_override=model_override or None,
        )
        return CommandResult(
            "/model-resolve", "ok", "Resolved model selection.", {"selection": asdict(selection)}
        )

    def _model_capabilities(self, argument_text: str) -> CommandResult:
        provider_id = argument_text.strip()
        adapter = self.chat.agent_runtime.models.adapters.get(provider_id)
        if not adapter:
            return CommandResult(
                "/model-capabilities", "error", f"Provider not found: {provider_id}"
            )
        resolver = getattr(adapter, "capabilities", None)
        capabilities = sorted(resolver()) if callable(resolver) else ["text_generation"]
        return CommandResult(
            "/model-capabilities",
            "ok",
            "Loaded provider capabilities.",
            {"provider_id": provider_id, "capabilities": capabilities},
        )

    def _provider_resolve(self, argument_text: str) -> CommandResult:
        capability_id = argument_text.strip()
        if not capability_id:
            return CommandResult(
                command="/provider-resolve",
                status="error",
                output="Usage: /provider-resolve <capability_id>",
            )
        explanation = self.providers.explain_provider_resolution(capability_id)
        selected = explanation.get("selected")
        output = (
            f"Provider {selected['provider_id']} selected for {capability_id}."
            if selected
            else f"No provider selected for {capability_id}."
        )
        return CommandResult(
            command="/provider-resolve",
            status="ok" if selected else "error",
            output=output,
            data=explanation,
        )

    def _provider_plugins(self) -> CommandResult:
        plugins = [asdict(plugin) for plugin in self.provider_plugins.list_plugins()]
        return CommandResult(
            command="/provider-plugins",
            status="ok",
            output=f"{len(plugins)} provider plugin(s).",
            data={"plugins": plugins},
        )

    def _provider_plugin(self, argument_text: str) -> CommandResult:
        plugin_id = argument_text.strip()
        if not plugin_id:
            return CommandResult(
                command="/provider-plugin",
                status="error",
                output="Usage: /provider-plugin <plugin_id>",
            )
        plugin = self.provider_plugins.get_plugin(plugin_id)
        return CommandResult(
            command="/provider-plugin",
            status="ok",
            output=f"Provider plugin {plugin.plugin_id}: {plugin.plugin_type}",
            data={
                "plugin": asdict(plugin),
                "explanation": self.provider_plugins.explain_plugin(plugin_id),
            },
        )

    def _provider_plugin_health(self) -> CommandResult:
        health = [asdict(item) for item in self.provider_plugins.list_plugin_health()]
        return CommandResult(
            command="/provider-plugin-health",
            status="ok",
            output=f"{len(health)} provider plugin health record(s).",
            data={"health": health},
        )

    def _enable_provider_plugin(
        self,
        context: PermissionContext,
        argument_text: str,
    ) -> CommandResult:
        plugin_id = argument_text.strip()
        if not plugin_id:
            return CommandResult(
                command="/enable-provider-plugin",
                status="error",
                output="Usage: /enable-provider-plugin <plugin_id>",
            )
        plugin = self.provider_plugins.enable_plugin(plugin_id, context)
        return CommandResult(
            command="/enable-provider-plugin",
            status="ok",
            output=f"Enabled provider plugin {plugin_id}.",
            data={"plugin": asdict(plugin)},
        )

    def _disable_provider_plugin(
        self,
        context: PermissionContext,
        argument_text: str,
    ) -> CommandResult:
        plugin_id = argument_text.strip()
        if not plugin_id:
            return CommandResult(
                command="/disable-provider-plugin",
                status="error",
                output="Usage: /disable-provider-plugin <plugin_id>",
            )
        plugin = self.provider_plugins.disable_plugin(plugin_id, context)
        return CommandResult(
            command="/disable-provider-plugin",
            status="ok",
            output=f"Disabled provider plugin {plugin_id}.",
            data={"plugin": asdict(plugin)},
        )

    def _lmstudio_status(self) -> CommandResult:
        status = self.lmstudio.explain_status()
        health = status["health"]
        return CommandResult(
            command="/lmstudio-status",
            status="ok" if health.get("available") else "error",
            output=health.get("message") or "LM Studio status checked.",
            data=status,
        )

    def _lmstudio_models(self) -> CommandResult:
        models = [asdict(model) for model in self.lmstudio.list_models()]
        return CommandResult(
            command="/lmstudio-models",
            status="ok",
            output=f"{len(models)} LM Studio model(s).",
            data={"models": models},
        )

    def _lmstudio_chat(self, argument_text: str) -> CommandResult:
        parts = shlex.split(argument_text)
        message = " ".join(parts).strip()
        if not message:
            return CommandResult(
                command="/lmstudio-chat",
                status="error",
                output='Usage: /lmstudio-chat "<message>"',
            )
        try:
            config = self.lmstudio.load_config()
            result = self.models.generate_request(
                ModelRequest(
                    agent_id="command-user",
                    provider="lmstudio",
                    model=config.default_model,
                    base_url=config.base_url,
                    user_message=message,
                    context={},
                    timeout_seconds=float(config.timeout_seconds),
                )
            )
        except Exception as exc:
            return CommandResult(
                command="/lmstudio-chat",
                status="error",
                output=str(exc),
            )
        return CommandResult(
            command="/lmstudio-chat",
            status="ok",
            output=result.content,
            data={"result": asdict(result)},
        )

    def _local_chat(self, context: PermissionContext, argument_text: str) -> CommandResult:
        message = " ".join(shlex.split(argument_text)).strip()
        if not message:
            return CommandResult(
                command="/local-chat",
                status="error",
                output='Usage: /local-chat "<message>"',
            )
        if not self.chat:
            return CommandResult("/local-chat", "error", "Chat runtime is unavailable.")
        try:
            result = self.chat.submit_turn(context, content=message)
        except Exception as exc:
            return CommandResult("/local-chat", "error", str(exc))
        return CommandResult(
            command="/local-chat",
            status="ok",
            output=result.response,
            data={"result": asdict(result), "conversation_id": result.conversation_id},
        )

    def _local_chat_agent(self, context: PermissionContext, argument_text: str) -> CommandResult:
        parts = shlex.split(argument_text)
        if len(parts) < 2:
            return CommandResult(
                command="/local-chat-agent",
                status="error",
                output='Usage: /local-chat-agent <agent_id> "<message>"',
            )
        agent_id = parts[0]
        message = " ".join(parts[1:]).strip()
        if not self.chat:
            return CommandResult("/local-chat-agent", "error", "Chat runtime is unavailable.")
        try:
            result = self.chat.submit_turn(context, content=message, target_agent_id=agent_id)
        except Exception as exc:
            return CommandResult("/local-chat-agent", "error", str(exc))
        return CommandResult(
            command="/local-chat-agent",
            status="ok",
            output=result.response,
            data={
                "result": asdict(result),
                "conversation_id": getattr(result, "conversation_id", result.session_id),
            },
        )

    def _local_chat_conversation(
        self, context: PermissionContext, argument_text: str
    ) -> CommandResult:
        parts = shlex.split(argument_text)
        if len(parts) < 2:
            return CommandResult(
                command="/local-chat-conversation",
                status="error",
                output='Usage: /local-chat-conversation <conversation_id> "<message>"',
            )
        conversation_id = parts[0]
        message = " ".join(parts[1:]).strip()
        if not self.chat:
            return CommandResult(
                "/local-chat-conversation",
                "error",
                "Chat runtime is unavailable.",
            )
        try:
            result = self.chat.submit_turn(
                context, content=message, conversation_id=conversation_id
            )
        except Exception as exc:
            return CommandResult("/local-chat-conversation", "error", str(exc))
        return CommandResult(
            command="/local-chat-conversation",
            status="ok",
            output=result.response,
            data={"result": asdict(result), "conversation_id": result.conversation_id},
        )
