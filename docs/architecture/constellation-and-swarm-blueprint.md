# Synapse Constellation and Swarm Blueprint

Status: research / implementation blueprint.

Scope: define how Synapse should implement a distinctive Constellation surface
and a governed Swarm execution model without importing external frameworks or
trusting external repository instructions.

## Sources reviewed

Primary/reference sources:

- PixiJS v8 ParticleContainer documentation:
  <https://pixijs.com/8.x/guides/components/scene-objects/particle-container>
- D3 force simulation documentation:
  <https://d3js.org/d3-force>
- OpenAI Agents orchestration and handoffs:
  <https://developers.openai.com/api/docs/guides/agents/orchestration>
- Microsoft AutoGen Swarm documentation:
  <https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/swarm.html>
- CrewAI introduction, Flows and Crews:
  <https://docs.crewai.com/v1.15.18/en/introduction>

External material was used only for architecture patterns. No code, prompts or
repository instructions were copied into Synapse.

## Current Synapse fit

Synapse already has most of the backend vocabulary needed:

- `MissionRuntime`
- `SwarmRuntime`
- delegation/runtime concepts
- ephemeral agents
- tool execution and tool intent boundaries
- operational projection snapshot/events/SSE
- frontend activity adapter and activity scene state
- PixiJS/Canvas Presence surface

The missing product piece is not “draw some nodes”. The real differentiator is:

```text
governed multi-agent execution
→ factual operational projection
→ legible animated constellation
→ user can understand who is doing what, why, and what changed
```

## Constellation design direction

### Principle

The Constellation should be a live operational map, not decorative telemetry.
Every visible node or edge must correspond to a backend fact.

Allowed baseline:

- Primary Agent always visible.
- Model/Runtime visible when selected/known.
- Search/Tool/Voice/Memory nodes appear only when they participate.
- Swarm/Worker nodes appear only when a real swarm/delegation run exists.

Do not invent fake workers, fake tools or fake swarm activity to make the
screen look busy.

### Rendering model

Use a layered renderer:

1. Ambient field
   - theme-aware atmospheric background;
   - low-frequency particles;
   - no semantic state.

2. Stable constellation graph
   - factual nodes;
   - factual edges;
   - stable layout seeded by entity IDs.

3. Activity pulses
   - short-lived particles or edge pulses from event stream;
   - driven by recent operational facts.

4. Labels and focus state
   - only for selected/hovered/primary nodes by default;
   - avoid turning the scene into a dashboard.

### Layout

Use a deterministic force-informed layout, not random positions every render.

Recommended approach:

- Keep a small custom layout for normal mode.
- Optionally use D3 force simulation offline/incrementally for complex graphs:
  center force, link force, many-body repulsion and collision force.
- Persist or memoize node positions by entity ID to avoid visual jumping.
- Apply semantic anchors:
  - Primary Agent near center.
  - Model/Runtime close to Primary Agent.
  - Tools/resources in outer orbit.
  - Workers/agents distributed around mission/swarm center.
  - Errors/approval-needed nodes pulled slightly forward visually, not moved
    unpredictably.

D3 should be treated as a layout calculator, not as the renderer. Rendering
should stay in the current frontend visual layer.

### PixiJS usage

PixiJS is a good fit for the final Constellation because:

- graph nodes, edge pulses and particles are GPU-friendly;
- `ParticleContainer` is suitable for many simple particles;
- static and dynamic properties can be separated for performance.

Important constraint:

- `ParticleContainer` is for simple particle sprites. It should not own complex
  interactive graph nodes, labels or nested child objects.

Recommended split:

```text
Pixi Container: scene root
├─ ParticleContainer: ambient particles
├─ Graphics/mesh layer: arcs, rings, static edges
├─ Graphics/sprite layer: nodes and halos
├─ ParticleContainer: transient edge pulses
└─ DOM/Canvas overlay or Pixi text: selected labels and diagnostics
```

