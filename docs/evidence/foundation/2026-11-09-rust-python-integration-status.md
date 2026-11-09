# Rust/Python integration validation status

Date: 2026-11-09. Gate 00: **BLOCKED / REOPENED**.

Binding authority: `docs/specs/2026-11-06-synapse-0.3-decision-charter.md`,
CR-001/004, MI-003, SE-005, PL-001/004/006 and QA-001–003. These records describe
experiments only; none authorizes product scaffolding or a permanent Core owner.

## Completed and independently reviewed

| Artifact | Exact reviewed commit | Result and boundary |
|---|---|---|
| First Rust/Python boundary comparison | `b362e3002a25e290f5976e4b5f58b99f971ac511` | PASS as throwaway spike; worker contains tested Python exit, embedding shares fatal exit. Schema-negative controls and identity-safe observer cleanup corrected and reviewed. |
| Windows worker lifetime containment | `52b79a6f69d3c494b565e0a50df23d7727613c65` | Specification and quality PASS, no Important findings. Ten alternating hung/busy worker+descendant runs exit after Rust hard death; observed 2.396–3.292 ms. Creation-time membership, suspended-child death, setup refusal, normal/deadline cleanup and original regression covered. |

Evidence and reproduction:

- `rust-python-boundary-spike.md` retains the first comparison, original orphan
  and volatile restart state; it is historical behavior before containment.
- `rust-python-worker-containment.md` supersedes the worker-orphan observation
  for the tested Windows artifact only. It is process lifetime containment,
  not a filesystem/network/credential security sandbox.
- `rust-native-ui-research.md` records primary-source feasibility research;
  actual native UI, audio, accessibility and browser probes remain NOT RUN.

Actual first-spike runtime: Rust 1.96.0/MSVC and CPython 3.14.3. Historical
3.14.10 receipts do not certify this runtime. Exact source, lock, executable and
runtime hashes are in the experiment evidence. Clippy was absent and NOT RUN.
Independent reviewers inspected existing receipts rather than repeating suites.

## Outstanding integration obligations

| Obligation | Current state | Required next proof |
|---|---|---|
| Durable cancellation, revocation and duplicate-effect prevention | BLOCKED: first spike uses volatile job state | One authoritative owner/writer; persist state before acknowledgement; crash/restart/readback and digest-bound idempotency fixtures |
| Ordered reconnect/replay and schema evolution | NOT RUN in new Rust boundary | Versioned generated contracts, bounded events and real Rust/Python restart fixtures |
| Native UI, real audio and accessibility | Research only | Comparable native candidates and actual OS accessibility/audio observations |
| Internal native browser | Research only | No authored JS bridge, policy enforcement and platform-specific hosting/automation proof |
| Storage in chosen ownership model | Historical Python-only evidence | Validate actual Rust/Python transaction and acknowledgement owner, >=100 verified deaths, recovery/migration/backup/restore |
| Standalone worker packaging | NOT RUN | Worker-only Rust host without embedded Python DLL coupling; clean-clone/offline discovery and distribution proof |
| Linux/macOS and restrictive host jobs/native faults | NOT RUN | Named platform lanes and explicit real-hardware limits; no Windows result substitutes |
| Updated security and aggregate gate | BLOCKED | Actual native consumers and allowed/denied-path evidence; legacy Node receipts cannot pass |

## Delivery discipline

Each next task cites the Charter, tests the real process/artifact and receives
independent review. Existing shared sources stay untouched by reference-only
0.2 code. No cloud inference, model weights, account access, production tools,
personal data or shared-branch publication was used by these experiments.

The next bounded task is persistent cancellation/idempotency ownership design
and its crash fixtures; it must not introduce two authoritative state stores.
