# Intelligence Trust Boundary flow inventory

Date: **2026-07-15**

This inventory was completed before implementation. It is the before-state
authority for content crossings and does not claim protection where the
runtime cannot observe a transport.

| Source | Data type | Owner | Current classification | Consumer | Destination | Local/external | Provider | Transformation | Redaction | Approval | Audit | Risk | Finding |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ModelRouter | prompt, history, memory, tasks, tools | user/project | none | model adapter | configured endpoint | ambiguous | selected model provider | prompt rendering and character truncation | none | none | provider/model/timing only | critical | Free prompt and assembled context reach adapters without classification or egress policy. |
| OpenAICompatibleAdapter | rendered chat messages and tool schemas | user/project | none | HTTP API | `/chat/completions` | external unless explicitly profiled | OpenAI-compatible | JSON encoding, optional stream | none | none | errors omit payload | critical | Direct network call; localhost is not sufficient evidence of locality. |
| OllamaModelAdapter | rendered chat messages | user/project | none | Ollama API | `/api/chat` | local network by intended configuration | Ollama | JSON encoding | none | none | errors omit payload | medium | Real network boundary; locality was inferred from deployment convention. |
| LMStudioProviderRuntime | chat messages | user/project | none | LM Studio API | `/chat/completions` | local network by declared product role | LM Studio | token profiling and retry reduction | none | none | counts/timing only | medium | Retry minimizes by size, not classification; endpoint locality needs an explicit profile. |
| model fallback | same model request | user/project | none | alternate adapter | alternate endpoint | may change local to external | configured fallback | route substitution | none | none | fallback event | critical | No new content decision when provider/boundary changes. |
| provider settings test | API key header and health request | user/organization | credential metadata | URL probe | configured endpoint | ambiguous | provider under test | GET request | key excluded from event | admin policy | status event | high | Network probe is not a content request but requires explicit destination trust. |
| MCPRuntime callback | tool arguments and result | user/project | none | registered executor | executor-defined | potentially external | MCP server | dict copy | none | Tool approval | connection/tool events | critical | Transport is callback-defined and externality was not enforced. |
| MCPToolBridge | tool arguments/results | user/project | none | ToolRuntime/MCPRuntime | MCP executor | potentially external | MCP server | schema validation | none | required by tool | Tool execution records | high | Existing Tool Boundary is authoritative but had no egress manifest. |
| generic ToolRuntime adapters | arbitrary arguments/results | mixed | none | registered handler | handler-defined | potentially external | tool provider | schema/permission processing | none | risk-based | execution metadata; some results persisted | critical | External adapters can be registered; no canonical external-boundary declaration or gate. |
| builtin tools | scoped arguments/results | user/system | none | local handler | local process/files | local | internal | schema validation | none | permission/risk policy | execution metadata | low | No network egress; minimization metadata absent. |
| Skill packages/scripts | package metadata and future script input | project | manifest fields only | Tool Boundary | handler-defined | potentially external | declared providers | package resolution | none | Tool policy | resolution events | high | Phase 1 does not execute arbitrary scripts directly; future external calls must remain behind Tool/Egress gates. |
| Context Fusion | memory, tasks, conversation, project context | mixed | sensitivity hint only | Primary/model context | in-process then model | local then provider-dependent | none | ranking and budget | none | none | source references | high | Context preserves sources but not canonical classification/ownership assets. |
| Memory retrieval | user/project memory | user/project | none | Context Fusion/model prompt | in-process then provider-dependent | local then provider-dependent | none | search and section rendering | truncation only | none | metadata | high | Historical records have no trust metadata and are copied into prompts. |
| Mission context/results | task context and outputs | project/mission | governance binding only | worker/model/swarm | provider-dependent | mixed | selected model/tool | orchestration/consolidation | none | mission/tool policy | mission events | high | RFC binding exists; egress constraints were not represented. |
| Project Governance | RFC, ADR, plans, evidence, criteria | project | project-owned | Context/Skills/Missions | in-process; may enter prompts/tools | mixed | none | budgeted summaries | secret-key redaction | RFC approvals only | governance evidence | high | Governance classification fields are preparatory; no egress enforcement existed. |
| Voice/Speech | raw audio, transcript, synthesis text/audio | user/project | none | local adapters | local process/model | local today | Faster Whisper/Piper/mock | decode/transcribe/synthesize | none | device/tool policy | metadata events | medium | No external speech provider is active; future external adapters need a gate. |
| Vision | screenshots/images/OCR/results | user/project | none | local providers | local filesystem/process | local today | local metadata/OCR placeholders | capture/analysis | no real media redaction | capture policy | safe metadata events | high | Raw media remains local today; unsupported media redaction must fail closed for future external providers. |
| Desktop Automation | screen, clipboard, keystrokes, UI form data | user/project | none | OS/UI provider | user applications | local with possible remote UI effects | OS provider | UI actions | none | desktop risk/approval | action metadata | critical | Upload/form submission through arbitrary UI cannot be comprehensively intercepted in this phase. |
| notifications | notification title/body/metadata | user/system | none | local/console provider | local storage/console | local today | local | serialization | none | notification policy | full notification event | medium | Providers are local, but event payload can contain user-authored body. |
| exports/imports | files, memory, traces, project artifacts | mixed | none | filesystem/admin surfaces | user-selected storage | local/export boundary | internal | serialization | none | operation-specific | scattered | high | No canonical export manifest or import provenance registry. |
| observability | events, errors, traces | mixed | implicit safe subsets | EventBus/stores | local logs/storage | local | internal | dataclass serialization | central redaction in selected paths | none | canonical event bus | high | Several domains emit whole dataclasses; payload-content prohibition is not universal. |
| provider outputs | model/tool/media output | provider-derived/project | none | agents/memory/tools | local persistence or next provider call | mixed | model/tool provider | parsing | none | inherited request only | timing/status | high | Derived provenance and restrictive classification inheritance were absent. |
| future datasets/evals | references only | project | preparatory fields | future runtime | not implemented | none | none | none | none | none | RFC metadata | medium | Private Evals/training are explicitly out of scope; training-use constraints need a preparatory contract only. |

## Before metrics and conclusions

- Real HTTP content paths: OpenAI-compatible, Ollama and LM Studio chat.
- Additional network path: provider settings probe; it does not send user
  content but can send an API credential header.
- Executable external abstraction: MCP callback through Tool Runtime.
- Active external Speech/Vision providers: zero.
- Canonical InformationAssets, EgressDecisions, manifests and ledger records:
  zero.
- Protected paths with a canonical EgressGate: zero.
- Known unguarded content-capable path families: model adapters, generic
  external tools/MCP, and UI-mediated Desktop Automation uploads.

The implementation must protect model and declared external Tool/MCP paths.
Speech and Vision receive contracts/guardrails for future external adapters,
while their current local behavior remains unchanged. UI-mediated network
effects and third-party post-receipt behavior remain explicit limitations.