### Visual behavior

Idle:

- Primary Agent and Model/Runtime visible.
- Ambient motion extremely slow.
- No false “processing”.

Thinking/processing:

- Primary Agent halo strengthens.
- Model/Runtime edge pulses.
- Active tool/resource edge pulses only when actual tool events exist.

Swarm:

- Mission/Swarm node appears as the temporary gravity center.
- Agents/workers orbit the swarm node by role.
- Handoffs/delegations animate as directional edge pulses.
- Completed worker nodes settle; failed nodes hold a subtle error halo.

### Failure modes to prevent

- Node exists in adapter state but is drawn as text only.
- SVG/canvas viewport clips glow or particles.
- fallback renderer and new renderer both render simultaneously.
- activity state says `ready` with one node but graph layer never materializes.
- stale bundle loads an old renderer.
- text diagnostic overlays become the product UI.

## Swarm architecture direction

### Pattern comparison

There are three relevant patterns:

1. Manager with agents-as-tools
   - One primary agent owns the final answer.
   - Specialists are bounded capabilities.
   - Best first production path for Synapse.

2. Handoffs
   - A specialist takes over a branch of the conversation.
   - Useful when ownership genuinely changes.
   - Requires clear routing and history rules.

3. Crew/Flow
   - A structured workflow owns state and calls a team for complex work.
   - Useful for longer workplace tasks.

For Synapse v0.01/v0.02, the safest product direction is:

```text
Primary Agent as manager
→ bounded specialist agents/tools
→ explicit handoff only when user or policy allows ownership transfer
→ mission/swarm record owns long-running state
```

This matches Synapse governance better than importing a generic autonomous
framework.

### Core backend contract

Swarm should be represented as a governed execution record:

```text
SwarmRun
├─ swarm_run_id
├─ conversation_id / project_id
├─ requester
├─ objective
├─ status
├─ participants[]
├─ allowed_handoffs[]
├─ tasks[]
├─ events[]
├─ artifacts[]
├─ approvals[]
└─ final_result
```

Participant:

```text
SwarmParticipant
├─ participant_id
├─ agent_id
├─ role
├─ model/provider
├─ allowed_tools
├─ current_task
├─ status
└─ authority_scope
```

Event:

```text
SwarmEvent
├─ event_id
├─ swarm_run_id
├─ type
├─ source_participant_id
├─ target_participant_id?
├─ related_tool_execution_id?
├─ related_message_id?
├─ timestamp
└─ safe_summary
```

### Execution rules

- No hidden autonomous swarm on normal chat.
- User-visible action starts a swarm.
- Every participant has explicit role, tools and authority.
- Handoffs are events, not prompt text.
- Tool calls remain under Tool Runtime / Tool Intent authority.
- Search uses the configured `web_search` path, not custom HTTP from agents.
- Each run has cancellation and recovery semantics.
- The Primary Agent may summarize, but should not fabricate participant work.

### Minimal viable swarm

First implementation should be intentionally small:

```text
Research Swarm
├─ Primary Agent: owns final answer
├─ Search Agent: uses web_search only
├─ Critic/Verifier Agent: checks cited facts against retrieved snippets
└─ Synthesizer path: Primary Agent writes final answer
```

This is the strongest match with the newly configured SearXNG capability and
with Synapse as a workplace product.

## Operational projection contract

The Constellation should consume one neutral projection shape:

```text
OperationalEntity
├─ entityId
├─ kind: agent | worker | model | tool-execution | search | memory-source | swarm | mission | runtime
├─ role
├─ status
├─ label
├─ currentTask
├─ currentOperation
├─ parentEntityId
├─ resources
└─ metadata

OperationalRelation
├─ relationId
├─ kind: controls | handoff | delegation | tool-use | model-call | memory-read | result-return
├─ sourceEntityId
├─ targetEntityId
├─ active
└─ metadata
```

