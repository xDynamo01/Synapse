# Foundation threat model — Gate 00

## Scope and status

Date: 2026-11-09. Source baseline: `009fe94f71b711af3a4cb688d9da6b8cbdfae538`.
This model consumes the approved architecture, the binding
`docs/specs/2026-11-06-synapse-0.3-decision-charter.md` and ADRs 0001–0003.
It covers the foundation and specifies obligations for Plan 01 and later
missions, tools, browser, Skills, models and remote-access plans. It is a
source-backed architecture model, not a vulnerability audit or runtime proof.
The nine threat scenarios below are hypotheses, not confirmed vulnerabilities.

**CURRENT** means a developer-run diagnostic or disposable experiment in this
revision. **REQUIRED** means approved product behavior awaiting implementation
and negative/real-composition evidence. **CONDITIONAL** means a future sensitive
boundary that cannot ship on this model alone. The tree has documentation,
diagnostics and experiments; it has no packaged Electron product, authoritative
mission runtime, production credential store or deployed remote service.
The existing fixed public fixture bearer is never a production identity.
See `experiments/transport/server/lifecycle.py:1-17` and
`docs/adr/0002-client-core-transport.md:58-80`.

The target is a personal local-first A.R.T.E.M.I.S. Assistant and universal
Workspace/CLI sharing a headless modular Core and independent clients. Core
owns authoritative state, mission policy and execution. Initial operation is
co-located, with future remote clients separately gated. ADR 0001 selects
standard-GIL CPython 3.14.10 and pinned Node 24/pnpm 11 tooling, ADR 0002 selects
versioned gRPC/Protobuf, and ADR 0003 selects Core-owned local SQLite WAL/FULL.
These choices do not qualify Electron packaging, personal-data protection or
physical Linux/macOS operation. Sources: `docs/adr/0001-core-runtime-and-toolchain.md:18-27`,
`docs/adr/0002-client-core-transport.md:10-26`,
`docs/adr/0003-foundation-persistence.md:8-25`,
`docs/specs/2026-11-06-synapse-0.3-clean-room-design.md:117-143`.

## Assets

- Human owner authority, interactive presence, client/Device Bridge identity,
  exact contract revisions, approvals, grants, revocations and recovery policy.
- Workspace artifacts; logically partitioned canonical memory, chats, retrieval
  sources and mission evidence; command/causation IDs, cursors and tool/QA receipts.
- Credentials, encryption keys, protected browser sessions, voice buffers and
  transcripts; local SQLite DB/WAL/SHM, immutable referenced blobs, snapshot,
  staging, export and recovery sets.
- Skill provenance/version lineage, pinned source/dependencies/generators,
  validated artifact identity, release signing authority and rollback points.
- Availability: bounded CPU/RAM/VRAM/time, temporary agent and subprocess
  lifetimes, model reservations, streaming backpressure and storage retention.
- Current experimental assets are synthetic journals and records, package/hash
  provenance and sanitized aggregate host/timing evidence under the operator's
  OS account. They are distinct from future protected production assets.

Sources: `docs/specs/2026-11-06-synapse-0.3-clean-room-design.md:288-298`,
`docs/specs/2026-11-06-synapse-0.3-clean-room-design.md:314-382`,
`docs/specs/2026-11-06-synapse-0.3-clean-room-design.md:384-474`,
`docs/specs/2026-11-06-synapse-0.3-clean-room-design.md:476-531`.

## Trust boundaries

Each row names the actual consumer, effective resource or unresolved location,
recipient and enforcing component. An invoking OS user's existing permissions
are not a new application security boundary. Git ignore is not confinement.

