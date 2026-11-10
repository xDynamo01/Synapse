# Per-model Generation Settings Implementation Plan

> Agentic workers: subagent-driven-development, then independent scoped review.
> This is actual backend integration, already owner-authorized.

**Goal:** Configure a real local model without silent global changes or fixed
generation limits that make the CPU backend time out on normal inference.

**Architecture:** Optional immutable-per-job generation settings are validated
on model registration, captured by Core at job start and included in the bounded
worker digest. Public API stays v1. Worker protocol evolves explicitly and
rejects incompatible peers. Python never sets grants or writes Core storage.

**Tech Stack:** existing Rust/Python3.14 stdlib local provider, no new inference
runtime or model weights.

**Spec:** integrated backend design and Task2/T4 of the integrated backend plan.
**Evidence:** `docs/evidence/backend/2026-11-10-local-inference-diagnostic.md`.

## Global Constraints / Decision Charter Compliance

Charter: `docs/specs/2026-11-06-synapse-0.3-decision-charter.md`,
MM-001/002, SE-001/002/005, PL-001/006, QA-001–003. No global
Responsive/Economical mode; no proxy/redirect/cloud fallback. Model advertisement
does not establish residency or resource fit. Never execute tool-call output.

## Review Focus

- Missing config preserves documented legacy behavior and request shape.
- Wrong types, booleans as integers, unknown fields and unbounded limits fail.
- Registered config changes cannot mutate an already-running job.
- Cancellation remains responsive even with a longer allowed deadline.
- Real model output must complete through Core and persist once, not a shim.

## Task 1 — Model configuration across the real Rust/Python boundary

Files: contracts, registry, conversation, worker, store only as needed;
Python protocol/providers/worker and both Rust/Python tests; v1 README.

- [ ] Add actual-binary/provider payload tests failing before the feature.
- [ ] Add optional `generation` to ModelManifest, default omitted for old
      clients. A supplied object has explicit required `max_output_tokens`
      (1..4096), `timeout_ms` (250..120000) and `reasoning_effort`
      (`provider_default`, `none`, `low`, `medium`, `high`); unknown fields denied.
- [ ] Resolve absent config to legacy1024 tokens/10000ms/provider-default.
      Capture effective config in durable job metadata; never reread it from a
      mutable registry while the job runs. Worker request digest covers settings.
- [ ] Map output tokens to provider `max_tokens`; omit reasoning field only for
      provider_default. Unsupported provider/model settings produce typed errors,
      not silent reasoning or endpoint fallback. Use configured HTTP deadline and
      supervisor deadline plus bounded5000ms startup/cleanup margin.
- [ ] Keep endpoint isolation, strict UTF8/JSON bounds and actual chat roles.
      Evolve worker protocol version if required; reject old/mismatched workers.
- [ ] Verify actual-binary config payload, restart/readback, pinning during model
      update, malformed limits, unknown model errors, cancel/timeout and existing
      regression. Python tests cover exact mapping and bool/type rejection.
- [ ] Commit/self-review and independent review. Then a separate real-model
      smoke on safe measured resources must use the exact Core binary directly.
      Synthetic fixtures are not model-operation evidence. Use own temporary
      loaded identifier and unload only the model opened for validation.

Real smoke target: two short Portuguese turns plus saved history/reopen and
cancellation. Record binary/source/config hashes, actual content, timings and
limits. No automatic learning/Swarm acceptance follows from this one feature.
