# Client/Core transport spike

Gate 00 Task 3 compares a Python gRPC service with HTTP unary calls and a
WebSocket event stream. Both use the same effect-free lifecycle and a disposable
SQLite journal to exercise process-death recovery. The contract, platform gates
and decision are in [ADR 0002](../../docs/adr/0002-client-core-transport.md).

## Reproduce

Provision CPython 3.14.10 with the standard GIL, uv 0.13.7, Node 24.22.2 and
the JavaScript distribution of pnpm 11.25.0 running under that Node. See
[ADR 0001](../../docs/adr/0001-core-runtime-and-toolchain.md) and the
[tool selection snippet](../runtime-compatibility/README.md#exact-tools) for
the verified Windows setup. The experiment uses its own `.venv`.

From the repository root in PowerShell:

```powershell
$t = (Resolve-Path experiments/transport).Path
$env:UV_PROJECT_ENVIRONMENT = "$t/.venv"
uv sync --locked --no-build --python 3.14.10 --project experiments/transport
uv run --locked --python 3.14.10 --project experiments/transport python experiments/transport/tools/generate-python.py
pnpm --dir experiments/transport install --frozen-lockfile
uv run --locked --python 3.14.10 --project experiments/transport pytest experiments/transport/tests -q -ra --basetemp "$t/.local/pytest-matrix"
pnpm --dir experiments/transport test
uv run --locked --python 3.14.10 --project experiments/transport python experiments/transport/tools/measure.py --output "$t/.local/measurements.json"
```

Set `$env:TRANSPORT = 'grpc'` before the Python and TypeScript test commands
to select the ADR path. Remove the variable to run both. The measurement
command takes `--candidate grpc` for the selected path.

The server reports readiness on a private child stdout pipe and stops when
the harness closes stdin. The harnesses validate ownership of the running
interpreter before fault injection. On Windows the venv launcher and the
listener can have distinct PIDs. The journal, virtual environments, generated
bindings and compiled JavaScript are ignored. Use a test journal under
`.local/` if invoking the server directly. The port is assigned by the OS on
`127.0.0.1`. The fixed bearer is public fixture data and grants access only to
this synthetic journal. Node tests run the prospective main-process adapter
under standalone Node. The actual Electron isolation test belongs to Plan 01.

The test matrices, raw results and upstream package metadata are recorded in
[transport spike evidence](../../docs/evidence/foundation/transport-spike.md).