| ID / state | Flow, effective resource and recipients | Enforcing control and limitation / source |
|---|---|---|
| B-01 CURRENT | Operator → OS/CIM aggregate host inventory → caller-selected `-OutputPath`; direct invocation or dot-sourced function; current OS user reads/writes. | Collector requires FileSystem provider and emits fixed/aggregate fields, not a workspace root or no-overwrite rule. Separate checker is not automatically applied to every output. `tools/foundation/collect-host-capabilities.ps1:8-17`, `tools/foundation/collect-host-capabilities.ps1:69-98`, `tools/foundation/collect-host-capabilities.ps1:130-146`. |
| B-02 CURRENT | Developer → local bootstrap PATH and `.local` Python/cache or fresh provisioned PATH → isolated `.venv-313` / `.venv-314`, generated declarations/compiled JS; developer/child processes share OS account. | Exact pins/frozen locks, no Python source builds or package install scripts preserve fixture provenance. Audit hooks are fixture hygiene; none proves product containment. Measurement spawns selected Python/Node and writes caller `--output`. `experiments/runtime-compatibility/README.md:28-108`, `experiments/runtime-compatibility/tools/measure-runtime.py:14-28`, `experiments/runtime-compatibility/tools/measure-runtime.py:41-86`. |
| B-03 CURRENT | Test parent → transport child: Python uses `sys.executable` plus source-relative server; Node uses `.venv/Scripts/python.exe` on Windows or `.venv/bin/python`, working-directory-relative server. Private stdout publishes numeric host/port/PIDs, stdin requests exit. | Harness checks child ownership; Windows launcher and actual runtime can differ; kill/reap must cover actual owned process. No credential discovery endpoint or OS sandbox. `experiments/transport/tests/process_harness.py:20-55`, `experiments/transport/tests/server-harness.ts:25-97`, `experiments/transport/server/main.py:14-35`. |
| B-04 CURRENT | Local gRPC caller → generated Protobuf parser → metadata check → shared Lifecycle. Numeric `127.0.0.1:0`, kernel port; plaintext fixture connection. | 4 KiB send/receive ceilings, one auth metadata value, bounded stream opening; Lifecycle checks synthetic bearer/contract. No production per-client issuance. `experiments/transport/server/grpc_server.py:17-58`, `experiments/transport/server/lifecycle.py:47-56`. |
| B-05 CURRENT | Alternative HTTP POST / WebSocket → JSON → same Lifecycle; numeric `127.0.0.1:0`. HTTP checks auth before JSON; WS upgrade and bounded first frame precede event auth. | 4 KiB body/message ceiling, opening deadline, access log disabled; WS event delivery checks shared auth. Different parser boundaries remain distinct. ADR 0002 retains this only as comparison. `experiments/transport/server/http_server.py:8-68`, `experiments/transport/server/lifecycle.py:109-120`, `docs/adr/0002-client-core-transport.md:82-87`. |
| B-06 CURRENT | Lifecycle → exact caller `--journal` → plaintext SQLite/WAL/FULL synthetic commands/events. Relative paths resolve under invoking cwd; no enforced `.local` root. | One public fixture principal, only effect-free hold; atomic command/ACK, immutable duplicate matching, single cancellation, 128-command cap, ascending cursor, one-event ACK/500 ms. This is not owner authorization or tamper protection. `experiments/transport/server/main.py:14-24`, `experiments/transport/server/lifecycle.py:26-39`, `experiments/transport/server/lifecycle.py:63-154`. |
| B-07 CURRENT | Separate in-process persistence adapter → caller absolute DB plus `-wal/-shm/-journal`; tests use scratch `source/records.sqlite`, `snapshot.sqlite`, `restored/records.sqlite`. | Schema/application/version checks and immutable parameterized transactions; same OS account, plaintext files. Backup stages `<destination-parent>/.snapshot-*/staged.sqlite`, normalizes/checks and hard-links without clobber. Restore validates standalone snapshot and publishes fresh WAL DB; tests reopen/read content. No application ACL, authenticated snapshot provenance, encryption or stopped-Core switch is implemented. `experiments/persistence/storage.py:11-145`, `experiments/persistence/tests/test_backup_restore.py:11-57`. |
| B-08 REQUIRED | Untrusted renderer → named preload IPC → Electron main → Core. Main alone owns endpoint/discovery and client credentials. | Packaged main must check sender/frame/method/payload/subscription ownership; isolate/sandbox renderer, disable Node, bound network/navigation and revoke subscriptions on destruction/navigation. Node process-type check is only a fixture guard. `docs/adr/0002-client-core-transport.md:58-70`, `experiments/transport/client/main-process-client.ts:24-35`. |
| B-09 REQUIRED | Main / CLI / distinct Device Bridge identity → initial local Core gRPC listener; no production address, discovery path, OS identity or credential path selected yet. | Numeric loopback initial bind, Core client authentication/scopes/ownership and revocation; an authenticated client is not an authenticated human approval. Resolve Q1 before integration. `docs/adr/0002-client-core-transport.md:74-80`, `docs/specs/2026-11-06-synapse-0.3-clean-room-design.md:504-515`. |
| B-10 REQUIRED | Owner → trusted presence check → immutable mission revision → effect consumer; authority administration includes pairing, credential export and recovery-policy change. | Core enforces exact scope/target/account/destination/effect/budget and current revocation at effect time; routine paired approval requires presence, administration trusted local confirmation. Concrete issuance/approval/replay storage unresolved. `docs/specs/2026-11-06-synapse-0.3-clean-room-design.md:306-347`. |
| B-11 REQUIRED | Core → Tool Broker → file/network/device/child process; staged artifact → independent QA → automatic integration → post-integration regression/rollback. | Separate capabilities and authoritative receipts, OS process containment; no ambient shell authority. Exact QA artifact and declared publication effect. Actual OS roots, executable policy and grant runtime unresolved. `docs/specs/2026-11-06-synapse-0.3-clean-room-design.md:194-212`, `docs/specs/2026-11-06-synapse-0.3-clean-room-design.md:349-382`. |
| B-12 REQUIRED | Context → model; Skill code/version/dependencies → broker; temporary Swarm → bounded projection/grants/reservations. | Retrieval cannot promote context. Local models/Planner/Scheduler/Lifecycle never grant authority. Skill installation is audited/quarantined inside approved scope; freeze in-mission version and require QA/rollback for promotion. Swarm requires owner acceptance, cannot write canonical memory, and must revoke/clean up. `docs/specs/2026-11-06-synapse-0.3-clean-room-design.md:288-298`, `docs/specs/2026-11-06-synapse-0.3-clean-room-design.md:384-474`. |
| B-13 CONDITIONAL | Browser profiles per Workspace/mission, sessions, clipboard/local files, downloads, network and credentials; concrete locations/allowlists/registry not implemented. | Protected manual browsing differs from brokered agent operations. Encrypted session/secure store and opaque handles, destination/budget and SSRF/local-network control; typed/hashed/scanned quarantine and no auto-execution. `docs/specs/2026-11-06-synapse-0.3-clean-room-design.md:476-518`. |
| B-14 CONDITIONAL | Device Bridge / wake detector → ephemeral microphone buffer → activated STT/transcript; no actual audio boundary implemented here. | Minimum pre-wake buffer is discarded and never sent to STT/models/memory/network. No raw-audio persistence by default; transcript uses chat policy. `docs/specs/2026-11-06-synapse-0.3-decision-charter.md:108-114`, `docs/specs/2026-11-06-synapse-0.3-decision-charter.md:142-145`. |
| B-15 CONDITIONAL | Core-owned DB/WAL/SHM, blobs, staging, snapshot/export set and platform secure store → authorized stopped-Core restore. Effective product roots/ACLs/keys/destinations unresolved. | Keys separate from data and backup; at-rest protection covers active/staged/exported sets. Verify authorization, snapshot manifest/references/content, preserve original, stop on corruption and switch only after readback. Structural SQLite validity does not establish provenance. `docs/adr/0003-foundation-persistence.md:28-81`. |
| B-16 CONDITIONAL | Explicit future personal-server listener → paired desktop/mobile devices; bind/discovery/certificate/key/pairing protocol not selected. | Remote disabled by default. Separate formal model must prove encrypted authentication, device scope and revocation, with trusted local pairing confirmation. No remote exposure follows from fixture loopback. `docs/adr/0002-client-core-transport.md:89-104`, `docs/specs/2026-11-06-synapse-0.3-clean-room-design.md:135-143`, `docs/specs/2026-11-06-synapse-0.3-clean-room-design.md:332-341`. |
| B-17 CONDITIONAL | Audited historical-data import; exact staged payload → approved publication/update/signing destination and recovery policy. | Clean-room forbids old runtime/config/state reuse. Separate mission/tool for data import; provenance, exact artifact QA and platform release validation precede distribution. No release identity/update pipeline exists here. `docs/specs/2026-11-06-synapse-0.3-decision-charter.md:42-66`, `docs/specs/2026-11-06-synapse-0.3-clean-room-design.md:343-382`, `docs/specs/2026-11-06-synapse-0.3-clean-room-design.md:520-563`. |

