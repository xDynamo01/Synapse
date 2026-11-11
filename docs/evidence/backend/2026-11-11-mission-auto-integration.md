# Automatic integration through the Core CLI

Windows schema 12 records the Workspace identity at approval. A reviewed
candidate is published by the existing broker with exclusive create-new
operations and durable intents. The Core reads the published files with
identity and byte guards, stages those observed bytes for the approved
postchecks, and requires the tool digests recorded by the corresponding
prechecks. Final readback holds the file and root handles until commit.

Known postcheck failure triggers handle-based removal of owned unchanged
files while authorization remains approved. A changed target, revocation
after writing, or ambiguous interruption preserves the files and reports
`recovery_required` with paths and intent IDs. Those targets remain
reserved. This scope does not add automatic recovery for ambiguous effects.

## Actual local model run

LM Studio listened on 127.0.0.1:1234 with the installed Qwen3.5 4B loaded
at 32,768 context tokens and one parallel slot. The actual Core CLI
planned a single Python file, accepted one explicit approval, generated
the candidate, ran the LPAC check, requested a separate review and
published the file into an empty non-Git test Workspace. It then ran
the postcheck and reached `integrated` in 66.499 seconds after approval.

Both native checks recorded success, verified cleanup, matching tool
digests and matching candidate digests. A read-only verification matched
the actual published bytes to the Core-sealed candidate and the confirmed
tool intent. The 1,495-byte `test_math.py` SHA-256 was
`ca652e9f70bc9d8933ff6a5ea1f23d7a5cc4e68ee25239cc2c12082dabbe0931`.

## Mixed Rust and Python generation

Two initial local attempts returned only the first of the two approved
artifacts. Core rejected both candidates before executing any checks or
writing the Workspace. A direct local diagnostic reproduced the one-item
response. The worker now specializes its fixed generation schema with the
approved artifact count and path enumeration. Core still verifies every
approved path occurs exactly once and enforces UTF-8 byte limits.

After that change, the actual local model produced both `calc.rs` and
`test_math.py`. The separate review accepted both and the Core published
them after two passing prechecks. Both postchecks passed and the run
reached `integrated` in 139.194 seconds after approval. A read-only
comparison verified the two published files against the sealed candidate,
confirmed intents and matching pre/post tool digests for each language.

## Controlled outcomes

The CLI fixture uses the real dedicated CPython runner with a controlled
provider. It covers successful two-file publication and postchecks,
pre-existing target preservation, rollback on rejected postcheck tool
identity, interruption before and after an effect, revoke after writing,
Workspace replacement after approval, Git ancestor refusal, and existing
candidate, test and review rejections. The broker unit tests cover hardlinks,
replaced identity, changed contents, deletion refusal and guarded readback.

The owner-facing states and setup are in [protocol v1](../../../backend/contracts/v1/README.md).
Local receipts and logs are in `.superpowers/mission-auto-integration/`.

Verification passed 59 CLI regressions, 13 Rust unit tests, ten Python worker
tests and the three configured native CLI tests. The integration fixture was
rerun after the model-schema change and passed in 79.44 seconds. Independent
review checked the approval binding, durable reservations, guarded readback
and schema specialization.
