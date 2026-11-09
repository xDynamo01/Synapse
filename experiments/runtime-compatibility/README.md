# Runtime compatibility experiment

**Historical evidence — 2026-11-09 PL-001/PL-006 amendment:** Python results are
retained; Node/pnpm/TypeScript selections are superseded and never product
dependencies. Rust/Python foundation revalidation is required before scaffolding.

Gate 00 Task 2. This is disposable compatibility evidence, not product runtime.
It implements no voice identity, model catalogue, transport, mission authority,
or persistence policy. No weights are downloaded or models instantiated.

Binding: [Decision Charter](../../docs/specs/2026-11-06-synapse-0.3-decision-charter.md)
`CR-001`, `CR-004`, `PL-001`, `PL-003`, `PL-004`, `QA-001`, `QA-002`, `QA-003`.
The decision and limits are in [ADR 0001](../../docs/adr/0001-core-runtime-and-toolchain.md).

## Exact tools

| Tool | Selected | Comparison |
|---|---|---|
| CPython, standard GIL | 3.14.10 | 3.13.18 |
| uv | 0.13.7 | Host 0.10.2 catalogue was stale |
| Node.js | 24.22.2 | Host 24.13.1 rejected |
| pnpm JavaScript distribution | 11.25.0 | Host standalone bundled Node 24.22.1 rejected |
| TypeScript | 7.0.2 | Exact experiment pin |

Install these tools from their primary sources listed in
[the evidence](../../docs/evidence/foundation/runtime-compatibility.md).
The JavaScript pnpm distribution must run under the selected Node executable;
a standalone pnpm with a different embedded Node is not equivalent. Installation
is local to this experiment. `.local/`, `.venv-*`, generated declarations,
compiled JavaScript, caches and dependencies are ignored by Git.

The current worktree has verified local tools. In PowerShell, from the repository
root, select them without changing the machine's installations:

```powershell
$experiment = (Resolve-Path experiments/runtime-compatibility).Path
$env:PATH = "$experiment/.local/bin;$experiment/.local/node-v24.22.2-win-x64;$experiment/.local/bootstrap/Scripts;$env:PATH"
$env:UV_CACHE_DIR = "$experiment/.local/uv-cache"
$env:UV_PYTHON_INSTALL_DIR = "$experiment/.local/python"
$env:UV_PYTHON_PREFERENCE = 'only-managed'
uv --version
node --version
pnpm --version
```

For a fresh checkout, provision uv 0.13.7, Node 24.22.2 and JS pnpm 11.25.0
on PATH, then use the following commands; the local-tool PATH snippet above is
only for the already-provisioned worktree. `uv python install 3.13.18` and
`uv python install 3.14.10` provision the exact interpreters. The bootstrap
receipts and file hashes are recorded in the evidence; no global upgrade is
required. Reusing existing unrelated Python environments is not supported.

## Reproduce the matrix

Keep both Python environments separate. From the repository root:

```powershell
$experiment = (Resolve-Path experiments/runtime-compatibility).Path
$env:UV_PROJECT_ENVIRONMENT = "$experiment/.venv-313"
uv run --locked --python 3.13 --project experiments/runtime-compatibility pytest -q
$env:UV_PROJECT_ENVIRONMENT = "$experiment/.venv-314"
uv run --locked --python 3.14 --project experiments/runtime-compatibility pytest -q
pnpm --dir experiments/runtime-compatibility install --frozen-lockfile
pnpm --dir experiments/runtime-compatibility test
```

The fixtures additionally reject Python patches other than 3.13.18/3.14.10 and
Node/pnpm versions other than the selected pins. Explicit `--python 3.13.18` and
`--python 3.14.10` are equivalent and avoid any ambiguity when multiple patches
are installed. Only the selected 3.14.10 path is required by subsequent Gate 00
tasks; 3.13 remains a comparison, not a second supported Core baseline.

Python checks seven library imports, native CPU API availability, an in-memory
async/schema/SQLite composition, cancellation, strict schema rejection and an
external-network guard. Numeric loopback is permitted only because Windows
asyncio implements its wakeup socketpair there. These Python-level guards are
test hygiene, not an OS security boundary. No HTTP, model or audio API is called.

TypeScript generates declarations from a local JSON Schema on every run,
compiles strict ESM, checks invalid generated types at compile time, cancels a
real child after its readiness signal, verifies that pipes close and the PID is
gone, and checks normal child exit. There is no mock process and no test-runner
forced-exit flag. Child watchdogs bound failure cases. This schema is a test
fixture; Task 3 owns the product transport/contract decision.

## Measure fresh-process startup and RSS

With each Python environment selected in turn:

```powershell
uv run --locked --python 3.14.10 --project experiments/runtime-compatibility python experiments/runtime-compatibility/tools/measure-runtime.py --node (Get-Command node).Source --output docs/evidence/foundation/runtime-python314.windows.json
```

For the comparison change the environment, interpreter and output suffix to
3.13.18/313. Each invocation runs five fresh Python and five fresh Node children,
measures parent launch to the readiness line, waits 100 ms and captures one RSS
snapshot, then requires clean exit. A 30-second watchdog bounds each probe.
Python RSS includes the seven imported candidates plus the psutil measurement
helper; Node imports only the ESM subprocess/event primitives. The two footprints
are not measurements of equivalent application work. Neither is a product budget.
OS disk caches are warm; this is process-cold, not reboot/disk-cold startup.

## Dependency policy

Exact direct versions are in `pyproject.toml`/`package.json`; all transitive
versions and artifact hashes are in `uv.lock`/`pnpm-lock.yaml`. Python source
builds and package install scripts are disabled. Use locked/frozen installs;
do not resolve latest versions during validation. Packages here are evidence
candidates only. Adding one to the future Core requires a scoped capability,
licence/distribution review, resource measurements with models where applicable,
and its own acceptance tests. Piper's declared GPL licence and voice/model
licences are not approved for product distribution by this experiment.

Read [the evidence](../../docs/evidence/foundation/runtime-compatibility.md) for
RED/GREEN results, rejected alternatives, source metadata and exact artifact
hashes. Linux/macOS execution is NOT RUN; the ADR names mandatory future CI
floors without claiming physical-platform validation.