## Entry points

Current entry points are operator-run host collector and package/generator/
measurement commands, transport `--candidate/--journal` server startup, numeric
loopback gRPC and comparison HTTP/WS calls, and in-process persistence methods
on caller-owned paths. Their effective resources and auth/parser differences
are B-01–B-07. Product entry points will be named preload calls, authenticated
CLI/Device Bridge/Core contracts, trusted owner-presence actions and brokered
tool/model inputs (B-08–B-12). Browser/downloads, credentials, audio, restore,
remote pairing, import and release remain conditional (B-13–B-17).

## Attacker capabilities

Current local callers can reach an operator-started loopback fixture and know
its public test bearer. They can affect only the synthetic journal through
its lifecycle calls; they gain no shell, model, browser or human authority.
The developer already chooses input/output paths and dependency provisioning
under their OS account. Modifying PATH/packages/parent directories or DB files
requires separate existing access; no Internet reachability, administrator
compromise, multi-tenancy or signing-key access is assumed.

Conditional attackers control renderer scripts, forged client requests, replayed
inputs, hostile web/retrieval/model text, or poisoned Skill/project code within
an invocation. They start without trusted owner presence, Core secrets, broader
file/network grants or cross-project context. Backup tampering/file theft and
stolen paired devices require those explicit prerequisites. The impact sought
is a new capability: unauthorized effect/egress, owner impersonation, context
leakage, counterfeit evidence or resource exhaustion. Source boundaries are
B-04–B-17; malicious content alone does not prove a broker or OS escape.

