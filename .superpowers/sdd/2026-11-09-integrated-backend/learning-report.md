# Automatic context learning — implementation evidence

Implementation based on `398a668`, retaining controller evidence commit `9eae18f`.
This is a self-review; independent review and a live model smoke remain pending.

## Interfaces and chronology

The existing successful conversation transaction queues one learning job per source
job. Its project, human message, model, endpoint and generation are pinned by the
source job. The internal worker protocol is version 3 with a required purpose;
the public protocol remains version 1 and adds `learning_get` by source job ID.
The same supervised worker receives a fixed instruction and only the latest human
message, with a static `response_format` JSON schema. The classifier cannot choose
the scope or call a tool. Foreground starts terminate and requeue active learning;
restart and polling resume queued work with bounded attempts. Extracted output is
validated as a complete batch before any writes. Canonical records use actual user
message/job provenance, the original project's scope, a bounded exact quotation,
and typed kinds. Duplicate keys in one batch are rejected. Content already stored
is deduplicated; source event cursors, not extraction completion times, decide
precedence. Conflicts are exposed as typed pending metadata. Status and memory
changes commit together. Explicit context remains required for retrieval.

Manual revisions receive the cursor of their memory event. Automatic revisions
use the cursor captured immediately after the source user message event. Existing
schema-5 records migrate conservatively to the current event cursor. The source
ordering binary test starts the newer turn while the old extraction is held, then
allows old extraction to complete first: the newer source still becomes revision 2.

The provider request follows [LM Studio structured output documentation](https://lmstudio.ai/docs/developer/openai-compat/structured-output),
which documents JSON schema via `response_format` for chat completions. Core does
not trust schema enforcement by the provider. No dependency or model was added.

## Verification on Windows

No red test run was recorded before implementation; do not infer a TDD red phase.

* `cargo check -p synapse-core --locked` — passed.
* `cargo fmt --all` — passed.
* `cargo test -p synapse-core --locked` — passed: 13 AI binary tests and 22 Core binary tests. The subsequent cancellation assertion was additionally exercised in the fault-feature run below.
* `cargo test -p synapse-core --locked --features test-fault-injection` — passed: 13 AI binary tests and 26 Core binary tests, including four fault-injection tests.
* `py -3.14 -m unittest discover -s backend/python/tests` — passed: 7 tests.
* `git diff --check` — passed (only line-ending notices).

Binary fixtures exercise automatic extraction, revision, duplicate suppression,
restart/interruption, context denial, invalid batch/no partial write, injected
scope, invented quote, oversize quote, credential rejection, duplicate candidate
keys, empty batch, pending kind conflict, cancellation without enqueue, foreground
preemption, manual stale protection and older/newer source chronology. The
test-only HTTP fixture can return an empty candidate list or scripted candidates;
production has no fake fallback. Python tests exercise purpose and schema mapping,
unknown purpose and old-version rejection, generation mapping and provider errors.

## Limitations

No real model was loaded or invoked for this work. A separate end-to-end local
model smoke must confirm actual extraction, provenance, explicit retrieval and
restart using the intended model and endpoint. Structured output support and
configured token budgets vary by model; such failures leave the conversation
successful and learning failed after bounded attempts. The credential checks are
conservative heuristics, not comprehensive secret detection. Exact quotation is
enforced, but the model's selection of a durable fact versus a transient or
semantically incorrect statement cannot be guaranteed by syntactic validation.
The pending conflict metadata does not itself provide a conflict resolution UI.

## Fix round 1 — source meaning and attribution

Review identified that arbitrary source substrings could reverse a negation or
attribute a quoted statement or instruction to the human. Core now requires
the candidate to equal the complete trimmed source message, with only one short
sentence, a recognized first-person assertion starter, and conservative exclusion
of quotation marks, attribution and command-like terms. The classifier prompt asks
for complete source units and an empty result for ambiguous messages. The JSON
schema and public API did not change. This intentionally rejects many legitimate
statements; a lexical gate cannot prove meaning, attribution, durability or the
absence of every possible command. The model's classification remains fallible.

Covering file: `backend/core/tests/ai_cli.rs`. The actual-binary adversarial test
checks clipped negation, attributed assistant content, quotation marks, a command,
first-person command-like text, a clipped multi-sentence source, a whole negative
assertion and a whole Portuguese assertion, and confirms no rejected value appears
as a revision. The regression run also retains preemption and restart tests.

* RED: `cargo test -p synapse-core --locked --test ai_cli learning_rejects_negation_clipping_attribution_and_commands -- --exact` — failed on the clipped-negation case, before the fix.
* GREEN: `cargo fmt --all; cargo test -p synapse-core --locked` — passed: 14 AI binary tests and 22 Core binary tests.

The requested scenario in which an older automatic extraction publishes *after*
a newer automatic record cannot be produced through the current supported queue:
there is one active worker, preemption joins and discards its result, queued jobs
are selected in source-cursor order, and an exhausted failed job has no public
requeue operation. The existing test does prove that a newer source survives an
older publication whose completion event occurs after that newer source event;
the existing manual-write test proves a genuinely stale source is rejected. An
artificial database mutation or concurrent writer would not prove the supported
single-worker path, so no such test is claimed here.
