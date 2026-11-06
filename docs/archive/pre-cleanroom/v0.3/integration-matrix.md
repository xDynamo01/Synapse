# Synapse 0.3 integration matrix

This matrix traces principal producer -> contract -> consumer paths from the
canonical composition root. It records wiring, not operational success.

## Runtime integration matrix

| Producer | Contract/transport | Final consumer | Evidence | Current gap |
|---|---|---|---|---|
| FastAPI lifespan | `build_application()` / `LifecycleManager` | `RuntimeContainer` and seven lifecycle resources | `main.py`, `bootstrap/application.py` | Packaged startup/recovery not run. |
| Electron renderer | `FrontendClient` over loopback HTTP | `/api/frontend/*` facade | 58 client path literals and registered routers | Only a subset of 568 backend routes is product-visible. |
| Conversation composer | frontend turn/stream/cancel endpoints | `ChatRuntime`, conversation store, model router | frontend boundary and chat wiring | Real model inference not run here. |
| Swarm request | mission/Swarm HTTP contracts | workforce planner, ephemeral agents, workers | mission router, canonical wiring and corrected acceptance | Test contract passes; real two- and four-agent project execution remains operationally unproved. |
| Worker attempt | `WorkerExecutionAdapter` -> `AgentRuntime` | model + governed tool loop | execution/worker adapters | Eight-round inner tool budget is preserved; real provider/tool execution remains unproved. |
| Worker result | verification policy and tool receipts | `WorkerRuntime` / result verifier | progress-sensitive verifier continuation | Replayed receipts cannot grant another outer round; global regression passes. |
| Tool caller | `ToolRouter` / `ToolRuntime` / permission bridge | registered adapter | integration feature builder | Default tool availability is configuration dependent. |
| MCP registry | MCP manifest/tool registry | `MCPToolBridgeRuntime` -> Tool Runtime | bridge sync during composition | No live external MCP server tested. |
| Tool intent | intent approval state | execution router -> tool/MCP/provider target | integration feature builder | Cancellation/restart not operationally replayed. |
| MoM UI | `/api/primary/mom/*` | `MoMRuntime` and primary chat routing | router plus `PrimaryChatRouting` | Loaded-model residency not checked in this mission. |
| Provider settings | provider settings and taxonomy | model, speech and insight consumers | model feature + provider projections | Catalogue entry does not equal provider health. |
| Project knowledge | document/reindex endpoints | SQLite RAG runtime -> memory/context consumers | frontend client and runtime wiring | Learned embeddings are environment gated. |
| Search caller | search port/tool replacement | local SearXNG composition | opt-in adapter | Binding is inert unless explicitly configured. |
| Intelligence assets | egress decision port | models, tools and MCP | explicit egress gate assignments | Desktop upload path is declared unguarded. |
| Voice capture | frontend voice facade | STT -> chat -> context fusion | frontend client and voice router | Returned TTS object is still a placeholder. |
| Audio/vision signals | multimodal session contracts | perception -> context fusion -> agent context | interaction/integration builders | Secondary three-context SCC; real devices untested. |
| Desktop plan | policy/approval + automation plan | OS-specific provider | desktop runtime and tool adapters | Active Windows execution not tested. |
| Scheduler/daemon | job queue and runner identity | agent worker / missions | automation feature builder | Reboot and recurring schedules untested. |
| Governance project | RFC/plan/evidence stores | mission implementation binding | governance feature builder | No 0.3 RFC was promoted by this inventory. |
| Repository/coding session | governed SQLite ports | repository and coding-session compositions | active global bindings | Crash/fencing recovery untested. |
| Sandbox/deployment/private evals | frozen domain ports | global composition adapters | active global bindings | Concrete sandbox driver remains opt-in. |
| Event producers | append-only event bus | operational projection, health and API streams | foundation + projection wiring | Journal corruption/replay not exercised. |

## Frontend control trace

| Visible flow | Frontend boundary | Runtime consumer | Classification |
|---|---|---|---|
| First-agent/bootstrap | `/api/frontend/bootstrap`, `/first-agent` | agent provisioning/admin | `INTEGRATED` |
| Conversation history and turns | `/api/frontend/conversations/*` | conversations + chat | `INTEGRATED` |
| Streaming response/cancel | turn stream/cancel endpoints | chat/model cancellation | `INTEGRATED`, provider not validated |
| File attachment | native picker IPC then attachment staging | conversation attachment store | `INTEGRATED` |
| Swarm create/control/result | `/api/swarms/*` and confirmation facade | missions + Swarm | `TESTED`; operational project run pending |
| MoM mode/resources | `/api/primary/mom/*` | MoM configuration/runtime | `INTEGRATED` |
| Projects/workspace | `/api/projects/*`, project context | governance + project knowledge | `INTEGRATED` |
| Activity constellation | activity snapshot/events/SSE | operational projection | `INTEGRATED` |
| Model settings/import | model/provider endpoints | model hub/provider settings | `INTEGRATED`, live model unvalidated |
| Voice catalogue/settings | voice providers/packs/voices | voice and speech adapters | `INTEGRATED` |
| Voice conversation | frontend voice endpoints | STT -> chat -> placeholder TTS | `INCOMPLETE` |
| Notifications | notification list/read/delete | notification runtime | `INTEGRATED` |
| Personalization | agent read/update | primary-agent/admin runtime | `INTEGRATED` |

## Contract ownership observations

- API routers are delivery adapters and obtain all runtime services from the
  canonical container.
- Feature builders own concrete wiring; domain contexts must not import API,
  commands or bootstrap.
- Ports/contracts are distributed among domain packages rather than held in one
  global interface package. The `contracts` directory is neutral support, not
  the sole contract owner.
- The main SCC means ownership is formally declared but not yet fully reflected
  in acyclic imports. Any extraction must start with a governed-edge decision,
  not a mechanical directory move.
