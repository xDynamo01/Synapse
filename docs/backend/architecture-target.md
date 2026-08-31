# Backend Target Architecture

Date: 2026-07-09
Status: proposed target structure

This document defines the backend shape Synapse should converge toward before
any new product work is added.

## 1. Target Layout

```text
backend/synapse/
  core/
    config/
    bootstrap/
    events/
    permissions/
    errors/
    serialization/

  contracts/
    dto/
    events/
    capabilities/
    policies/
    api/

  runtime/
    agents/
    chat/
    models/
    voice/
    memory/
    context/
    missions/
    tools/

  infrastructure/
    storage/
    providers/
    scheduler/
    mcp/
    system/
    security/

  integrations/
    lmstudio/
    ollama/
    openai_compatible/
    faster_whisper/
    piper/

  api/
    routers/
      agents.py
      chat.py
      models.py
      voice.py
      memory.py
      context.py
      tools.py
      insight.py
      missions.py
      system.py
      settings.py

  dev/
    mocks/
    fixtures/
    diagnostics/

  tests/
```

## 2. Boundary Rules

- `runtime/` owns behavior and orchestration.
- `api/` is an adapter over runtime, not a second runtime.
- `integrations/` wrap external systems only.
- `contracts/` define shared types and protocols only.
- `core/` stays product-agnostic.
- `dev/mocks/` is never imported by the real runtime unless a dev flag is
  explicit.

## 3. Dependency Direction

Required dependency order:

```text
core
  -> contracts
  -> runtime
  -> api
```

Side boundaries:

- `integrations/` can be used by `runtime/`, but never by `api/` directly.
- `dev/` can depend on contracts and selected runtime seams only in test or
  explicit dev mode.
- `contracts/` cannot import `runtime/`.
- `runtime/` must not import FastAPI.
- `api/` depends on `runtime/` and `contracts/`, not the other way around.

## 4. Runtime Domains

### Agents

- `runtime/agents/` should own:
  - identity
  - config
  - runtime state
  - policy enforcement
  - worker state
  - swarm preparation

### Chat

- `runtime/chat/` should own:
  - turn flow
  - session persistence
  - command dispatch
  - context loading integration

### Models

- `runtime/models/` should own:
  - model selection
  - provider resolution
  - model catalog coordination
  - fallback and capability rules

### Voice

- `runtime/voice/` should own:
  - voice session orchestration
  - STT/TTS/voice-analysis coordination
  - session state and validation

### Memory and Context

- `runtime/memory/` should own:
  - memory projections
  - persistence contracts
  - storage backends
- `runtime/context/` should own:
  - context fusion
  - history aggregation
  - memory, mission, perception, and tool context assembly

### Missions

- `runtime/missions/` should own:
  - mission state
  - task assignment
  - dependency tracking
  - delegation and queue semantics

### Tools

- `runtime/tools/` should own:
  - tool execution
  - policy gating
  - tool discovery integration
  - intent handoff

## 5. Infrastructure Domains

- `infrastructure/storage/`
  - filesystem and persistence helpers.
- `infrastructure/providers/`
  - concrete external providers and provider registries.
- `infrastructure/scheduler/`
  - queue and recurring job mechanics.
- `infrastructure/mcp/`
  - MCP catalog, bridge, and metadata.
- `infrastructure/system/`
  - machine inspection and local diagnostics.
- `infrastructure/security/`
  - secrets, masking, local credential handling, and boundary checks.

## 6. Integration Domains

### Model integrations

- `integrations/lmstudio/`
- `integrations/ollama/`
- `integrations/openai_compatible/`

### Voice integrations

- `integrations/faster_whisper/`
- `integrations/piper/`

These modules should only adapt external protocols to internal contracts. They
should not own product policy or route logic.

## 7. Contract Set

The following contracts need to exist before further refactoring:

- `Agent`
- `ModelProvider`
- `ModelRuntime`
- `VoiceSTTProvider`
- `VoiceTTSProvider`
- `VoiceAnalysisProvider`
- `MemoryStore`
- `ContextProvider`
- `ToolProvider`
- `MissionRuntime`
- `SystemInsightProvider`

Each contract should have:

- interface or protocol
- DTOs
- structured errors
- emitted events
- minimal tests

## 8. API Router Strategy

The monolithic `routes.py` should be split by domain into separate routers:

- `api/routers/agents.py`
- `api/routers/chat.py`
- `api/routers/models.py`
- `api/routers/voice.py`
- `api/routers/memory.py`
- `api/routers/context.py`
- `api/routers/tools.py`
- `api/routers/insight.py`
- `api/routers/missions.py`
- `api/routers/system.py`
- `api/routers/settings.py`

Compatibility rule:

- existing endpoints should be preserved when possible
- placeholder-only endpoints should be marked deprecated, moved to
  `dev/diagnostics/`, or removed if unnecessary
- production routers must not import mock implementations

## 9. Mock Isolation

Mocks must live under `dev/mocks/` and remain explicitly gated.

Allowed runtime behavior:

- use mock only when `SYNAPSE_DEV_MODE=true`
- or when a provider is explicitly configured as mock

Otherwise the runtime should fail clearly with a structured
`provider_not_configured` error or an equivalent unsupported-provider error.

## 10. Consolidation Priorities

The target architecture should be reached in this order:

1. contracts
2. API router split
3. mock isolation
4. provider consolidation
5. voice separation
6. memory/context consolidation
7. agent/swarm preparation
8. insight and system normalization
9. configuration cleanup
10. tests and documentation

## 11. Acceptance Signal

The target layout is considered ready when:

- runtime no longer depends on FastAPI
- API routers are domain-scoped
- mocks are isolated from product runtime
- providers are consolidated behind explicit contracts
- voice no longer has ambiguous STT/TTS/provider ids
- memory and context are composed through contracts
- tests cover the domain seams
- documentation reflects the actual runtime boundary
