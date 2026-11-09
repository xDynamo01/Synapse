# Foundation authority invariants

## Scope and status

These non-negotiable requirements bind Plan 01 and every later mission, client,
model, tool, browser, Skill, credential and remote-access slice. They consume
ADRs 0001–0003 and the binding
`docs/specs/2026-11-06-synapse-0.3-decision-charter.md`.
They specify future Core/OS enforcement. They do not claim that experimental
bearer checks, Python audit hooks, process ownership or SQLite integrity checks
already implement product authority. Source baseline:
`009fe94f71b711af3a4cb688d9da6b8cbdfae538` (2026-11-09 review).

## Authority invariants

All checks default to refusal when identity, scope, ownership, version, policy
or evidence is absent/ambiguous. Enforcement belongs at the sensitive consumer,
not merely the UI/prompt. A refusal must not emit a secret-bearing diagnostic.

| ID | Invariant | Non-negotiable rule | Enforcement owner | Required verification |
|---|---|---|---|---|
| AI-01 | Authenticated human owner approval | Only owner may approve/revise/revoke/discretionarily cancel. Routine paired approvals require interactive presence; pairing, credential export and recovery-policy changes require trusted local confirmation. Client auth never equals approval. | Core mission/owner authority; trusted local confirmation component | Deny model/Skill/client metadata approval, unattended paired request and remote authority administration without trusted local confirmation; valid owner path succeeds |
| AI-02 | Immutable scope and effect | One approval binds exact contract revision, Workspace/targets/account/tools/permissions/destinations/data leaving/budgets/QA/rollback/external effect. Declared actions run autonomously without repeated approval; expansion/change requires revised contract and approval. Persist replay-resistant approval binding and recheck at effect time. | Core mission state + Tool Broker/effect consumer | Changed revision/target/destination/effect, stale/duplicate approval, preflight write/code/network/secret access denied; declared retry reconciles without repeat external effect |
| AI-03 | Core enforcement stops | Core automatically halts on revocation, failed gate, exhausted budget, stop condition, policy or invariant breach. Stops may only reduce authority. Reconnect/restart/recovery cannot resurrect a grant; bound in-flight and descendant cleanup semantics. | Core scheduler/mission/revocation + OS/device broker | Revoke during queued/in-flight execution, exhaust budget, fail QA, kill/restart/replay; prove no new effect after enforced stop and owned child cleanup |
| AI-04 | Client authentication and ownership | Independently authenticate desktop main, CLI and Device Bridge with scoped identities; Core checks every call and stream ownership. Unknown, expired, revoked or wrongly scoped identity is denied. Credential issuance/storage/rotation/discovery must be designed before product integration. | Core transport/auth + platform credential adapter | Forged/revoked identity, duplicate/missing auth, wrong client/stream/cursor ownership denied at Core even with compromised main |
| AI-05 | Numeric loopback by default | Initial listener binds only numeric loopback; no wildcard/LAN bind, remote discovery or silent fallback. Remote listening remains disabled until separately modeled, explicitly enabled authenticated encrypted pairing/revocation gate. Loopback reachability confers no authority. | Core startup/configuration + remote gate | Inspect actual socket and negative configuration on supported OS; refuse wildcard/nonlocal initial bind; remote remains closed without E-04 evidence |
| AI-06 | Opaque scoped secret handles | Credentials/keys live in platform encrypted secure storage, separate from DB/WAL/SHM/blobs/backups. Only enforcing broker/adapter may resolve scoped handles for declared target/account/use. Models/prompts/memory/logs receive handles only; revocation and recovery cannot expand scope. | Credential broker + platform secure store + effect consumer | Deny wrong-scope/expired/revoked handle, plaintext secret request, unauthorized export and inherited subprocess secret; verify store/key lifecycle and protected staging/export |
| AI-07 | Log and evidence redaction | Allowlist/minimize diagnostics and receipts; redact credentials, session material, private context and personal data before persistence/export/model delivery. No secrets/raw audio/runtime personal state enter Git. Pre-wake audio stays ephemeral; raw audio not persisted by default. | Core observability + memory/voice + release reviewers | Canary secrets/sessions/private records absent across prompt, memory, traces, crash/error, receipts, snapshots metadata and Git; inspect allowed sanitized output |
| AI-08 | Authoritative state and evidence | Core owns command/causation/event identity and atomic admission; idempotent immutable retries/cancel and owned ascending cursor replay cannot create authority. SQLite structural validity is not approval/provenance. Preserve original on corruption; validate authorized backup/reference set/readback before stopped-Core switch. | Core event/persistence/recovery + OS file protection | Reject altered/foreign event/cursor/approval/snapshot/schema and stale journals; crash/restart/replay preserve committed state and current revocations; restore content/reference readback |
| AI-09 | Packaged client boundary | Renderer is untrusted; named preload only. Main owns endpoint/token, validates sender/frame/method/payload/subscription, bounds delivery and closes on navigation/destruction. Context isolation/sandbox on, Node off, restrictive network/navigation. No raw IPC/transport/arbitrary command exposed. | Electron main/preload + packaged platform QA; Core rechecks auth | In packaged app deny forged frame/raw IPC/network bypass and token discovery, verify subscription teardown and permitted round trip with actual embedded Node |
| AI-10 | Denial by default and least authority | Absence of explicit grant denies effect. Models/Skills/web/CLI/agents cannot mint grants. Enforce project context and OS file/network/device/process boundaries; read-only direct user Workspace grant does not permit persistent/executable/network/account effects. No silent cloud inference, global promotion, Swarm activation or remote enablement. | Core policy/Tool Broker + OS/device + model/memory/Skill lifecycle | Adversarial content, subprocess escape, undeclared egress/context/promotion and unaccepted Swarm denied; allowed scoped operation still works; receipts and resource/lifetime cleanup verified |

