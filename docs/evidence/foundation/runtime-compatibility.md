# Runtime compatibility evidence

**Historical scope after 2026-11-09 PL-001/PL-006:** Python measurements remain
evidence; Node/pnpm/TypeScript selections are superseded and confer no product
dependency approval. These receipts do not validate Rust/Python composition.

Captured: 2026-11-06. Status: **TESTED / PASS on Windows x64** for the selected
experiment. Linux/macOS: **NOT RUN**. Product validation/operation: **NOT RUN**.

Decision: [ADR 0001](../../adr/0001-core-runtime-and-toolchain.md).
Binding [charter](../../specs/2026-11-06-synapse-0.3-decision-charter.md) IDs:
`CR-001`, `CR-004`, `PL-001`, `PL-003`, `PL-004`, `QA-001`, `QA-002`, `QA-003`.

## Environment and artifact identity

Task 1 [host evidence](host-capabilities.windows.json) is the consumed baseline:
Windows 10.0.26200 x64 (Windows 11), 6 physical/12 logical CPUs,
17,064,919,040 RAM bytes, no validated GPU budget. CPU-only import experiments
ran in new, independent `.venv-313` and `.venv-314` environments.

Base commit: `f1c1676` (Task 1 collector negative-test addition). The committed
[artifact hash manifest](runtime-artifact.sha256.json) identifies exact test,
fixture, configuration and lock bytes; its scope excludes documents and generated
outputs. The Task 2 execution report records the final tested commit. This avoids
an impossible self-referential commit identifier in a committed document.

- [Exact Windows tool versions/executable SHA-256](runtime-toolchain.windows.json)
- [Primary release metadata, package artifact hashes and URLs](runtime-package-sources.json)
- [Python 3.13 / Node raw samples](runtime-python313.windows.json)
- [Python 3.14 / Node raw samples](runtime-python314.windows.json)
- Python [uv.lock](../../../experiments/runtime-compatibility/uv.lock): all transitive pins and SHA-256 hashes.
- TypeScript [pnpm-lock.yaml](../../../experiments/runtime-compatibility/pnpm-lock.yaml): all transitive pins and integrity hashes.

## RED, intermediate failure and GREEN

All commands were run from the repository root after selecting the local tools
as documented in the [experiment README](../../../experiments/runtime-compatibility/README.md).
The approved commands were executed with `UV_PROJECT_ENVIRONMENT` set to the
corresponding isolated environment. Only pytest was declared in the initial
Python manifest; no compatibility packages or TypeScript dependencies were
declared yet.

| Stage / command | Exact result |
|---|---|
| RED: `uv run --python 3.13 --project experiments/runtime-compatibility pytest -q` | Exit 1, 10 failed / 1 passed, 0.14 s. Seven `ModuleNotFoundError` import cases plus dependent composition failures. |
| RED: same command with `--python 3.14` | Exit 1, 10 failed / 1 passed, 0.13 s. Same missing package failures. |
| RED: `pnpm --dir experiments/runtime-compatibility test` | Exit 1, `ERR_MODULE_NOT_FOUND` for json-schema-to-typescript. |
| First dependency-complete Python runs | Each exit 1, 1 failed / 10 passed. Test-only network guard blocked the Windows asyncio loopback socketpair. Corrected the guard, not upstream packages. |
| GREEN: `uv run --locked --python 3.13 --project experiments/runtime-compatibility pytest -q` | Exit 0, 12 passed, 0.54 s (3.13.18). |
| GREEN: same command with `--python 3.14` | Exit 0, 12 passed, 0.48 s (3.14.10). |
| Frozen JS pnpm install | Exit 0, lock unchanged; install scripts disabled. |
| GREEN: `pnpm --dir experiments/runtime-compatibility test` | Exit 0, 3 passed; strict type generation/compilation succeeded, live cancellation/reaping and natural exit succeeded. |

The final selected-version rerun occurs after the ADR is written and again on
the committed artifact; its exact results/commit are in the local execution
report. The public hash manifest permits validation independently of that report.
Test files contain the Python patch/GIL gate and an explicit Node/pnpm patch gate.

Additional negative evidence:

```text
node experiments/runtime-compatibility/tools/check-toolchain.mjs
exit 1: actual Node 24.13.1; expected 24.22.2

pnpm --dir experiments/runtime-compatibility install --frozen-lockfile
(host standalone pnpm)
exit 1: ERR_PNPM_UNSUPPORTED_ENGINE; expected >=24.22.2 <25; got v24.22.1

uv pip install --dry-run --no-build --python <isolated-3.14.10-python> llama-cpp-python==0.3.36
exit 1: No solution found; llama-cpp-python==0.3.36 has no usable wheels
```

The last check is a read-only resolver rejection. No source build, local patch,
model constructor, voice download or inference was used to obtain a pass.

## Cold-start and RSS

Five new child processes per candidate, imports completed before readiness,
one working-set/RSS sample 100 ms later, clean exit. Parent monotonic timing
measures launch to the readiness line. OS/package caches remain warm. This is
not a reboot/disk-cold benchmark, peak-memory test or loaded-model budget.

