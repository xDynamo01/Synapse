# ADR 0071: Context Fusion Runtime

## Status

Accepted.

## Context

Synapse now has independent sources of contextual information: conversations, missions, delegations, multimodal sessions, audio/vision contracts, perception signals, health, and readiness. Future agent runtimes should consume a consistent structured context instead of rebuilding it from many domain runtimes.

## Decision

Introduce `ContextFusionRuntime` as a read-only aggregation and validation layer.

The runtime defines:

- `InteractionContext`
- `ContextSignalGroup`
- `ContextSnapshot`
- `ContextConsistency`
- `ContextFusionResult`

Optional snapshots persist under:

```text
DATA_DIR/context_fusion/snapshots/{context_id}.yaml
```

## Scope

Context Fusion consumes:

- Conversation Runtime
- Mission Runtime
- Mission Context Runtime
- Perception Runtime
- Multimodal Runtime
- Health Runtime
- Readiness Runtime
- Delegation Runtime

It does not alter those runtimes.

## Rules

Context Fusion does not infer:

- emotion
- intention
- sarcasm
- irony
- psychological state
- social judgment

It only consolidates information that already exists.

## Validation

`validate_context()` reports missing sources and warnings for:

- missing conversation
- missing mission
- missing multimodal session
- missing signals
- missing participants
- incomplete context

Validation is non-blocking.

## Non-Goals

This stage does not implement:

- LLM reasoning
- emotional AI
- social inference
- vector memory
- RAG
- planner
- workflow engine
- frontend visualization or animation
- UI
- Agent Runtime injection

## Consequences

Benefits:

- Future Agent Runtime integration can consume one structured object.
- Context completeness can be inspected before agent use.
- Multimodal and mission context remain decoupled.

Limitations:

- Context is structural, not semantic.
- No ranking, summarization model, or interpretation exists.
- Fusion is not yet injected into Agent Runtime.