Authoritative sources: `docs/specs/2026-11-06-synapse-0.3-decision-charter.md:182-229`,
`docs/specs/2026-11-06-synapse-0.3-decision-charter.md:301-337`,
`docs/specs/2026-11-06-synapse-0.3-clean-room-design.md:194-212`,
`docs/specs/2026-11-06-synapse-0.3-clean-room-design.md:288-298`,
`docs/specs/2026-11-06-synapse-0.3-clean-room-design.md:306-382`,
`docs/specs/2026-11-06-synapse-0.3-clean-room-design.md:384-518`,
`docs/adr/0002-client-core-transport.md:58-104`,
`docs/adr/0003-foundation-persistence.md:28-81`.

## Verification owners

The enforcement owner in each row must name a concrete implementation task and
independent verification owner in its consuming plan. Plan 01 owns AI-04/05/09
and the initial state/event boundary; mission authority owns AI-01/02/03.
Credential/observability/persistence plans own AI-06/07/08. Each tool/model/Skill/
browser/remote plan must prove AI-10 and all other applicable rows at its own
consumer. Evidence binds exact revision, environment, command, negative result,
allowed-path composition, limitations and rollback. Structural document PASS
cannot close a runtime enforcement gate or qualify physical platform behavior.

## Residual risks

The threat model's R-01–R-04 remain **NOT ACCEPTED**. No authority expansion or
data egress is permitted by documenting an uncertainty. Explicit human owner
acceptance must identify the exact risk/effect/revision and mitigation; charter
contradictions also require its formal amendment. Sensitive implementations
remain BLOCKED until applicable E-01–E-05 models and enforcement evidence exist.
Credential/at-rest protection and key lifecycle remain unresolved implementation
designs, so personal-data use of plaintext experiment paths is not authorized.
See [foundation-threat-model.md](foundation-threat-model.md).

## Decision Charter Compliance

**Charter:** `docs/specs/2026-11-06-synapse-0.3-decision-charter.md`.
**Binding decisions:** CR-001, CR-004; VO-001, VO-006; ME-001–ME-005;
MI-001–MI-007; SK-001–SK-004; MM-001; SW-001–SW-004; SE-001–SE-006;
PL-001–PL-005; QA-001–QA-003.

| Decision | Implementation obligation | Test/evidence owner |
|---|---|---|
| CR-001, CR-004; VO-001, VO-006 | Clean-room and privacy/evidence hygiene | AI-07/08; voice/release/persistence |
| ME-001–ME-005; MM-001; SW-001–SW-004 | Scoped/versioned context, local cognition and accepted bounded temporary agents | AI-10; model/memory/lifecycle |
| MI-001–MI-007 | Immutable one-time approval, human authority, Core stops, preflight limits, exact effects and independent QA/integration | AI-01/02/03/08; mission/QA |
| SK-001–SK-004; SE-001–SE-006 | No expertise-derived authority, formal models, broker/OS enforcement, handles and distrust | AI-02/06/07/10; sensitive slice owners |
| PL-001–PL-005 | Headless authoritative Core, independent scoped clients, loopback/remote gate and truthful physical validation | AI-04/05/09; Plan 01/platform |
| QA-001–QA-003 | Exact artifact, negatives and real composition with scoped status | security-review.md; consuming independent QA |

**Reviewed but not applicable:** CR-002/CR-003 archival/branch mechanics are
unchanged; PX-001–PX-006, VO-002–VO-005 and MM-002 describe product presentation,
voice/language and resource UI not implemented here. **Proposed deviations:**
None. A later plan must cite the exact applicable invariant IDs and cannot
weaken them without the corresponding owner-approved charter amendment.