## Threats and mitigations

Every row is a **conditional design hypothesis**, with counterevidence from the
current fixture stated where relevant. Priorities describe required design
attention, not vulnerability severity. Invariant IDs refer to
[authority-invariants.md](authority-invariants.md).

| ID | Attacker / prerequisite and entry | Boundary / path and new impact | Required mitigation / invariant | Current counterevidence or gap | Verification owner | Negative / acceptance evidence |
|---|---|---|---|---|---|---|
| T-01 | Compromised renderer script in a packaged client | B-08 → raw IPC/token/Core request → unauthorized tool or stream access | Narrow preload; sender/frame/method/payload/stream binding; sandbox/Node off/navigation limits; Core recheck AI-01/04/10 | No packaged Electron here; Node process-type guard is insufficient product evidence | Plan 01 client/Core | Forged sender/frame, navigation and destroyed-consumer requests denied; renderer cannot discover credential/raw transport; packaged allowed route works |
| T-02 | Untrusted local process, no valid product credential | B-09 → forged client or discovery replacement → scoped data/action impersonation | Core-issued scoped identity, protected discovery/credentials, rotation/revocation; numeric loopback AI-04/05/10 | Public fixture token is synthetic and hold is effect-free; loopback alone is not identity | Plan 01 Core/auth | Unknown/duplicate auth, wrong client/scope, stale/rotated credential and unauthorized stream denied at Core; inspect actual listener |
| T-03 | Model/retrieved text controls proposed action, no owner authority | B-12 → planner/tool request → privilege/target/context expansion or egress | Treat output as data; bind exact contract/context; deny by default AI-01/02/06/10 | No model/tool runtime exists; prompting cannot enforce policy | Model routing + mission + memory | Injected tool/approval request, unrelated project lookup and undisclosed cloud inference denied; permitted local inference remains usable |
| T-04 | Poisoned Skill or dependency after mission-scoped discovery | B-12 → install/execute/evolve/promote → code or cross-context authority | Audit origin/license/scripts/deps, quarantine; freeze version; broker grants; independent QA/lineage/rollback AI-02/06/10 | No executable Skill installation/evolution path; pinning fixture dependencies does not prove isolation | Skills + QA + Tool Broker | Permission/dependency expansion and in-flight version swap denied; project private content blocked from global descendant; regression rolls back |
| T-05 | Hostile page/document/download inside future browser | B-13 → clipboard/file/credential/local-network or form destination → exfiltration/execution | Protect profiles; broker destination/effect; SSRF restrictions, quarantine/type/hash/scan, no auto-execution AI-02/06/10 | Browser/egress rules not implemented; manual browsing does not authorize agent effects | Browser/network + credential | Page cannot read local context/secret/clipboard; redirect/SSRF/new destination and auto-run blocked; declared submission exact destination receipted |
| T-06 | Malicious project/Skill subprocess with scoped invocation | B-11 → inherited environment/handles/path/network/process tree → escape, leakage or persistent child | Enforced OS isolation, scoped roots, network/secret policy, child lifetime and receipts AI-03/06/07/10 | Harness owns/reaps test child; audit hook/working directory/ignored paths are not containment | Tool Broker + platform/device | Attempt outside-root/link traversal, extra destination, inherited secret and child survival after stop denied on each OS; permitted tool still runs |
| T-07 | Captured approval/client request, no fresh owner presence | B-10 → replay/changed revision/restart race → unauthorized repeated or broadened effect | Persist approval binding principal/exact revision/effect; anti-replay and revocation at consumer; trusted local administration AI-01/02/03 | Fixture command idempotency is not human approval; nonce/storage/TOCTOU protocol remains Q3 | Mission/owner authority | Changed target/destination/revision, duplicate approval, revoked/raced execution and recovery replay denied; declared retry reconciles without repeated effect |
| T-08 | Crafted event/ACK or tampered DB/snapshot with separately acquired file access | B-06/15 → cursor/evidence/restore → counterfeit receipt, missed stop or stale grant | Core-owned atomic command/event identity, replay ownership, corruption/provenance gates, no-clobber restore, readback AI-03/08/10 | Fixture cursor/ACK and SQLite schema/integrity checks exist; no authenticated provenance/application ACL; sequential event IDs are not tamper evidence | Core/event + persistence/recovery | Foreign cursor/journal, altered event/approval, modified snapshot/reference and unsupported schema rejected; restore preserves originals and rechecks revocation |
| T-09 | Malicious content/tool requesting secrets, unauthorized private context or secret-bearing diagnostics | B-11/12/13/15 → unauthorized consumer/diagnostic/export → plaintext secret or private-data leakage | Secure-store keys separated from DB/backups; scoped opaque handles; redact diagnostics/public evidence and unauthorized export/promotion, preserve authorized local private context AI-06/07/10 | Current synthetic/plaintext fixtures and host checker do not prove consumer authorization/redaction; permitted local project context is not leakage | Credential + model/memory + observability + release | Authorized local consumer: policy-approved private project field reaches local inference and canonical memory unchanged (PC-01). Unauthorized consumer: private fields absent from unrelated context/export/global promotion and diagnostic/public sinks (PC-02/03); plaintext credential/session-secret canary absent from model/prompt/memory/log; unauthorized handle scope/export denied (PC-04) |

