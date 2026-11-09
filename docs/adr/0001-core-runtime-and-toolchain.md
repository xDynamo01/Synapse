# ADR 0001: Core runtime and toolchain

Date: 2026-11-06

Status: **PARTIALLY SUPERSEDED — 2026-11-09 owner-approved PL-001/PL-006 amendment**.

Python compatibility/import evidence remains TESTED / PASS for the original
Windows experiment. Node/pnpm/TypeScript/client/Electron selections below are
historical and have no product authority or dependency approval. Python pins
remain evidence candidates subject to the actual Rust/Python composition.
Rust toolchain/native UI and the authority boundary are **NOT RUN / BLOCKED**;
follow [foundation revalidation](../superpowers/plans/2026-11-09-rust-python-foundation-revalidation.md).
The original decision text below is retained as experiment history.
Independent review and integration regression remain Gate 00 obligations.
No product capability is VALIDATED or OPERATIONAL by this ADR.

## Context and authority

The [binding Decision Charter](../specs/2026-11-06-synapse-0.3-decision-charter.md)
requires a clean-room, headless modular Core and independent clients. Task 1's
[host snapshot](../evidence/foundation/host-capabilities.windows.json) reports
Windows x64, 12 logical processors, about 15.9 GiB OS-visible RAM and an AMD GPU
whose dedicated memory is unverified. This experiment therefore uses CPU import
surfaces only, never allocates model weights and makes no GPU claim.

## Historical decision — Python evidence retained; client portion superseded

Use **standard-GIL CPython 3.14**, initially pinned to **3.14.10**, for the Core.
Use **Node.js 24**, initially **24.22.2**, and **pnpm 11**, initially **11.25.0**,
for client/tooling work. Pin **uv 0.13.7** for Python environments/locks and
**TypeScript 7.0.2** for the representative client experiment. The pnpm JavaScript
distribution must execute under that Node version; its standalone distribution
can embed a different runtime. The first Electron build must separately verify
Electron's embedded Node and renderer isolation; this decision does not prove
Electron compatibility or choose an Electron version.

