# Backend Module Status

| Domain | Status | Evidence / gate |
| --- | --- | --- |
| Intelligence Trust Boundary | Implemented / Frozen | canonical assets/classification/trust/purpose/minimization/redaction/manifests/ledger; Model + Tool/MCP gates; 8 acceptance scenarios; global evidence in finalization report |
| Project Governance + RFC Runtime | Implemented / Frozen | canonical Project/RFC/Review/Gate/Plan/Evidence contracts; 8 acceptance and 103 architecture tests green; global gate recorded in finalization report |
| Skills Runtime Phase 1 | Implemented / Frozen | versioned packages, registry/discovery/resolver/loader, assignments/leases, Tool boundary, controlled API/Commands, pilot migration, no new SCC or autoevolution |
| Agent kinds / Primary / ephemeral workforce | Implemented / NOT READY | Exactly three kinds; Primary bootstrap/restart; bounded Mission/Swarm ephemeral lifecycle; Creator removed; final global gate pending |
| Operational storage primitives | Complete pilot / NOT READY | 48-family inventory; 4 migrated pilots; atomic/lock/revision/migration/recovery/pagination/retention primitives; SQLite strategy measured |
| Provider taxonomy | Complete / NOT READY | 1 neutral catalog; 20 real Windows-composition manifests; specialized execution registries preserved; frozen surfaces unchanged |
| Agent Management | Implemented / Frozen | custom provisioning and lifecycle green |
| Delegation | Implemented / Frozen | 105 direct tests green |
| Conversation + Chat | Implemented / Frozen | 97 focused tests green; 0 domain failures globally |
| Memory and Context | Implemented / Frozen | 126 domain tests green; global result in baseline |
| Models and Providers | Implemented / Frozen | 153 focused tests green; global result in baseline |
| Missions, Mission Control, Workers and Recovery | Implemented / Frozen | 148 focused tests green; task mutations, attempts, recovery, DLQ, scheduler, daemon and trace validated |
| Tools and MCP | Implemented / Frozen | 168 integrated tests green; global result in baseline |
| Voice and Speech | Implemented / Frozen | 9 acceptance cases; 93 integrated tests; global 957 passed/26 external failed; no domain mock API/commands |
| Platform Governance, Policy, Observability, Health and Foundation | Implemented / Frozen | 115 transverse tests; 613 frozen-domain tests; OpenAPI unique |
| Client-neutral contracts | Implemented / Frozen | `synapse.contracts` contains DTOs/protocols without runtime imports; obsolete UI projections removed |
| Swarm | Implemented / Frozen | leader-worker, parallel, pipeline and review-loop acceptance paths green |
| Backend Freeze | Complete | final global suite has zero failures; visual state and old App Shell removed |
| Architecture Stabilization Phase 1 | Complete / NOT READY | one root, 9 builders, real lifespan lifecycle, 18 architecture and 990 global tests green; Phase 2 blockers remain |
| API bounded-context decomposition | Complete / NOT READY | 13 routers, one registry, exact 425/471/100 OpenAPI equality; Commands handled by the following phase |
| Command bounded-context decomposition | Complete / NOT READY | 14 handlers, one registry, exact 339 branches/363 names/24 aliases; OpenAPI unchanged; final global evidence in freeze baseline |
| Health contributor inversion | Complete / NOT READY | 10 contributors, one registry, 32 component IDs/82 summary fields preserved; timeout/failure isolation; OpenAPI unchanged |
| Context Fusion read-port inversion | Complete / NOT READY | 6 ports/adapters, concrete domain imports 9→0, Context Fusion SCC 26/79→1/0; frozen surfaces unchanged |
| Perception + Multimodal + Vision | Implemented / Frozen | 6 acceptance cases; 43 focused tests; 974 global passed + 4 subtests; Ruff/OpenAPI unique; no production visual mocks |
| World State + Attention Engine + Agent Loop | Implemented / Frozen | 8 required acceptance cases; 14 focused tests; 988 global passed; Ruff green; 430 OpenAPI paths/480 unique operations; conservative opt-in autonomy |
| Native Email | Removed / Post-removal audited | 279 focused and 927 global tests green; 403 OpenAPI paths/449 operations with zero mail-domain terms; canonical NotificationSink, Delegation/Conversation/Swarm, Tools, Scheduler, resources, attachments, policy and approvals verified |
| Insight + System Runtime | Implemented / Frozen | 153 focused tests; 9 mandatory acceptance scenarios; 938 global tests + 4 subtests green; OpenAPI unique |
| Desktop Automation + Application Control | Implemented / Frozen | 20 mandatory acceptance scenarios; 34 exclusive and 107 focused tests; 972 global tests + 4 subtests green |
| Frontend | Not implemented | old Electron ADE removed; future client owns all presentation state |
| Tool execution boundary | Complete / NOT READY | one public catalog and executor; builtin/MCP/Desktop adapters; direct consumer paths removed; persisted idempotency, timeout, cancellation and verification; frozen public surfaces preserved |
| Administrative DataDir maintenance | Implemented / NOT READY | 4 explicit contributors; durable safe plans; policy/approval/lock/restart controls; 8 canonical API and 8 Command operations; no generic backup/restore |

“Frozen” means the domain contract and focused tests are complete; it does not
mean the entire backend is release-ready.