| Candidate | Median ready time | Median RSS bytes | Maximum sampled RSS bytes |
|---|---:|---:|---:|
| Python 3.13.18, seven candidate imports + measurement helper | 594.128 ms | 80,609,280 | 80,781,312 |
| Python 3.14.10, same imports | 620.887 ms | 82,702,336 | 82,833,408 |
| Node 24.22.2, ESM subprocess/event primitives, alongside 3.13 batch | 49.030 ms | 36,380,672 | 36,401,152 |
| Node 24.22.2, same primitives, alongside 3.14 batch | 49.983 ms | 36,368,384 | 36,392,960 |

The Node probe does less work than the Python probe; compare each only against
future runs of the same fixture. The measured 3.14 overhead is not a performance
claim or a release budget. No models, real audio devices, GPU kernels, server or
Electron process were exercised.

## Primary sources and exact pins

All sources accessed **2026-11-06**. Versioned registry metadata and candidate
artifact hashes are preserved in `runtime-package-sources.json`; lockfiles hold
the full resolved graphs. Upstream metadata is provenance/compatibility evidence,
not a guarantee of runtime operation or a security audit.

| Selection | Primary source | Reason |
|---|---|---|
| CPython 3.14.10 / 3.13.18 | [3.14.10 release](https://www.python.org/downloads/release/python-31410/), [3.13.18 release](https://www.python.org/downloads/release/python-31318/) | Current pinned maintenance releases for the required comparison. |
| uv 0.13.7 | [Versioned PyPI metadata](https://pypi.org/pypi/uv/0.13.7/json), [managed Python documentation](https://docs.astral.sh/uv/concepts/python-versions/) | Exact isolated environment manager and managed interpreters. |
| Node 24.22.2 | [Release](https://nodejs.org/en/blog/release/v24.22.2), [release schedule](https://github.com/nodejs/Release), [archive checksums](https://nodejs.org/dist/v24.22.2/SHASUMS256.txt) | Supported Node 24 line, explicit patch and verified Windows archive. |
| pnpm 11.25.0 | [Versioned registry metadata](https://registry.npmjs.org/pnpm/11.25.0), [pnpm 11 requirements](https://pnpm.io/blog/releases/11.0) | Exact installed major, JavaScript distribution uses selected Node. |
| anyio 4.16.0 | [Versioned metadata](https://pypi.org/pypi/anyio/4.16.0/json) | Async library with portable asyncio path. |
| pydantic 2.14.3 | [Versioned metadata](https://pypi.org/pypi/pydantic/2.14.3/json) | Schema engine exercises a native Rust extension transitively. |
| ctranslate2 4.8.5 | [Installation matrix](https://opennmt.net/CTranslate2/installation.html), [versioned metadata](https://pypi.org/pypi/ctranslate2/4.8.5/json) | Native CPU inference dependency shared with STT; wheels for required Python minors. |
| faster-whisper 1.2.1 | [Upstream](https://github.com/SYSTRAN/faster-whisper), [versioned metadata](https://pypi.org/pypi/faster-whisper/1.2.1/json) | Representative STT import surface without Torch/model downloads. |
| piper-tts 1.8.0 | [Upstream](https://github.com/OHF-Voice/piper1-gpl), [versioned metadata](https://pypi.org/pypi/piper-tts/1.8.0/json) | Representative local ONNX TTS import; GPL declared, not product-approved. |
| onnxruntime 1.31.1 | [Install requirements](https://onnxruntime.ai/docs/install/), [versioned metadata](https://pypi.org/pypi/onnxruntime/1.31.1/json) | Shared CPU runtime; captured macOS arm64 wheel floor is 14.0. |
| aiosqlite 0.22.1 | [Versioned metadata](https://pypi.org/pypi/aiosqlite/0.22.1/json) | Async wrapper around stdlib SQLite; no separate database server. |
| pytest 9.2.0 / psutil 7.2.2 | [pytest metadata](https://pypi.org/pypi/pytest/9.2.0/json), [psutil metadata](https://pypi.org/pypi/psutil/7.2.2/json) | Test runner and cross-platform RSS helper. |
| TypeScript 7.0.2 / @types/node 24.19.2 | [TypeScript metadata](https://registry.npmjs.org/typescript/7.0.2), [Node types metadata](https://registry.npmjs.org/@types/node/24.19.2) | Compiler plus types matching the Node major. |
| json-schema-to-typescript 16.0.0 | [Upstream](https://github.com/bcherny/json-schema-to-typescript), [metadata](https://registry.npmjs.org/json-schema-to-typescript/16.0.0) | Actual generation from a local schema, without choosing the transport. |
| Rejected llama-cpp-python 0.3.36 | [Versioned metadata](https://pypi.org/pypi/llama-cpp-python/0.3.36/json) | PyPI supplies only a source archive; resolver rejection reproduced under the wheel-only policy. |

## Limits and integration decision

The selected experiment passes on the named Windows host. Proceed to independent
review and subsequent Gate 00 experiments using ADR 0001. This is not permission
to scaffold the product or to mark all of Gate 00 passed. Linux/macOS CI,
physical devices, full model/voice behavior, Electron packaging, security
boundaries, persistence recovery and post-integration regression remain their
respective gates. No source files from earlier Synapse versions were used.
