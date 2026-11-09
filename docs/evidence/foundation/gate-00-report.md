# Gate 00 — Clean-room foundation decision report

Prepared 2026-11-09; approved decision filenames retain 2026-11-06.

Gate result: **PASS** — selected Windows foundation experiments and document
contracts only. Capability status: **TESTED**. This report is consumed together
with exact-HEAD clean-clone receipts; without those receipts the aggregate
checker fails. Final independent whole-branch review and any later integration
regression remain separate obligations.

Scaffolding: **AUTHORIZED within Plan 01 scope**, after independent review of
this handoff. No product implementation, shared merge, push, publication,
credential boundary or additional risk acceptance occurs in Task 6.

## Decisions

| Task | Exact reviewed commit | Accepted output |
|---|---|---|
| 1 | `f1c1676225d66e8d35ed167e63c5811b9d7a1d06` | Redacted capability schema/collector and negative/fallback fixtures |
| 2 | `54ab41cd1c7aad9820798296119227e36ceb86f5` | ADR 0001: CPython 3.14.10 standard GIL, uv 0.13.7, Node 24.22.2, JS pnpm 11.25.0, TypeScript 7.0.2 |
| 3 | `52cb737a2179ad4a3387eda4fcc245bf8e1420d7` | ADR 0002: gRPC over HTTP/2 with Protocol Buffers, `synapse.foundation.v1`, contract `1.0` |
| 4 | `009fe94f71b711af3a4cb688d9da6b8cbdfae538` | ADR 0003: SQLite WAL, per-connection FULL sync, linked SQLite >=3.51.3 |
| 5 | `e3933f2558116ef6b07f3f8bb926431109d49dd1` | Foundation threat model, ten authority invariants, private-context consumer requirements and document gate |

The exact synthesis commit is identified by `git rev-parse HEAD` in each local
receipt, avoiding a self-referential commit in this committed document. The
execution report retains clone identity, commands, actual output, date and
commit. `test-gate-00.ps1` requires matching HEAD, clean state, all seven selected
check receipts and SHA-256-bound output, accepted ADRs, evidence and no product
roots. Receipts are local evidence, not cryptographic attestation of a hostile
runner. The aggregate does not execute or replace the underlying tests.

CPython 3.13.18 passed but 3.14 has the later support horizon at small measured
import overhead. Stale host Python/uv catalogues, host Node 24.13.1 and standalone
pnpm's embedded Node 24.22.1 do not satisfy the selected pins. Wheel-only
llama-cpp-python 0.3.36 resolution failed; no source workaround was accepted.
HTTP/JSON+WebSocket passed the comparison but gRPC keeps one schema/service and
had lower measured startup/RSS. SQLite rollback journal was unnecessary after
WAL met the accepted crash/read/restore experiment. Candidate inference/audio
packages and Piper/voice licences are not product-distribution approvals.

## Measurements and budgets

These are the original decision samples, reproduced in their linked sources;
they are not release SLAs. Fresh aggregate execution records new measurements
locally without overwriting the historical committed samples.

| Measurement | Recorded decision evidence |
|---|---|
| Host | Windows 11 x64 build 26200; 6 physical/12 logical CPUs; 17,064,919,040 OS-visible RAM bytes; dedicated GPU memory unverified, CPU fallback |
| Runtime imports, five process-cold/warm-cache runs | Python 3.14 median ready 620.887 ms / RSS 82,702,336 bytes; 3.13 median 594.128 ms / 80,609,280 bytes |
| Node minimal ESM probe | Median ready 49.983 ms / RSS 36,368,384 bytes alongside selected Python batch; does less work than Python |
| gRPC selected transport | Median ready 491.210 ms, RSS 38,498,304 bytes, reconnect 1.648 ms, kill/restart/replay 255.872 ms |
| HTTP/WS comparison | Median ready 699.286 ms, RSS 50,012,160 bytes, reconnect 1.792 ms, kill/restart/replay 469.316 ms |
| Persistence crash budget | 120 s loop, 128 MiB child RSS, 8 MiB active file family; measured 31.165 s, 26,173,440 RSS bytes, 2,081,040 file bytes |
| Durability | 120 confirmed writer kills: 60 pre-commit invisible, 60 acknowledged retained, zero loss/partial visibility, 120 integrity passes; 256-version backup/restore |

Sources: `runtime-compatibility.md`, `transport-spike.md`, `persistence-spike.md`
and their raw JSON/locks/hashes in this directory. Five small transport samples
do not establish sustained throughput; the sub-ms reconnect difference is within
sample spread. No model memory allocation or GPU budget was inferred.

## Reproduction

Start with a fresh local clone of the committed Gate 00 artifact, not an archive
export or a copied working directory. Provision the verified pinned tools per
`experiments/runtime-compatibility/README.md`; copying only the verified tool
distributions is acceptable, but never copy experiment venvs/site-packages or
generated clients. Install from committed locks into fresh environments. Use
repository-local caches/temp, no machine-wide tool upgrade and no model weights.

Run these from the clone root under the selected uv/Node/JS-pnpm tools. Set
`UV_PROJECT_ENVIRONMENT` separately for each Python project as documented in
its README; use `TRANSPORT=grpc` for selected transport commands.

