# Mission candidate generation, native check and review

The Core now accepts `mission_execute` on an approved sealed mission and
persists one candidate lineage in schema 11. It records the exact staged
candidate digest, runs each fixed native check and invokes the pinned review
configuration only when every receipt passes. Rejection and cancellation
remain durable. Candidate bytes stay in Core storage. This milestone ends
at the review decision.

## Real CLI exercise

The loaded Qwen3.5 4B planned one standard-library Python file,
`test_math.py`. An explicit approval bound the plan. A generation call
created the exact candidate and the dedicated CPython check compiled and
ran its tests under verified LPAC. A separate review call with different
generation settings received the objective, candidate bytes and observed
check phases. It approved the result. This run used the same model weights
for both invocations. The Workspace remained empty. Two real runs reached review readiness. The second took 36.901 seconds after approval.

## Negative controls

The configured CLI fixture exercises an approved review after two sequential native checks, rejection after
passing native checks, a native test failure, an unapproved generated path,
cancellation during generation, and restart after interruption. It also
revokes a review-ready mission and preserves the historical verdict while
removing readiness. Runs stopped before review never call the reviewer. No tested run writes Workspace files.

The worker tests cover distinct static schemas and JSON escaping at the
candidate byte limit. Conversation, learning and planning retain their
existing wire limits. The public command contract is in
[protocol v1](../../../backend/contracts/v1/README.md).

The final run passed 59 CLI regressions, five Rust unit tests, ten Python
worker tests and the configured coordinator fixture with all six scenarios.
Independent review found and prompted fixes for legacy cancellation,
revocation after approval, phase failure diagnostics and escaped wire sizes.
The local live receipts and regression logs are in
`.superpowers/mission-candidate-review/`.
