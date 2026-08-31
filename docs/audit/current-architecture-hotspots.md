# Current architecture hotspots

Audit date: **2026-07-15**

Worktree: `backend-freeze-cleanup` at `8196eb11c34442af563b20082bc1666755f4d8a9` (dirty)

## Measured hotspots

Centrality is `unique incoming contexts + unique outgoing contexts` in the
governed graph. It is structural degree, not runtime traffic or business
importance. Concrete imports are cross-context import-symbol occurrences not
classified as contract/port/provider/sink/source/reader imports.

| Context | In | Out | Centrality | Reciprocal contexts | Concrete import occurrences | Interpretation |
| --- | ---: | ---: | ---: | --- | ---: | --- |
| core | 61 | 1 | 62 | none | 3 | Expected foundation fan-in; not cyclic after compatibility exclusions |
| tools | 13 | 16 | 29 | agents, approvals, decisions, missions, policies | 42 | Primary SCC-01 runtime/governance hotspot |
| observability | 28 | 0 | 28 | none | 0 | Healthy sink-like fan-in |
| agents | 16 | 11 | 27 | context, models, policies, tools | 56 | Shared identity plus concrete runtime hotspot |
| policies | 9 | 6 | 15 | agents, approvals, tools | 14 | Policy orchestration imports authorities in both directions |
| api | 0 | 13 | 13 | none | 47 | Delivery fan-out; no reverse domain dependency |
| decisions | 4 | 8 | 12 | tools | 12 | Governance bridge participates in SCC-01 |
| scheduler | 1 | 11 | 12 | none | 26 | Operational coordinator, not cyclic |
| workers | 1 | 11 | 12 | none | 42 | Broad coordinator, not cyclic |
| audio | 6 | 4 | 10 | speech_adapters | 10 | One concrete runtime import sustains SCC-03 |
| delegation | 4 | 6 | 10 | none | 30 | Broad but currently one-way |
| providers | 8 | 2 | 10 | none | 12 | Taxonomy fan-in without SCC membership |
| approvals | 3 | 6 | 9 | policies, tools | 18 | Mutating authority embedded in reciprocal orchestration |

`core` and `observability` are high-degree by design and are not hotspots merely
because they are central. `tools`, `agents`, and `policies` are hotspots because
degree combines with multiple reciprocal concrete dependencies. File size was
not used.

## File evidence

Highest cross-context import occurrence counts:

| File | Occurrences |
| --- | ---: |
| `workers/agent_worker.py` | 19 |
| `voice/runtime.py` | 18 |
| `chat/runtime.py` | 17 |
| `scheduler/runtime.py` | 17 |
| `tools/runtime.py` | 16 |
| `agent_loop/runtime.py` | 15 |
| `policies/effective.py` | 14 |
| `agents/admin.py` | 13 |
| `approvals/manager.py` | 13 |
| `commands/handlers/platform_governance.py` | 13 |
| `speech_pipeline/runtime.py` | 13 |
| `decisions/runtime.py` | 12 |

Highest imports whose endpoints are members of the same SCC:

| File | Cycle-related occurrences |
| --- | ---: |
| `voice/runtime.py` | 8 |
| `agents/runtime.py` | 7 |
| `decisions/runtime.py` | 6 |
| `policies/effective.py` | 6 |
| `tools/runtime.py` | 5 |
| `approvals/resume.py` | 4 |
| `speech_adapters/faster_whisper.py` | 4 |
| `speech_adapters/interfaces.py` | 4 |
| `speech_adapters/local_analysis.py` | 4 |
| `speech_adapters/runtime.py` | 4 |
| `tools/permission_bridge.py` | 4 |

The notable patterns are concrete runtimes used in both directions, consumer
DTOs owned by suppliers (`ModelRouter -> AgentConfig`), a composition adapter
inside `world_state/sources.py`, and a concrete provider runtime imported by
its consumer (`AudioRuntime -> SpeechAdapterRuntime`). `contracts/__init__.py`
re-exports many symbols, but it is not in an SCC and is not treated as a cycle
hotspot.

## Ports and protocols

The AST inventory contains 49 Protocol classes. The complete record for every
protocol—including owner, location, methods, runtime/type-only consumers,
structural implementer candidates, bootstrap-wired candidates, mutation verbs,
direction and use assessment—is embedded in
`current-dependency-graph.json` under `ports_and_protocols`.

