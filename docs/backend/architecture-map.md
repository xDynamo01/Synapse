# Backend Architecture Map

Date: 2026-07-09
Scope: current backend state, before consolidation

This document maps the current Synapse backend as it exists today. It is a
snapshot for freeze-and-cleanup work, not a target architecture proposal.

## 1. Current Structure

The backend is centered on `backend/synapse/core/app.py` and exposed through a
single monolithic API router in `backend/synapse/api/routes.py`.

### Core and bootstrap

- `backend/synapse/core/`
  - app bootstrap, config, data directory, events, permissions, exceptions,
    serialization, and model routing.
- Main coupling point:
  - `core/app.py` builds most runtimes and acts as the composition root.

### Product runtimes

- `backend/synapse/agents/`
  - identity, registry, provisioning, admin, audit, presence, and
    agent runtime orchestration.
- `backend/synapse/chat/` and `backend/synapse/conversations/`
  - chat turn flow, session persistence, conversation history, summaries, and
    local chat entry points.
- `backend/synapse/tools/`, `backend/synapse/tool_intents/`,
  `backend/synapse/tool_discovery/`, `backend/synapse/approvals/`,
  `backend/synapse/execution_router/`
  - tool catalog, execution, policy checks, intent persistence, approval flow,
    and routing decisions.
- `backend/synapse/model_hub/`, `backend/synapse/providers/`,
  `backend/synapse/provider_plugins/`, `backend/synapse/model_providers/`,
  `backend/synapse/models/`
  - model discovery, provider selection, provider settings, plugin metadata,
    and model adapters.
- `backend/synapse/audio/`, `backend/synapse/voice/`,
  `backend/synapse/speech_adapters/`, `backend/synapse/speech_pipeline/`
  - audio normalization, voice sessions, STT/TTS adapter selection, and the
    speech pipeline.
- `backend/synapse/memory/`, `backend/synapse/context/`,
  `backend/synapse/context_fusion/`
  - persisted memory and context loading/fusion.
- `backend/synapse/missions/`, `backend/synapse/mission_control/`,
  `backend/synapse/delegation*`, `backend/synapse/dead_letter/`,
  `backend/synapse/scheduler/`, `backend/synapse/daemon/`
  - mission orchestration, delegation, background jobs, daemon loop, and
    failure recovery.
- `backend/synapse/health/`, `backend/synapse/readiness/`,
  `backend/synapse/system_insight/`
  - diagnostics, readiness, and local machine insight.
- `backend/synapse/vision/`, `backend/synapse/multimodal/`,
  `backend/synapse/perception/`
  - visual and multimodal signals.
- `backend/synapse/notifications/`, `backend/synapse/presence/`,
  `backend/synapse/lifecycle/`, `backend/synapse/retention/`,
  `backend/synapse/commands/`, `backend/synapse/mcp/`, `backend/synapse/mcp_bridge/`
  - operational projections and administrative surfaces.
- `backend/synapse/contracts/`
  - frontend-agnostic DTOs and protocols with no runtime imports.

## 2. Dependency Shape

### Primary coupling points

- `core/app.py`
  - composition root and runtime wiring.
- `api/routes.py`
  - monolithic FastAPI router that exposes the whole product surface.
- `chat/runtime.py`
  - couples context loading, memory, model routing, presence, and session
    persistence.
- `voice/runtime.py`
  - owns factual voice sessions and events and coordinates audio and speech
    adapters without visualization authority.
- `context_fusion/runtime.py`
  - merges history, memory, mission state, perception, and external context.
- `tools/runtime.py`
  - combines execution, seed tool wiring, and domain-specific helpers.

### Observed architectural tension

- provider stacks overlap semantically:
  - `providers/`
  - `model_providers/`
  - `provider_plugins/`
  - `speech_adapters/`
  - `speech_pipeline/`
- mocks and placeholders are still mixed into product-facing paths in several
  domains.
- `commands/runtime.py` has become a broad administrative surface with many
  debug and diagnostic commands.

## 3. Route Surface

The current API is centralized in `backend/synapse/api/routes.py`. The route
surface spans:

- agents
- audio / voice / speech
- frontend-owned visualization and animation are outside the backend runtime
- chat / conversations / context
- agent communication / notifications
- capabilities / providers / model hub / models
- health / readiness / insight
- missions / delegation / mission control
- notifications / presence / lifecycle / scheduler / daemon / workers
- execution / decisions / tasks / trace / events
- MCP / bridge / runtime catalog
- retention / dead-letter / migrations
- admin / policy / approvals / agent admin