Both tested Python minors pass the same composition. Python 3.14 retains a later
upstream maintenance horizon than 3.13, and the measured additional import
footprint is small on this host (about 2 MiB). Choosing 3.14 does not depend on
claiming it is faster: the comparison's startup median is slightly lower.
Upstream schedules: [3.14](https://peps.python.org/pep-0745/) and
[3.13](https://peps.python.org/pep-0719/), accessed 2026-11-06.

The minimal representative package set is:

| Capability under test | Exact candidate | Scope |
|---|---|---|
| Async scheduling/cancellation | anyio 4.16.0 | In-memory asyncio composition |
| Schema validation | pydantic 2.14.3 | Native pydantic-core plus strict negative checks |
| Local inference runtime | ctranslate2 4.8.5 | CPU capability query; no model |
| STT import surface | faster-whisper 1.2.1 | Imports shared CTranslate2/ONNX/AV/tokenizers stack |
| TTS import surface | piper-tts 1.8.0 | PiperVoice API; no voice selected |
| ONNX execution runtime | onnxruntime 1.31.1 | CPU provider available; no session/model |
| Async SQLite | aiosqlite 0.22.1 | Real in-memory SQLite through Python stdlib |
| Test/measurement | pytest 9.2.0, psutil 7.2.2 | Experiment-only helpers |
| Type generation | json-schema-to-typescript 16.0.0, @types/node 24.19.2 | Local schema to strict ESM test |

These are **evidence candidates, not automatically approved product
dependencies**. In particular CTranslate2 does not prove universal LLM/GGUF
support, and Piper does not satisfy the eventual original feminine multilingual
voice acceptance criteria merely by importing.

## Evidence and alternatives

[Reproduction, RED/GREEN results and measurements](../evidence/foundation/runtime-compatibility.md)
identify the test inputs, lock hashes and Windows binaries. Both Python versions
pass 12 tests; the selected Node/pnpm/TypeScript path passes 3 tests including
generated-type negatives, live child cancellation and clean exit.

| Alternative | Disposition and evidence |
|---|---|
| CPython 3.13.18 | Compatible (12 PASS); not the Core baseline because 3.14 also passes and has a later maintenance horizon. Retain as comparison/fallback evidence. |
| Host Python 3.14.3 / uv 0.10.2 catalogue | Superseded for this gate by current pinned maintenance tools; not used as selected-runtime evidence. |
| Host Node 24.13.1 | Negative version check fails; rejected for the selected patch. |
| Host standalone pnpm 11.25.0 | Engine check reveals embedded Node 24.22.1 and fails the 24.22.2 floor. Use verified JS pnpm 11.25.0 under selected Node. |
| llama-cpp-python 0.3.36 from PyPI | `uv pip install --dry-run --no-build` fails: no usable wheels. Rejected from this wheel-only representative experiment, not declared universally unsupported. No source patch or compilation workaround. |
| Free-threaded Python, Python 3.15, Node 26 | Not tested within the approved 3.13/3.14 and Node 24 experiment. No acceptance claim. |
| macOS Intel with this ONNX pin | No matching macOS x64 wheel in captured release metadata. Not an accepted CI target for this package set; macOS arm64 is the initial floor. |

## Package, platform and upgrade policy

- Keep all experiment and eventual runtime direct dependencies exact; commit
  transitive locks with hashes. Verification uses `uv --locked` and pnpm frozen
  installs. No arbitrary Git revisions, alternate indexes, local vendor patches,
  source-build fallback or unreviewed install scripts bypass a failing gate.
- Product dependencies are selected by later scoped capabilities, with licence,
  provenance, resource and end-to-end checks. The experiment does not grant
  product distribution approval for Piper GPL or any voice/model artefact.
- Required automatic CI floors for Plan 01 are Windows 11 x64 (a Windows Server
  2025 x64 runner may supply a separate CI lane), Ubuntu 24.04 x64/glibc, and
  macOS 14 or newer **arm64**. Run frozen installs, the same Python and TypeScript
  checks, generated-type negatives, cancellation and clean-exit tests on the
  selected versions. No physical Linux/macOS or cross-platform CI run occurred
  in Task 2: their current result is **NOT RUN**.
- The wheel metadata contains macOS 14 arm64 ONNX/AV wheels and Linux glibc 2.28
  wheels; the chosen CI floors meet those metadata floors. Availability is not
  execution proof. Windows native imports rely on the C++ runtime required by
  upstream; packaging must provision and test that dependency explicitly.
- Review upstream releases/advisories before every release and at least monthly.
  A patch upgrade changes pins, tool hashes and locks in one isolated change,
  reruns this matrix/negative tests/measurements plus all affected foundation
  checks on all required CI targets, and receives independent review. Failure
  holds the previous accepted pin; do not weaken assertions to accept it.
  Python minor or Node/pnpm major changes require a superseding ADR and the same
  two-candidate comparison. An unfixable required capability reopens this ADR.
- Rollback reverts this ADR and experiment pins/locks to the previous reviewed
  artifact. No deployed product or stored user data exists, so rollback cost is
  local environment regeneration plus rerunning the foundation checks.

## Decision Charter Compliance

| Binding decision | Evidence/obligation |
|---|---|
| CR-001 | All executable files are new under experiments/; no historical runtime imported. |
| CR-004 | Git ignores environments, caches and generated artifacts; public evidence has aggregate metrics and hashes, no personal paths, audio or secrets. |
| PL-001 | Headless Python composition and separate ESM child process; transport and Electron are later gates. |
| PL-003 | One local Python composition; no product services or distributed infrastructure. |
| PL-004 | Required three-platform CI floors; Windows TESTED, Linux/macOS NOT RUN, physical validation still required. |
| QA-001 | TESTED/PASS only; neither model operation nor product readiness claimed. |
| QA-002 | Missing-package RED, strict-schema/type negatives, real async/SQLite and child-process composition; independent review/integration regression pending at parent gate. |
| QA-003 | Exact artifact hashes, tools, commands, results and limitations in linked evidence; final tested commit in the execution report. |

Reviewed but not applicable: voice identity/translation, memory, missions,
Skills, MoM/Swarm and browser behavior are not implemented by this experiment.
Proposed deviations: None.
