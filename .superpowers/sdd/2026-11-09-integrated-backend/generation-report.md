# Per-model generation settings

Public v1 model manifests may omit `generation`; effective defaults are 1024 tokens, 10000 ms and `provider_default`. A supplied object requires all three fields, strict types, no unknown keys, token range 1–4096 and timeout range 250–120000 ms. Core stores the effective snapshot with each job (schema v5) and exposes it in `job_get`. The internal worker contract is v2 and its digest includes that snapshot. The local provider maps output tokens to `max_tokens`, omits `reasoning_effort` only for `provider_default`, and uses the configured HTTP timeout. Core applies the configured timeout plus a 5000 ms supervisor margin. Cancellation remains independent of the timeout.

## Validation and chronology

- Before implementation, `py -3.14 -m unittest discover -s tests -p test_worker.py` failed the new generation mapping test (1 failure, 5 passed). The new actual-binary tests were added after implementation, so they do not constitute a pre-implementation RED run.
- `cargo test -- --test-threads=1` initially had 9 AI tests pass and 21 of 22 Core tests pass; the future-schema test still used version 5, now the current schema. Updated that fixture to version 6.
- After the correction, `cargo test -- --test-threads=1`: 9 AI binary tests and 22 Core binary tests passed, including existing rollback tests. `cargo fmt --check` passed.
- `py -3.14 -m unittest discover -s tests`: 6 passed, including all reasoning mappings, exact payload, invalid types and limits.
- The binary fixture verifies explicit provider payload, stored snapshot and restart readback, a direct simulated registry change during a held job, long-deadline cancellation and short configured timeout. The registry currently exposes no update API; the simulated update uses the test database directly.

## Limits and review

No model weights were loaded and no real-model inference was run. The fixture proves the field is sent, not that a particular model honors it. An OpenAI-compatible provider can silently ignore an unsupported `reasoning_effort`; there is no negotiated capability in the current provider protocol to distinguish that behavior from successful use. Explicit provider HTTP errors remain typed errors; silent ignoring cannot currently be detected. Thus unsupported-setting detection and the separate real-model smoke remain open. This does not complete T4 or establish model operation.
