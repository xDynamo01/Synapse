# Voice execution boundary V1

## Scope

Piper no longer starts an operating-system process. Speech adapters describe external
work through the consumer-owned `SpeechExecutionPort`. This slice does not provide a
production executor, a Sandbox driver, provider installation, model download, network
access, microphone streaming, or playback.

## Request model

`speech-execution-request-v1` uses a structured argument vector and fixes `shell` to
`false`. It records a tool reference, transient stdin reference and checksum, logical
working-directory reference, bounded timeout, opaque environment references, input
and expected-output artifact references, correlation, policy and capability
references, plus a deterministic identity and semantic fingerprint. Secret values are
not part of the durable request identity.

The transient stdin payload exists only for the executor call. Voice does not place
text, WAV or PCM bytes in its SQLite journal through this contract.

## Result facts

`speech-execution-result-v1` separately records request acceptance, observable start,
exit, timeout, cancellation, unavailability or failure. Exit code, stdout/stderr
references, produced artifact references and termination proof are independent facts.
The result ledger requires exact request identity and fingerprint, treats an identical
late/duplicate result idempotently and rejects a contradictory result.

These distinctions are normative:

- process exit is not output verification;
- exit code zero is not valid synthesis;
- observed timeout is not termination proof.

Piper accepts a successful synthesis only after the executor reports the expected
artifact and the adapter independently verifies a non-empty, parseable WAV. The audio
is then handled by the existing Voice artifact flow.

## Sandbox boundary and capability reporting

The frozen Sandbox contracts require admission facts, a plan, materialization,
capability grants, filesystem/process/resource specifications and driver evidence.
Voice owns none of that authority and does not reconstruct those facts. No dependency
from Speech adapters to Sandbox is introduced.

Until a future Composition slice supplies a compatible executor, Piper reports
`degraded` with `execution_boundary=unavailable`. An installed executable and model do
not make the adapter operational. Piper remains local-only and requests no network or
download capability.

## Restart and later work

Voice records synthesis as running before provider dispatch. Existing Slice 5 replay
therefore preserves an interrupted request as pending/unknown and requires explicit
reconciliation; construction and replay do not dispatch Piper. Successful execution
request/result fingerprints are retained in synthesis metadata. Exact correlation
prevents a late result from rewriting another request.

Slice 7 may add Composition-owned binding to a concrete Sandbox-compatible executor.
It must supply the missing governed facts and must not weaken admission, termination,
cleanup, artifact verification, egress or secret-reference requirements.
