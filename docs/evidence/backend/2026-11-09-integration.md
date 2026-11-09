# Integrated backend implementation status

Date: 2026-11-09. Delivery: real backend first; native frontend deferred.

Authority: `docs/specs/2026-11-06-synapse-0.3-decision-charter.md`, including the
owner's backend-first amendment; implementation design and task plan are
`docs/specs/2026-11-09-integrated-backend-design.md` and
`docs/superpowers/plans/2026-11-09-integrated-backend.md`.

## Reviewed implementation

| Component | Exact code commit reviewed | Evidence and limits |
|---|---|---|
| Rust Core, SQLite domains and actual CLI | `3b04328` | Independent specification/quality approval after two fix rounds. Twelve real-binary tests: strict protocol, ownership lock, durable idempotency/replay, chat/memory pages, UTF8 byte limits, immutable mission state and catalogs. |
| Supervised Python local AI and conversation | `d4de2dd` | Independent fix review accepted saved-chat continuation. Seven real-binary AI tests plus twelve Core regressions and five Python tests. Fixture HTTP inference only; no loaded-model operational claim. |
| Approved workspace tools, first supported slice | `830fa9d` | Independent scoped approval, no proven Important/Minor findings. Seventeen Core and seven AI binary tests plus five Python tests. Separate opt-in fault-injection test passed after durable prepare. This is not full Task3 completion. |

No old0.2 or experiment implementation was copied into the product. All modules
compose through the same Rust Core, versioned CLI and sole SQLite writer. Python
supplies data-only AI responses and cannot authorize tools or write Core state.

## Implemented paths

- Persistent chats and role-preserving, ordered selected-chat continuation,
  including after restart. No silent context truncation;64-message/48KB worker
  context budget rejects oversize with rollback.
- Versioned canonical project memory records with provenance, optimistic
  revisions and explicit context references; separate saved conversation history.
- Immutable mission proposal/approval/cancel/revoke, digest-bound requests,
  durable response receipts and cursor-based metadata events.
- Paginated model/Skill catalogs and full manifest retrieval; immutable versions.
- Async inference/conversation jobs, persistent cancellation and interruption,
  suppression of late replies and one active local inference job.
- Windows creation-time kill-on-close worker containment, strict UTF8/protocol
  validation and bounded loopback-only provider; no production synthetic fallback.
- Approved workspace list/read/create-new, exact resource/action/artifact hash,
  immutable Skill pin/permission checks, bounded receipts and protected state.
  Windows fixed NTFS only; reparse points and hard-linked regular files denied.
- Durable prepared file intent before effects. Interrupted/ambiguous intentions
  reserve the request and target and return `recovery_required`; they do not
  automatically adopt, overwrite, delete or replay a file operation.

## Explicit remaining work

Full backend is **not complete**. Missing functionality must not be relabelled
operational because these integrated paths pass:

- Artifact replacement with tested backup/rollback and operational intent recovery.
- Skill instructions connected to generation, audited discovery, candidate
  evolution, independent QA and automatic promotion/rollback.
- Model/resource routing, consent-gated temporary Swarm execution and cleanup.
- Automatic validated canonical memory learning; current memory write is explicit.
- Voice/wake/STT/TTS/translation and protected internal browser/device adapters.
- Natural-language mission planning and complete isolated project/git integration.
- Actual model inference, streaming and resource validation; no model was loaded
  for these tests and no weights were downloaded.
- Relocatable Python package/runtime distribution and Linux/macOS execution.
- Native frontend and real device/platform validation.

Existing packages initially carry development0.1 metadata; product0.3/version1
protocol labeling must be aligned in the final backend handoff. The project and
branch target remain Synapse0.3. Clippy was unavailable and NOT RUN.

## Reproduction

From the repository root on the measured Windows/MSVC/Python3.14.3 host:

```powershell
cargo fmt --all -- --check
cargo test -p synapse-core --locked
py -3.14 -m unittest discover -s backend/python/tests -v
cargo test -p synapse-core --locked --features test-fault-injection --test core_cli tool_crash_after_durable_prepare_does_not_apply_or_replay -- --nocapture
```

Run sequentially: Windows refuses replacing a test executable while it is
running. Fault injection is opt-in and excluded from the normal build. Fixtures
use temporary roots/local HTTP servers. Existing observed outputs were reviewed;
reviewers did not rerun complete suites. Tests cover named failure points, not
arbitrary power loss or every filesystem instruction.

For actual use, see `backend/contracts/v1/README.md` and the root README.
`SYNAPSE_PYTHON_EXECUTABLE` names the actual interpreter; a model must be explicitly
registered/configured. Provider discovery is not proof of model residency.

## Decision Charter Compliance

Binding: CR-001/004, PX-001/002, ME-001–005, MI-001–007, SK-001–004,
SE-001–006, PL-001/003/004/006 and QA-001–003. Record storage, mission states,
permission enforcement and process integration are tested as listed. Memory
learning, complete Skill execution/evolution and remaining project automation
are pending, not satisfied by registries alone. Visual/voice/device and full
MoM/Swarm runtime gates remain pending as listed. No whole-product acceptance,
cloud fallback, credential access, shared-branch push or release is claimed.