The renderer should not know internal backend classes. The backend projection
must normalize Mission/Swarm/Tool/Search/Voice facts into this shape.

## Implementation order

### Phase 1 — Constellation renderer reliability

Goal: make the visual layer trustworthy before adding real swarm complexity.

Tasks:

1. Remove the text-only diagnostic as normal rendering.
2. Keep debug facts behind a dev-only overlay.
3. Ensure baseline Primary Agent + Model/Runtime nodes always render.
4. Prevent clipping by sizing the canvas/world bounds from available viewport.
5. Make fallback mutually exclusive with the real renderer.
6. Add visual regression tests for:
   - idle baseline;
   - processing;
   - one tool edge;
   - reduced motion;
   - resize.

Acceptance:

```text
New Chat
→ Presence/Constellation
→ Primary Agent visible
→ Model/Runtime visible
→ no raw id text as the only visible node
```

### Phase 2 — Search as first factual tool activity

Goal: make Search visibly participate.

Tasks:

1. Emit an operational entity for `web_search`.
2. Emit relation Primary Agent -> Search Tool when search starts.
3. Emit relation Search Tool -> Source Results when results arrive.
4. Show short edge pulses for those events.
5. Keep result contents out of the visual scene; show only safe summaries.

Acceptance:

```text
User asks a search-backed question
→ web_search runs through SearXNG
→ Constellation shows agent, model/runtime, search tool and result/source summary
```

### Phase 3 — Minimal governed Research Swarm

Goal: introduce the product differentiator without broad autonomy.

Tasks:

1. Create a governed `ResearchSwarmRun`.
2. Participants:
   - Primary Agent
   - Search Agent
   - Verifier Agent
3. Use existing Search Runtime.
4. Persist run/events.
5. Project run/events into Operational Projection.
6. Add user-facing start/cancel controls.

Acceptance:

```text
Start Research Swarm
→ Search Agent searches
→ Verifier checks
→ Primary Agent synthesizes
→ Constellation shows factual handoffs/delegations
```

### Phase 4 — General Swarm framework

Goal: turn the first swarm into a reusable governed runtime.

Tasks:

1. Generalize participant registry.
2. Add allowed handoff matrix.
3. Add budget limits:
   - max agents;
   - max turns;
   - max tool calls;
   - max wall-clock time.
4. Add pause/resume/cancel.
5. Add recovery from partial run.
6. Add audit and user-visible timeline.

Acceptance:

```text
Swarm runs are durable, auditable, cancellable and visible in Constellation
```

## Recommended next build slice

Do not start with a full autonomous swarm.

Start with:

```text
Constellation Renderer Reliability Slice
```

Reason:

- The user already sees the Constellation as a product differentiator.
- The current renderer has had visible regressions: clipping, text-only nodes,
  duplicate renderer layers and stale style loading.
- A swarm without a reliable visual projection will look broken even if backend
  execution works.

Then implement:

```text
Search-backed factual activity
```

This uses the newly configured SearXNG path and gives the Constellation a real
workplace behavior before introducing multi-agent orchestration.

## Non-goals

- Do not import AutoGen/CrewAI/LangGraph/OpenAI Agents SDK into Synapse now.
- Do not let external framework prompts/instructions become Synapse behavior.
- Do not create fake swarm animations.
- Do not make normal chat secretly spawn agents.
- Do not bypass existing Tool Runtime, permissions, approvals or egress
  boundaries.
- Do not make the Constellation depend on network availability.

## Product thesis

The differentiator should be:

```text
Synapse does not just answer.
Synapse shows the work structure forming in real time:
who acted, what tool was used, where information came from,
what is waiting, what failed, and what completed.
```

That requires the Constellation and Swarm to be developed together, but in this
order:

1. reliable factual renderer;
2. search/tool activity projection;
3. minimal research swarm;
4. generalized governed swarm runtime.