| Family / port | Owner | Consumer(s) | Implementer / adapter | Direction and assessment |
| --- | --- | --- | --- | --- |
| Six `*ContextReader` ports | context_fusion | ContextFusionRuntime | six `bootstrap/adapters/context_fusion.py` projections | Read-only, consumer-owned, bootstrap-wired; demonstrably reduced Context Fusion to singleton |
| `HealthContributor` | health | Health registry/runtime | ten bounded contributors plus Primary/Ephemeral contributions | Read-only collection, bootstrap registered; reduced Health coupling |
| `HealthSnapshotSource` | health | readiness, tools; missions type-only | HealthRuntime (plus structural candidates) | Read-only; cross-context use is effective |
| `ToolExecutionPort` | tools | execution_router, mcp_bridge, tool_discovery, tool_intents; agent_loop/missions type-only | ToolRuntime, wired in bootstrap | Used and cycle-reducing, but 13 methods include registration, execution, query, cancel, retry, rollback and verification; larger than a minimal consumer port |
| `MaintenanceContributor` | maintenance | maintenance registry/runtime | four owner contributors, bootstrap wired | Contains inspect plus plan/execute mutation; intentionally administrative but broad |
| `NotificationSink` | agent_loop | Agent Loop | LocalNotificationSink in bootstrap | One-method event notification; appropriately narrow |
| `VoicePerceptionSink` | voice | voice/bootstrap | Null sink or PerceptionRuntime projection | One-method notification; appropriately narrow |
| `MemoryStorage` | memory | MemoryStore | FileMemoryStorage | Local persistence seam; used |
| `AudioDeviceBackend` | audio | DeviceRuntime | SoundDeviceBackend | Local provider seam; used inside owner context |
| Speech adapter protocols | speech_adapters | adapter runtime/factories | FasterWhisper, Piper, LocalAnalysis and mock adapters | Supplier-owned execution adapters; they consume audio DTOs and do not solve AudioRuntime's reverse concrete import |
| Vision provider protocols | vision | VisionRuntime | MSS/local/null providers | Domain-local provider seams; no cross-context cycle |
| Desktop provider protocols | desktop_automation | DesktopRuntime | Windows/Linux/macOS/fallback providers | Domain-local provider seams; concrete construction remains in authorized composition/factory paths |
| `BaseModelAdapter` | models | ModelRouter | LM Studio, Ollama, OpenAI-compatible, mock | Used; supplier-local provider abstraction |
| Generic `contracts.*` protocols | contracts | mostly re-export/local; `MemoryStore` and `MissionRuntime` have real external imports | structural implementation not always provable by method-name matching | Potentially duplicated with domain-specific contracts; mutation-heavy (`read/write/append/emit`, `create/get/state/emit`) and not uniformly bootstrap-adapted |
| `PlanProvider` | missions | local planner annotation | supplied object, not imported cross-context | Local protocol; zero import references is not orphan proof |
| `FrameClassifier` | voice | local VAD runtime | injected classifier | Local protocol; zero import references is not orphan proof |
| `ProviderFactory` | providers | ProviderRuntime/catalog | registered factories | Used locally; creation mutation is expected |
| lifecycle `Startable`/`Closable` | bootstrap | LifecycleManager/Application | lifecycle resources | Composition-local protocols; appropriate |

### Findings

- **No proven orphan adapter:** absence of a bootstrap import is insufficient
  because several providers are built by domain registries/factories. The audit
  therefore does not label structurally detected but unwired candidates orphan.
- **Possible orphan/duplicate contracts:** generic protocols under
  `synapse.contracts` often have only package-local/re-export evidence and
  overlap newer domain-owned ports. They require call-site migration evidence
  before deletion; no deletion is recommended here.
- **Oversized port:** `ToolExecutionPort` has 13 methods and permits mutations
  unrelated to many read-only consumers. It successfully centralizes execution,
  but future consumers should receive smaller views rather than the full port.
- **Unnecessary mutation exposure:** `contracts.MemoryStore`,
  `contracts.MissionRuntime`, `MaintenanceContributor`, and `ToolExecutionPort`
  expose mutation. Only the latter two have explicit current composition
  evidence; read-only consumers should not receive the full surfaces.
- **Existing port not yet used everywhere:** Agent and approval compatibility
  paths still import `ToolRouter`; Missions imports tool models while Tools
  imports a concrete MissionRuntime. Existing Tool/Mission contracts could
  remove some of those edges without inventing a general interface layer.
- **No port yet fits SCC-03:** speech adapter protocols are owned by the supplier
  and AudioRuntime imports the concrete supplier runtime. The missing seam is a
  two-method audio-owned execution view.

Structural implementer matching is intentionally labeled as a candidate in the
JSON. One-method protocols have many accidental shape matches; those are not
treated as confirmed implementations without bootstrap or direct construction
evidence.

## Event candidates

| Dependency | Event suitability | Reason |
| --- | --- | --- |
| frozen-domain events → world-state projection | Appropriate and already used | notification/projection; no synchronous answer required |
| world-state snapshot → attention | Inappropriate | policy decision requires current synchronous state |
| audio → speech adapter | Inappropriate | transcription/synthesis must return a result or error |
| agent/model generation | Inappropriate | caller requires generated result and cancellation semantics |
| policy/approval/tool minimum cycles | Inappropriate | policy decisions, validation and commands require results/transactional ordering |
| health/observability notifications | Appropriate | snapshot contribution and telemetry are read/notification flows, already bounded |

## Candidate ranking

| Candidate | Priority | Benefit | Risk / why not selected now | Suggested order |
| --- | --- | --- | --- | ---: |
| Audio → SpeechAdapterRuntime | P1 | Removes SCC-03 entirely by changing one cross-context edge | Low risk; synchronous contract is only two methods | **1 — selected** |
| Attention ↔ World State | P2 | Removes SCC-02 entirely | Requires relocating/composing an event projection adapter and preserving event registration; still small | 2 |
| Missions ↔ Tools | P1 within SCC-01 | Uses existing boundaries and may reduce global SCC | Does not necessarily split SCC-01 alone because Tools has eight other direct reciprocal pairs | 3 |
| Agents ↔ Models | P1 within SCC-01 | Corrects DTO ownership with a narrow model selection input | Frozen generation contracts and multiple AgentRuntime consumers raise equivalence risk | 4 |
| Tools/Policies/Approvals cluster | P1 within SCC-01 | Attacks the densest reciprocal governance knot | Three-context inseparable orchestration, mutation and approval semantics make it larger than the selected phase | 5 |

The selected target maximizes measurable SCC reduction per changed dependency.
It does not imply that SCC-01 is less important; SCC-01 is the dominant release
blocker, but its smallest pairs need a more careful sequence to guarantee a
component split.

## Limitations

Static imports do not reveal runtime call frequency, dynamic provider loading,
or transaction boundaries. Centrality is unweighted. Protocol implementation
is structural in Python and can be implicit. Historical metrics are compared
only where methodology is compatible. No code, guardrail or cycle was changed
by this audit.
