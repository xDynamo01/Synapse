# ADR 0072: Agent Multimodal Context Bridge

## Status

Accepted.

## Context

`ContextFusionRuntime` can build read-only context snapshots from conversations,
missions, multimodal sessions, perception signals, health, readiness, and
delegation state. Agent processing still used only traditional memory,
conversation context, and delegation context.

Future voice and multimodal chat flows need a controlled way to expose
fused context to agents without turning perception into memory or automation.

## Decision

Add an optional `LoadedContext.multimodal_context` field and let
`AgentWorker` attach a serialized `ContextFusionResult` when processing:

- conversation-backed inbox messages
- delegations linked to a conversation
- delegations linked to a mission
- records that carry a multimodal session id in metadata

The bridge is controlled by:

```text
DATA_DIR/config/multimodal_context_policy.yaml
```

The policy can disable the bridge, include or exclude conversations, missions,
or multimodal sessions, limit signals, and remove health/readiness summaries
from the attached context.

## Consequences

- Existing contexts remain compatible; the field is optional.
- Missing perception signals do not fail worker processing.
- Context fusion failures emit an event and the worker continues without the
  multimodal block.
- Agent Runtime receives fused context only as structured read-only input.
- The bridge does not infer emotion, write memory, create tasks, create
  approvals, or automate decisions.

## Events

- `agent.multimodal_context.attached`
- `agent.multimodal_context.skipped`
- `agent.multimodal_context.failed`

## Interfaces

Commands:

- `/agent-context-preview <agent_id> <conversation_id>`
- `/agent-multimodal-policy`

API:

- `GET /agents/{agent_id}/context-preview/{conversation_id}`
- `GET /agent-multimodal-policy`

Health/readiness expose simple availability flags:

- `agent_multimodal_bridge_available`
- `agent_multimodal_bridge.ready`

## Non-Goals

- No real providers.
- No Whisper, MediaPipe, camera, microphone, visualization, animation, or voice UI.
- No emotional, psychological, social, or intent inference.
- No memory writes or RAG.
- No planner, workflow engine, or perception-based automation.