The router is functional but too large to safely evolve without more domain
segmentation.

## 4. Providers, Adapters, and Plugins

### Model-related

- `backend/synapse/model_providers/lmstudio.py`
  - real LM Studio integration.
- `backend/synapse/models/adapters.py`
  - includes `MockModelAdapter`, `OllamaModelAdapter`, and an
    OpenAI-compatible path that still needs consolidation.

### Speech-related

- `backend/synapse/speech_adapters/`
  - includes mock STT/TTS/analysis adapters plus Faster Whisper and Piper
    adapters.
- `backend/synapse/speech_pipeline/`
  - still contains mock-facing session flows.

### Plugin metadata

- `backend/synapse/provider_plugins/`
  - metadata-only catalog for future plugin enablement and health tracking.

## 5. Mocks and Placeholders

Current product surface still contains mock or placeholder behavior in multiple
areas:

- audio mock transcribe and synthesize routes
- speech mock STT/TTS/analysis routes and adapters
- vision mock providers isolated behind internal test helpers, with no mock API routes
- communication mock provider
- mock model adapter
- placeholder OpenAI-compatible model path
- mixed diagnostic routes that behave like product endpoints

These are useful for development, but they need explicit isolation from the
real runtime path.

## 6. Persisted Data Layout

The backend persists state under `data/`. Important areas include:

- `data/config/`
  - runtime configuration and policy YAML files.
- `data/agents/<agent_id>/`
  - agent config, skills, inbox, memory, and audit-related state.
- `data/memory/`
  - global, system, and user memory files.
- `data/conversations/`
  - conversation sessions and message logs.
- `data/chats/`
  - chat session state.
- `data/audio/`
  - audio sessions and mock device state.
- `data/voice/`
  - voice settings and local model cache.
- `data/model_hub/`
  - model catalog, defaults, and discovered-folder state.
- `data/provider_plugins/`
  - plugin manifests and plugin state.
- `data/context_fusion/`
  - fused context snapshots.
- `data/mcp/`
  - server and tool catalog metadata.
- `data/daemon/`, `data/presence/`, `data/lifecycle/`
  - daemon identity and runtime projections.
- `data/jobs/`, `data/scheduler/`, `data/locks/`
  - background job queue, recurring jobs, and scheduler lock.
- `data/notifications/`, `data/retention/`, `data/dead_letter/`
  - operational projections.
- `data/tool_intents/`
  - persisted tool intent review state.
- `data/vision/`, `data/multimodal/`, `data/perception/`
  - multimodal session data and signal logs.

## 7. Config Files

Key configuration files currently in use:

- `data/config/system.yaml`
- `data/config/permissions.yaml`
- `data/config/provider_policy.yaml`
- `data/config/provider_settings.yaml`
- `data/config/provider_plugin_policy.yaml`
- `data/config/lmstudio_provider.yaml`
- `data/config/local_chat_policy.yaml`
- `data/config/voice_settings.yaml`
- `data/config/speech_adapter_policy.yaml`
- `data/config/speech_pipeline_policy.yaml`
- `data/config/notification_policy.yaml`
- `data/config/scheduler_policy.yaml`
- `data/config/readiness_policy.yaml`
- `data/config/multimodal_context_policy.yaml`
- `data/config/agent_tool_calling_policy.yaml`
- `data/config/agent_provisioning_policy.yaml`
- `data/config/agent_admin_retention_policy.yaml`
- `data/config/admin_policy.yaml`
- `data/config/delegation_*.yaml`
- `data/agents/<agent_id>/CONFIG.yaml`

These files mix product settings, local defaults, and policy state. The next
consolidation pass should make the schema boundaries explicit.

## 8. Current Risks

- `api/routes.py` is the largest single maintainability risk.
- `commands/runtime.py` has outgrown a simple command surface.
- provider and adapter semantics are duplicated across several modules.
- voice and speech still mix product behavior with dev/test helpers.
- the backend has enough surface area that failures cluster around orchestration
  and cross-runtime behavior rather than isolated CRUD logic.

## 9. Freeze Rule For This Phase

- No backend refactor has been applied yet.
- No new frontend work should be introduced as part of this backend cleanup.
- The next steps should be consolidation by contract, not feature addition.
