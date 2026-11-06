# Synapse 0.3 findings and operational-validation backlog

The findings are evidence-backed inventory results. Mission 0.3.1 made no
runtime correction; Mission 0.3.2 resolved FND-031-001 test-first.

## Findings

| ID | Priority | Finding | Evidence | Required decision/action |
|---|---|---|---|---|
| FND-031-001 | RESOLVED | Swarm verifier continuation repeated without new tool evidence. | Red test observed 8 calls; the progress guard now permits one feedback call per default agent and the corrected acceptance observes 6 total calls, including the preserved inner post-tool calls. Global suite: 4,689 passed. | Resolved in Mission 0.3.2; preserve the eight-round inner tool budget and require new receipt IDs for further outer continuation. |
| FND-031-002 | P1 | Main dependency SCC contains 24 contexts and 80 internal edges. | Architecture support graph over production imports. | Produce governed-edge ownership map and split one reciprocal boundary at a time. |
| FND-031-003 | P1 | Audio, multimodal and perception form a second three-context SCC. | Four internal graph edges. | Define the owning session/signal port before moving imports. |
| FND-031-004 | P1 | Voice conversation response advertises TTS but returns `status: placeholder`. | `api/routers/voice.py` conversation-turn response. | Bind the existing synthesis runtime or remove/rename the claim through an approved API contract change. |
| FND-031-005 | P1 | HTTP surface is much wider than the Electron client surface. | 568 unique registered routes versus 58 client API literals. | Classify routes as product, admin, compatibility or internal; apply auth/exposure policy per class. |
| FND-031-006 | P1 | Bootstrap metadata reports 25 health contributors while the constructed registry contains 19 registrations. | Temporary-data canonical composition. | Define whether metadata counts contributors, feature health objects or global bindings; make the metric unambiguous. |
| FND-031-007 | P2 | Renderer and stylesheet are concentrated in two large files. | `main.tsx` 5,126 lines; `styles.css` 3,540 lines. | Extract only along verified product-flow ownership boundaries after visual baselines exist. |
| FND-031-008 | P2 | Direct-import test discovery reports several contexts only indirectly exercised. | Context-to-test import inventory. | Map acceptance/architecture coverage before labelling any context untested; add direct tests only for real gaps. |
| FND-031-009 | P2 | Search and concrete sandbox driver are implemented but intentionally inert. | Global binding inventory. | Keep optional unless a 0.3 RFC authorizes activation and operational dependencies. |
| FND-031-010 | P2 | Provider taxonomy is broader than executable/healthy providers. | 25 taxonomy entries versus 8 provider manifests in temporary composition. | UI and readiness must distinguish discoverable, configured, installed, loaded and healthy. |

## Root-cause record for FND-031-001

The failure is not caused by the numeric value eight being exhausted. The
observed sequence is:

1. two default ephemeral analysis agents are created;
2. each emits `list_directory` and receives the receipt;
3. because the execution adapter permits inner tool continuation, each model is
   called again and returns premature text;
4. the outer worker verifier rejects the missing `read_file` evidence;
5. two outer feedback rounds call each agent once more before failure.

This yields four model calls per agent and eight globally. The test's expected
four corresponds to one initial call plus one feedback call per agent, which is
compatible with a one-round inner adapter. Both the eight-round implementation
and four-call test entered the preserved snapshot together, so Git history did
not identify the intended contract. Mission 0.3.2 retained the inner budget and
made outer verifier continuation progress-sensitive. The resulting two-agent
sequence is six calls: initial, post-tool and one feedback call per agent.

The first corrected global run then exposed a separate concurrency race: two
workers could both observe the same deterministic tool-input asset as missing
and attempt registration. The Intelligence Boundary now owns idempotent
`ensure_asset()` semantics; a deterministic concurrent test proves both tool
executions reuse one asset.

## Mission 0.3.2 operational backlog

| Order | Validation slice | Success evidence |
|---|---|---|
| 1 | Resolve FND-031-001 | **COMPLETE:** red/green acceptance and concurrency tests, 274 architecture tests and 4,689-test global regression pass. |
| 2 | Canonical startup/shutdown | Disposable-data lifecycle report; all required resources start and close without leaked processes. |
| 3 | Packaged Electron boot | Current root executable launches the current sidecar, renderer reaches bootstrap and versions/hashes match. |
| 4 | Real chat inference | Configured local model produces a streamed response with provider/model receipt. |
| 5 | Real two- and four-agent Swarm | Exact Portuguese project request completes with file read/edit/readback receipts and approval continuation. |
| 6 | Persistence/recovery | Restart, corruption and rollback matrix for every active global SQLite binding. |
| 7 | Voice loop | Female ready voice completes microphone/STT/chat/TTS/playback without placeholder state. |
| 8 | Desktop automation | One reversible Windows operation proves plan, approval, execution and independent verification. |
| 9 | Tool/MCP | Every advertised executable tool has permission, receipt, cancellation and failure evidence. |
| 10 | Route exposure | All 568 routes classified; unauthorized/internal routes are not unintentionally exposed. |
| 11 | Resource pressure | One-model residency and RAM/VRAM/disk behavior measured under chat, Swarm and voice. |
| 12 | Reboot recovery | Startup, scheduled work, persisted state and active artifact verified after Windows reboot. |

## Stop conditions

- Do not declare backend readiness from FND-031-001 closure or a green global
  suite alone; the operational slices below remain required.
- Do not refactor either SCC without a governed-edge decision and architecture
  test for the desired direction.
- Do not activate optional search/sandbox production wiring as a side effect of
  validation.
- Do not treat mocks, temporary composition or route registration as operational
  proof.