## Verification owners

Plan 01 owns packaged renderer/main/Core contract, numeric listener, discovery,
client identity and event/restart tests. Mission/owner authority owns presence,
immutable approval and revocation races; persistence owns DB/backup integrity,
ACL/protection and stopped-Core restore; Tool Broker/platform owns effective OS
containment and descendant cleanup. Model/memory, Skills/QA, browser/network,
credentials/observability and remote/release owners consume their rows above.
Each later slice must name a concrete task/maintainer, exact artifact, command,
negative tests, real composition and limitations. A plan cannot close a gate by
restating the mitigation. No operational control is asserted by this document.

## Residual risks

No authority expansion or data egress risk is accepted by this baseline.
Any proposal to permit either requires **explicit authenticated human owner
acceptance**, with risk ID, exact revision/effect/destination, rationale,
bounded duration, mitigation, verification evidence and revocation/rollback.
Acceptance cannot override the binding charter: a conflict requires its formal
owner-approved amendment. Silence, model judgment, document PASS or a paired
client credential is not acceptance. Until then, the affected capability is
**BLOCKED**; Gate 00 documentation may pass while product gates remain closed.

| ID | Residual uncertainty | Owner | Disposition / closure evidence | Acceptance status |
|---|---|---|---|---|
| R-01 | Local identity/discovery/account, packaged IPC and interactive approval/replay/revocation race design unresolved (Q1–Q3) | Plan 01 + mission authority | BLOCKED for product authority; packaged/client/owner negative and restart evidence required | NOT ACCEPTED; owner acceptance required for any authority expansion |
| R-02 | OS roots/ACLs, DB/WAL/SHM/blob/staging/snapshot/export at-rest protection, key lifecycle, manifest provenance and recovery objective unresolved (Q4) | Persistence + credentials/recovery | BLOCKED before personal data; specify platform secure store, key release/rotation/recovery/deletion, separated keys, protected temp/export sets and owner-authorized restore readback | NOT ACCEPTED; owner acceptance required for any data egress or expanded recovery authority |
| R-03 | Effective subprocess/network/device containment, Skill/model context, secret handling, resource/lifetime, browser/audio controls unresolved (Q5–Q6) | Tool Broker + model/memory + Skills + browser/voice | BLOCKED for sensitive implementation until E-01/02/03/05; test on each OS and actual runtime; pre-wake/raw-audio privacy remains mandatory | NOT ACCEPTED; no prompt-only or audit-hook exception |
| R-04 | Future remote pairing/discovery/encryption/revocation, audited import, signing/publication and physical platforms not exercised (Q7–Q8) | Remote + migration/release + QA | Remote stays disabled; E-04 and exact-artifact release/import gates precede enablement; physical Linux/macOS, power-loss and production scale remain NOT RUN | NOT ACCEPTED; no nonlocal listener or new publication grant |

