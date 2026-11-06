# Client/Core transport spike evidence

Captured 2026-11-06. **Windows experiment TESTED / PASS** for both candidates.
[ADR 0002](../../adr/0002-client-core-transport.md) selects gRPC/Protobuf.
Linux/macOS, packaged Electron and remote TLS/pairing are **NOT RUN**.

## Artifact and reproduction

- Worktree baseline `54ab41c`. Exact experiment inputs are identified by the
  SHA-256 manifest in the [raw Windows measurements](transport-measurements.windows.json).
  The execution report records the tested commit after the decision is committed.
- Windows 11 x64 build 26200, 6 physical/12 logical CPUs, CPU-only. The
  [host snapshot](host-capabilities.windows.json) and
  [ADR 0001 toolchain](runtime-toolchain.windows.json) identify the baseline and
  executable hashes. CPython 3.14.10 standard GIL, uv 0.13.7, Node 24.22.2,
  JavaScript pnpm 11.25.0 and TypeScript 7.0.2.
- [Run commands and tool selection](../../../experiments/transport/README.md).
  Frozen [Python](../../../experiments/transport/uv.lock) and
  [Node](../../../experiments/transport/pnpm-lock.yaml) locks record exact
  versions and artifact digests. Python code generation, TypeScript declaration
  generation and strict compilation use the local Protobuf schema.
- [Primary registry release metadata and lock cross-checks](transport-package-sources.json)
  cover grpcio and grpcio-tools 1.85.1, protobuf 7.36.2, aiohttp 3.14.5,
  grpc-js 1.14.7, proto-loader 0.8.1, ws 8.22.1 and ws types 8.18.2. The
  recorded native wheel tags support the named CI targets at the metadata
  level. Linux/macOS install and runtime checks remain required.

## RED and GREEN

With the server entrypoint temporarily held out of the worktree path, the
same Python and Node commands failed before readiness for both candidates
with Python `[Errno 2]` opening `server/main.py`. This is a reproduced
fixture negative on the adopted worktree. The entrypoint was restored before
the GREEN runs.

| Run | Python | TypeScript/Node |
|---|---:|---:|
| No-server RED | Exit 1, 4 failed | Exit 1, 2 failed |
| Both candidate paths | Exit 0, 4 passed | Exit 0, 2 passed |
| Selected gRPC path after ADR | Exit 0, 2 passed | Exit 0, 1 passed |

Both candidates execute the same parameterized fixtures against owned live
server processes. Python checks the actual listening socket of the runtime
PID and requires precisely the announced `127.0.0.1` listener. Both clients
check exact health, event, duplicate and backpressure payload shapes. The
fixtures exercise major version and authentication rejection, admission,
explicit cancellation, cursor replay and slow-consumer failure. Python also
checks same-major minor acceptance, changed-input conflicts, rejected shell
actions, invalid cursors and ACKs, eight concurrent duplicate submissions,
and the full 128-command journal cap.

The Python restart fixture observes event 1, commits event 2, forcibly kills
and reaps the Core interpreter, then reconnects to the replacement Core with
the same journal. Explicit retries return the original admission events
without advancing the journal. Cancellation commits event 3 and a stream
opened after cursor 1 reads exactly events 2 and 3, including the original
causation. The TypeScript fixture kills an owned process with a live stream,
requires an observable connection failure, reconnects, retries without
duplicating admission and replays the cancellation. Both harnesses check
interpreter ownership and reaping, including the Windows venv launcher.
A successful run also exercises graceful shutdown.

## Timing and idle RSS

Five fresh processes per candidate. OS caches are warm. Startup measures
parent launch to private readiness output. RSS samples the actual Python
server process 100 ms after readiness and excludes the venv launcher.
Reconnect measures a new Python client through the first replayed event.
Restart includes forced kill and reaping, a new ephemeral bind and replay
against the same journal. The benchmark checks one durable command and
its cancellation across reconnect/restart on every sample.

| Candidate | Median startup ms | Median idle RSS bytes | Median reconnect ms | Median kill/restart/replay ms |
|---|---:|---:|---:|---:|
| gRPC/Protobuf | 476.041 | 38,588,416 | 1.667 | 265.980 |
| HTTP/JSON + WebSocket | 718.946 | 50,012,160 | 1.603 | 478.897 |

The sub-millisecond median reconnect difference is within the spread of the
samples. The gRPC startup and RSS results favor the selected candidate in
this fixture. Initial startup creates the journal, while restart opens an
existing journal. Neither run establishes product limits, a disk-cold boot
time, end-to-end throughput or sustained load behavior.

## Adapter and security comparison

- gRPC generates the Python service base, stub and messages. Node generates
  declaration files and loads the same descriptor at runtime. Compile-time
  negatives verify identifier/cursor types and keep credentials outside
  domain messages. HTTP uses the same generated TypeScript shapes but its
  route mapping, JSON codec and stream frames are manual. TypeScript shape
  assertions do not validate arbitrary JSON at runtime.
- Both use a shared one-event application acknowledgment window with a 500 ms
  deadline. An unacknowledged event preserves the previous cursor and yields
  `BACKPRESSURE`. Successful resumed replay and healthy unary access verify
  recovery. Socket saturation, sustained load and production retention are
  outside this sample. [gRPC flow control](https://grpc.io/docs/guides/flow-control/)
- Both are plaintext numeric loopback fixtures using a fixed test bearer and
  one effect-free action. gRPC supports secure channels and transport
  credentials, while the HTTP option can use HTTPS/WSS. Pairing and production
  authorization require threat modeling. The Node adapter exercised here is
  intended for Electron main. Packaged renderer isolation, IPC ownership and
  embedded Node compatibility are Plan 01 gates.
  [gRPC authentication](https://grpc.io/docs/guides/auth/),
  [aiohttp TLS support](https://docs.aiohttp.org/en/stable/web_reference.html#aiohttp.web.TCPSite),
  [Electron security](https://www.electronjs.org/docs/latest/tutorial/security)

Proceed to independent review and the next Gate 00 decisions. The comparison
does not supply product, remote-security, storage-selection or physical
platform acceptance.
