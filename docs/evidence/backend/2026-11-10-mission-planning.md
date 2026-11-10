# Integrated mission planning — real Core and local model

Date2026-11-10. Runtime source `3d3e74f429544059864c542fce1ab4329219cf31`.
Planning/proposed-contract milestone accepted after independent scoped review,
one live-provider correction and its re-review. This is not execution acceptance.

## Actual model and observed flow

The owner reported LM Studio at localhost:1234/v1. Read-only inventory showed
Qwen3.5 4B loaded at8192 context/parallel4. At the owner's explicit request the
same installed model was reloaded at32768 context/parallel1 with automatic
placement. Native API and an actual short reply confirmed the effective settings.
No weights were downloaded. The user's model remains loaded; it was not unloaded
after the planning smoke. These are current-instance settings, not a claim that
every later LM Studio restart will preserve its default UI configuration.

The actual CLI Core registered that numeric-loopback model with an explicit
1024-token/120000ms/reasoning-none generation profile, selected an exact immutable
Skill and a human-seeded canonical constraint reference, and planned an objective
for three flat Rust/Python/documentation files and two fixed checks.
No simulated provider or direct provider HTTP call substituted for the Core run.

Observed in5.219s: valid plan, original objective unchanged, resources exactly
`calc.rs`, `test_calc.py`, `README.md`, checks `rust_test` and `python_unittest`,
captured primary/reviewer manifests and explicit distinct review generation,
fixed execution limits and a digest-bound mission in state `proposed`.
The planner did not approve the mission, generate source or write Workspace files.
A preapproval tool call was refused with `mission_not_approved`. Restarting Core
preserved the identical plan/proposal. The selected constraint was seeded through
an explicit owner memory write before planning; no planner canonical learning was
performed. Actual reviewer invocation, compilation and integration remain later.

## Live incompatibility and correction

Initial source45ee172 passed56 Rust and8 Python tests, but the real Qwen run failed
with provider_error in0.574s. LM Studio's own error identified a prompt-template
restriction: only one initial system message. The planner had separate initial
instructions, Skill and memory system pieces. A tiny direct same-schema diagnostic
returned HTTP200; it did not constitute a completed plan and did not identify the
schema as the failure cause.

The shared Core finalizer now validates all original logical pieces against
64messages/48000compactUTF8 bytes/32768per-message bytes, combines only contiguous
leading system pieces in order with explicit boundaries, then validates the final
wire messages again before user append/job insertion. Planner and conversation
both use it. Later history roles/order, protocol4, generation and canonical
learning source are unchanged. Existing histories containing a later system role
may still be rejected by such providers; there is no silent history rewrite.

Fix evidence: three focused RED cases (planner, guided conversation, merged-message
overflow), then33 affected Rust tests and8 Python tests passed. Independent
re-review accepted the fix and checked the actual Core helper, receipt, hashes,
empty Workspace and restart. The original code review's minor diagnostic concern
remains deferred: proposal failures conflate malformed output/policy/storage causes.

## Artifact identity

Ignored artifacts under `.superpowers/sdd/2026-11-10-mission-planning/`:

- `live_planner.py`: actual executable stdin/stdout controller.
- `synapse-backend-planner.exe` SHA256
  `768037b95fa95a940f0d51da5bdccfddefd089500c08b6bb3cbda5c4965d9649`.
- `live-90cac770671a4ee490a09b993ae0ba8e/receipt.json` SHA256
  `8e08e8872016d424e6216106fd2badfd99d256606afa98e15e2b3814017e0883`.
- Initial failed receipt `live-251f39dbc9d047c185fcb21acd7f6b8e/receipt.json` and
  preserved initial executable `synapse-backend-planner-45ee172.exe`.

Model/source association is observed controller metadata, not cryptographic model
attestation or an independently reproduced build. A schema-valid proposal is not
proof of semantic project correctness; the later runner and independent QA must
verify generated code before integration. No mission execution, LPAC success,
Swarm, voice or complete backend capability is inferred from this planning run.