```powershell
pwsh -NoProfile -File tools/foundation/test-host-capabilities.ps1
uv run --locked --no-build --python 3.14.10 --project experiments/runtime-compatibility pytest -q -p no:cacheprovider
pnpm --dir experiments/runtime-compatibility install --frozen-lockfile --ignore-scripts
pnpm --dir experiments/runtime-compatibility test
uv sync --locked --no-build --python 3.14.10 --project experiments/transport
uv run --locked --python 3.14.10 --project experiments/transport python experiments/transport/tools/generate-python.py
pnpm --dir experiments/transport install --frozen-lockfile --ignore-scripts
$env:TRANSPORT = 'grpc'
uv run --locked --python 3.14.10 --project experiments/transport pytest experiments/transport/tests -q -ra -p no:cacheprovider
pnpm --dir experiments/transport test
uv run --locked --no-build --python 3.14.10 --project experiments/persistence python -u -B -m pytest -q -s -p no:cacheprovider
pwsh -NoProfile -File tools/foundation/test-security-docs.ps1
pwsh -NoProfile -File tools/foundation/test-gate-00.ps1 -ReceiptPath .local/gate-00/receipts.json
git status --porcelain
```

Also rerun selected `measure-runtime.py --node <selected-node> --output <local-json>`
and transport `tools/measure.py --candidate grpc --output <local-json>` per their
READMEs, retaining new samples locally. Each receipt contains `name`, `command`,
`started_utc`, `exit_code`, log filename and its lowercase SHA-256. Top-level
receipt fields are `commit`, `initial_clean: true`, `clone: fresh-local-clone`
and `checks`. Required names: `host`, `runtime-python`, `runtime-typescript`,
`transport-python`, `transport-typescript`, `persistence`, `security`.
The aggregate verifies actual successful-suite output (12/3, 3/2 and 10 tests,
including all 120 crash iterations), not just an editable PASS label.

## Limitations

- Linux/macOS selected suite execution and CI: **NOT RUN** in Gate 00.
  Plan 01 must run Windows 11 x64 (or separately labelled Server 2025 CI),
  Ubuntu 24.04 x64/glibc and macOS 14+ arm64; availability metadata is not proof.
- Packaged Electron, embedded Node, renderer/main IPC and product client
  identity/credential issuance: **NOT RUN / BLOCKED for product integration**.
  Plan 01 owns desktop pinning and synthetic packaged denial/round-trip proof;
  Plan 02 product identity/lifecycle cannot bypass E-02.
- Remote TLS, discovery, pairing, credentials, revocation and migration:
  **NOT RUN**; remote listening remains disabled, E-04 mandatory.
- At-rest/key lifecycle and personal-data use: **BLOCKED** pending E-02.
  Experiment plaintext SQLite and public bearer are synthetic-only fixtures.
- Tool/browser/Skill/model/voice enforcement: **NOT RUN**, E-01/E-03/E-05
  precede sensitive implementations; imports do not prove inference or voice.
- Physical Linux/macOS audio, secure storage, models, installer/update and
  recovery: **NOT RUN**, never VALIDATED/OPERATIONAL from CI alone.
- Hardware power loss, commit-internal timing, controller failures, backup
  power-loss publication, blob durability and product-scale datasets: **NOT RUN**.
- R-01–R-04 remain **NOT ACCEPTED**. No authority expansion or data egress risk
  is accepted. All downstream plans retain AI-01–AI-10 and PC-01–PC-04;
  authorized private local project context must not be blanket-redacted.
- Task 3 deferred P3: native-termination wait uses outer node:test timeout and
  can skip fixture finally when no event arrives; Core is already reaped.
  Track fixture hardening in whole-branch review; no claim of a clean global
  product suite or solved production cleanup follows from the scoped gate.

## Plan 01 handoff

Specification: `docs/specs/subprojects/01-repository-and-skeleton.md`.
Detailed plan: `docs/superpowers/plans/2026-11-06-repository-and-cross-platform-skeleton.md`.
The handoff selects exact foundation pins and semantics and leaves Electron/React
pin selection as an explicit first-task provenance/security gate. Plan 01 builds
an inert bootstrap and separate non-release synthetic packaged test, not the
Plan 02 product service, owner authentication or durable journal. No root product
directories exist in Gate 00. Missing downstream evidence blocks its own gate;
it does not invalidate the narrower Windows foundation result or waive a control.

## Decision Charter Compliance

**Charter:** `docs/specs/2026-11-06-synapse-0.3-decision-charter.md`

**Binding decisions:** CR-001, CR-002, CR-003, CR-004, MI-003, MI-004,
SE-005, SE-006, PL-001, PL-002, PL-003, PL-004, QA-001, QA-002, QA-003.

| Decision | Implementation obligation | Test/evidence owner |
|---|---|---|
| CR-001–CR-004 | New experiments only, preserve history, isolated branch and redacted evidence | Host gate, aggregate root/clean check and exact clone |
| MI-003, MI-004 | Experiments confer no product authority or preflight expansion | Task 5 threat model; Plan 01/02 refusal requirements |
| SE-005, SE-006 | Client-only CLI, formal security prerequisites | Security document validator and downstream E-01–E-05 gates |
| PL-001–PL-004 | Headless modular foundation, versioned transport, future remote gate and truthful platform scope | Selected runtime/gRPC/persistence suites; Plan 01 platform gates |
| QA-001–QA-003 | RED/GREEN, negatives, exact artifact, clean-clone real fixtures, scoped PASS and retained limits | Aggregate ten negative cases and local execution report; independent review |

**Reviewed but not applicable:** PX-001–PX-006, VO-001–VO-006, ME-001–ME-005,
MI-001/MI-002/MI-005–MI-007, SK-001–SK-004, MM-001/MM-002, SW-001–SW-004,
SE-001–SE-004 and PL-005 receive no product runtime implementation in Gate 00.
Their requirements are retained by the threat model/architecture and consuming
plans; no audio, memory, missions, Skills, cognition, Swarm or browser is claimed.

**Proposed deviations:** None.
