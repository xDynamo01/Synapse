# ADR 0002: Versioned client/Core transport

Date: 2026-11-06

Status: **ACCEPTED — Windows transport experiment TESTED / PASS**.
The independent review and aggregate regression are Gate 00 obligations.
Product, packaged Electron, Linux/macOS execution and remote pairing are
**NOT RUN**.

## Decision

Use **gRPC over HTTP/2 with Protocol Buffers** at the independent client/Core
boundary. Start with package `synapse.foundation.v1` in the
[versioned schema](../../experiments/transport/proto/synapse/foundation/v1/lifecycle.proto).
Use the pinned toolchain in [ADR 0001](0001-core-runtime-and-toolchain.md).
The Windows experiment exercises Python gRPC with generated messages and
stubs, and Node gRPC with a loaded descriptor and generated TypeScript
declarations. Plan 01 owns production dependency and distribution approval.

Both candidates passed the same Windows lifecycle. The gRPC path keeps one
versioned schema and service definition across unary calls and the bidirectional
event stream. Type generation and operation dispatch use the same descriptor.
HTTP/WebSocket can share TypeScript shapes but needs custom routes, JSON decoding
and WebSocket framing. The measured gRPC process starts with lower median RSS
and reaches readiness sooner on the test host. The evidence records all samples
and their scope. [Transport evidence](../evidence/foundation/transport-spike.md)

## Contract and lifecycle

| Operation | Semantics |
|---|---|
| `GetStatus` | Reports health, server contract version, admitted command count and latest event cursor. |
| `SubmitCommand` | Atomically commits the admitted command and its acknowledgment event before returning. Reusing a `command_id` with the same immutable input returns the original acknowledgment with `duplicate=true`. Changed input returns `COMMAND_CONFLICT`. |
| `CancelCommand` | Persists one cancellation event for an admitted command. Retries return that same event. Unknown IDs return `NOT_FOUND`. This test cancels a held fixture command. |
| `SubscribeEvents` | Opens with an exclusive `after_event_id` cursor and has no fixed maximum age. Delivers ascending events and accepts one acknowledgment per outstanding event. An invalid cursor or ACK yields a structured error. A stalled consumer receives `BACKPRESSURE` with its last acknowledged cursor and the stream closes. |

A command and its events carry `command_id` and `causation_id`. Event IDs are
monotonic decimal strings scoped to the journal. Structured domain errors carry
`code`, `message`, `retryable` and `last_event_id`. Transport and connection
failures use the client's transport error path. The test accepts well-formed
major 1 requests and returns the implemented version `1.0`. New minor fields
must be additive, with optional presence and compatible defaults where needed.
Reserve deleted tags and names, preserve published field meanings, and use a
new package/service major for breaking changes. Clients explicitly reconnect
and resume from the last processed event. A client reconciles ambiguous
submission outcomes through the same command ID and immutable input.
[Protocol Buffers field evolution](https://protobuf.dev/programming-guides/proto3/)

The shared experimental journal caps admission at 128 commands, uses a
one-event acknowledgment window with a 500 ms deadline, and configures 4 KiB
transport message ceilings. The clients also bound individual event reads
in the fixture. These bounds and the opening-frame deadline are fixture
parameters. Production retention, admission limits, deadlines and storage
selection require their own evidence. Socket and HTTP/2 flow control protect the transport buffer. The
application acknowledgment keeps replay tied to consumption.
[gRPC flow control](https://grpc.io/docs/guides/flow-control/)

## Electron and authority boundary

The renderer calls a narrow, named preload API. The preload uses Electron IPC
to the main process. Main validates the sender, frame, method, payload and
subscription ownership, owns Core discovery and credentials, and terminates
the gRPC connection. Configure context isolation and renderer sandboxing,
disable Node integration, and limit renderer network and navigation via CSP
and allowlists. Expose typed operations and bounded event delivery through
`contextBridge`. Keep the transport, token, endpoint, raw IPC and arbitrary
network/command capability out of the renderer and preload API. Main cancels
subscriptions when the authorized consumer is destroyed or navigates away.
Packaged Electron must exercise the allowed route and deny renderer bypass and
forged IPC before integration acceptance.
[Electron security](https://www.electronjs.org/docs/latest/tutorial/security),
[Electron IPC](https://www.electronjs.org/docs/latest/tutorial/ipc)

Core rechecks authentication and all mission authority. CLI, future clients,
renderer and main cannot confer approval through transport metadata. Only the
authenticated human owner can approve, revise, revoke or discretionarily cancel
missions. Core can halt within its enforcement policy and must limit activity
before approval to the charter's bounded preflight. The spike uses a fixed
public test bearer on an ephemeral numeric loopback bind with one effect-free
action. Test authentication does not supply product identity or authorization.

## Alternatives and gates

| Candidate | Result |
|---|---|
| gRPC/Protobuf | Selected. One service schema, Python stubs and generated Node types. Requires locked code generation, HTTP/2-aware packaging and verification of Electron's embedded Node. |
| HTTP/JSON plus WebSocket | Windows comparison passes. Browser tooling and JSON inspection are convenient. Separate routes, JSON decoding and WebSocket lifecycle carry more adapter responsibilities. Kept as experiment evidence. |

Future desktop and mobile clients can use the same Protobuf messages and
service when Core moves to the owner's server. gRPC supports TLS and
authenticated credentials at the transport layer. HTTP/WebSocket could also
use HTTPS/WSS with a separately designed credential protocol. Pairing,
credential provisioning, revocation, encrypted channels, discovery and device
authority require the formal remote-access threat model and a later scoped
implementation. The spike exercises neither certificates nor pairing.
[gRPC authentication](https://grpc.io/docs/guides/auth/),
[aiohttp server TLS configuration](https://docs.aiohttp.org/en/stable/web_reference.html#aiohttp.web.TCPSite)

Plan 01 must run locked installs, generation, contract negatives, real
cancellation, long-lived subscriptions, backpressure, kill/restart and cursor
replay for gRPC on Windows 11 x64, Ubuntu 24.04 x64/glibc and macOS 14+ arm64.
It must also verify the selected packaged Electron and renderer/main boundary
on the applicable platform lanes. Linux/macOS CI evidence does not replace PL-004 physical
validation. Reopening the transport choice requires a superseding ADR and the
same two-candidate comparison. Rollback of this spike is a repository revert
and recreation of local environments. It has no deployed state.

## Decision Charter Compliance

| Binding decision | Evidence or downstream requirement |
|---|---|
| CR-001, CR-004 | Clean-room fixture with disposable journals, local artifacts ignored and public evidence limited to aggregate timings, pins and hashes. |
| MI-003, MI-004 | Effect-free test command; product owner policy and preflight enforced by Core in Plan 01 and mission slices. |
| SE-005, SE-006 | Client-only CLI/main boundary, with sensitive subprocess and remote capabilities gated by formal threat models. |
| PL-001, PL-002, PL-003 | Headless Core, independent typed client, remote TLS migration path and one process with a shared lifecycle implementation. |
| PL-004 | Windows experiment TESTED / PASS. Three-platform CI and physical validation are separate gates. |
| QA-001, QA-002, QA-003 | Status scoped to the experiment. Exact inputs, commands, negatives, process reaping and selected rerun in linked evidence and the Task 3 execution report. |

Reviewed but not applicable: voice, memory, model execution, browser and Skills
behavior. Proposed deviations: None.