The residual questions preserve the independent review's Q1–Q8 topics; they are
missing design/verification prerequisites, not findings. Compromise of the
invoking developer OS account is not newly inferred from caller-controlled
experiment paths. Locks/hashes do not guarantee dependency safety; release
advisory/provenance review still follows ADR 0001.

## Mandatory extensions

These formal models are required **before implementation** of the named
sensitive boundaries (SE-006); they extend this baseline and cannot silently
weaken its invariants. Updating code or choosing a library is not a substitute.

| ID | Extension / prerequisite | Required concrete coverage | Verification owner |
|---|---|---|---|
| E-01 | Browser/network | Profiles/sessions, page isolation, navigation/submission destinations/redirects/SSRF/local network, quarantine/download execution, manual versus agent authority, egress/receipts/stop | Browser/network slice before implementation |
| E-02 | Credential and protected persistence | Platform store, scoped handle issuance/use/revocation, key lifecycle, DB/sidecar/blob/staging/export protection, backup provenance/retention and local owner recovery | Credential + persistence slice before personal data or credential boundary implementation |
| E-03 | Self-evolving Skills | Origin/dependencies/license, quarantine/OS isolation, immutable version, lineage, cross-context redaction, independent exact-artifact QA/promotion/rollback | Skills/evolution slice before implementation |
| E-04 | Remote access and pairing | Explicit bind/discovery opt-in, encrypted authenticated channel, owner-presence/local administrative confirmation, device scopes, lost device/replay/revocation/recovery | Remote slice before any remote listener or pairing implementation |
| E-05 | Tools and subprocesses | Effective OS process/file/network/device grants, paths/links/inherited environment/handles, child tree/stop, secret broker, receipts and resource exhaustion | Tool Broker + platform slice before executable tool boundary implementation |

## Decision Charter Compliance

**Charter:** `docs/specs/2026-11-06-synapse-0.3-decision-charter.md`.
**Binding decisions:** CR-001, CR-002, CR-003, CR-004; VO-001, VO-006;
ME-001–ME-005; MI-001–MI-007; SK-001–SK-004; MM-001; SW-001–SW-004;
SE-001–SE-006; PL-001–PL-005; QA-001–QA-003.

| Decision | Implementation obligation | Test/evidence owner |
|---|---|---|
| CR-001–CR-004 | Clean-room/reference-only history, isolated integration/release and sanitized public evidence | B-01/02/17; release/QA |
| VO-001, VO-006 | Discard pre-activation buffer and no default raw-audio persistence | B-14; voice/device privacy tests |
| ME-001–ME-005 | Separate store semantics, authorized lazy project context, versioned promotion/privacy | B-12; model/memory negative cases |
| MI-001–MI-005 | Mission boundary, one exact-scope approval, human authority, bounded preflight and explicit external effect | AI-01/02/03/10; mission/owner authority |
| MI-006, MI-007 | Independent exact-artifact QA, automatic integration/regression/rollback | B-11/17; integration/QA |
| SK-001–SK-004 | Expertise cannot grant authority; scoped discovery, frozen lineage and project-first promotion | T-04 / E-03; Skills/QA |
| MM-001, SW-001–SW-004 | Local cognition separate from accepted temporary Swarm, bounded contexts/grants/resources and cleanup | B-12 / T-03/06; model/Swarm lifecycle |
| SE-001–SE-006 | Local-first, opaque handles, brokered agent browser, distrust, subprocess containment, formal extension gates | T-01–T-09 / E-01–E-05; named slice owners |
| PL-001–PL-005 | Headless Core, stable contracts, remote disabled, platform truth and opt-in background audio | B-08/09/14/16; Plan 01 / platform |
| QA-001–QA-003 | Scoped status, negative/real evidence, exact revision and limitations | security-review.md; foundation validator / later independent QA |

**Reviewed but not applicable:** PX-001–PX-006 visual/product presentation;
VO-002–VO-005 voice identity/language/translator UX; MM-002 resource-mode UI.
These are not changed or implemented by a foundation security document.
**Proposed deviations:** None. Contradictions stop integration and require an
owner-approved charter amendment, never automatic reinterpretation.
