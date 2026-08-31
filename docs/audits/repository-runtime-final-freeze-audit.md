# Repository Runtime — final freeze audit

Date: 2026-08-09
Decision: **IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN**
Global backend: **NOT READY**

This report is the evidence companion to
`docs/architecture/repository-runtime.md`. The freeze covers the local bounded
context, its reference-only integration, opt-in Composition Root, SQLite V1
persistence and local Git/filesystem adapter. It does not activate the runtime in
global bootstrap or authorize staging, commit, push or remote mutation.

## Production inventory and public surface

All **25 production modules** have a concrete producer/consumer role. No provisional
model, deprecated alias, mutable global registry, test double or generic execution
facade remains.

| Package | Modules | Public exports | Responsibility | Freeze |
| --- | ---: | ---: | --- | --- |
| `repository_runtime` | 21 | 255 | immutable facts, policies, services, consumer-owned ports, SQLite V1 and local adapter | frozen |
| `repository_runtime_integrations` | 2 | 25 | Coding Sessions reference/lease/intent translation | frozen |
| `repository_runtime_composition` | 2 | 11 | typed opt-in construction, health and close lifecycle | frozen |

The domain facade is intentionally a typed SDK. Its public groups and consumers
are:

| Export group | Producer | Consumer/justification | Decision |
| --- | --- | --- | --- |
| identities, paths, platform and state enums | domain constructors | every factual artifact and adapter binding | freeze public |
| observation/classification/snapshot facts | observation services and adapter | planning, verification and callers | freeze public |
| changes, planning and authorization correspondence | pure services | explicit application requests | freeze public |
| restore/application/verification/recovery artifacts | lifecycle services | callers, persistence and E2E orchestration | freeze public |
| persistence records, ports and SQLite implementations | persistence boundary | Composition Root and exact replay clients | freeze public |
| local adapter config/materials/capabilities | adapter | Composition Root and explicit local clients | freeze public |
| typed errors and diagnostics | all named authorities | fail-closed caller handling | freeze public |
| canonical helpers and V1 constants | canonical/persistence boundary | artifact identity and migration validation | freeze public |
| Coding Sessions contracts | integration adapter | future session context by explicit reference | freeze public |
| runtime config/health/builder/handle | Composition Root | opt-in local construction only | freeze public |

The executable freeze gate fingerprints the sorted exports. Frozen counts and
fingerprints are:

| Facade | Count | SHA-256 of sorted newline-delimited exports |
| --- | ---: | --- |
| domain | 255 | `370c4664ad3ce9c166c75049e40c80414dc482467c45043602e2bd4f2a5dc4dc` |
| integrations | 25 | `f6374e4d002e7c643bc8f531d3f4a5952cdd8e3227de073fdea4586e520e21f5` |
| composition | 11 | `ab7c029d535c5795e06df2fcea626d4f4119e6b65afffc7604cb8a9886fe2c3b` |

## Frozen contracts and authority

- Canonical format: `repository-json-v1`.
- Record format: `repository-record-v1`.
- Schema: V1.
- Migration: V1, checksum
  `sha256:88f94a662d93d0a0dc48724d75260e0e56ce0a348c8a264f83194216325f7c84`.
- Identity semantics bind repository, checkout and optional worktree exactly;
  occurrence metadata never changes semantic identity.
- Observation, mutation plan, authorization fact, application, verification and
  recovery are separate authorities and artifacts.
- Project Governance owns project identity/context. Governance/Approvals owns
  authorization. Coding Sessions owns session intent and coordination. Repository
  Runtime owns technical repository facts and operations. Deployment owns
  publication. Commit never implies push.

## Lifecycle and persistence

The frozen lifecycle is observation → classification → snapshot → change set →
plan → authorization correspondence → restore point → application → verification
and reconciliation → explicitly requested recovery → post-recovery verification.
No arrow is inferred from success in the preceding stage.

Persistence is append-only and versioned. Identity plus divergent payload fails
closed; idempotent retries do not duplicate records; causal revisions, checksum,
lineage gaps, unknown versions and corruption remain explicit. Exact reads never
mean latest/current. Replay and restart preserve partial observation, unauthorised
plans, partial application, divergent verification, recovery-required, partial
recovery, rollback-failed and manual-intervention states without inventing a
transition.

## Final adapter capability matrix

| Feature | Frozen factual state |
| --- | --- |
| Windows, worktree/common-dir, detached/unborn HEAD, status/index observation | supported |
| submodule and nested repository traversal | degraded; boundary detected and rejected |
| sparse checkout | supported when absent; degraded when active |
| LFS | unavailable when absent; degraded when configured |
| hooks and filters | supported when absent; degraded when detected |
| encoding | degraded; Git text uses explicit decoding and file content remains bytes |
| symlink/junction/reparse containment | supported fail-closed on Windows |
| exact-plan filesystem mutation | degraded; closed operations and factual verification required |
| recovery | degraded; verified restore coverage only |
| metadata/classification and HEAD/branch/index recovery | unsupported |
| staging, commit, push and remote mutation | unsupported and absent |

`degraded`, `unsupported` and `unavailable` are first-class capability states and
are never promoted to `supported` by health or Composition Root wiring.

## Integration, health and limitations

The only governed edges are composition → domain, composition → integrations and
integrations → domain. None of the three contexts belongs to an SCC. The pure
domain does not import integration or composition, and global bootstrap imports
none of them.

Coding Sessions integration is optional and reference-only. A checkout/worktree
lease coordinates sessions but is not authorization or filesystem security.
Health reports the factual schema/migration, Git availability/version, platform,
adapter state and optional integration; it does not claim unsupported behavior.

Operational limitations are deliberate: no automatic repository, branch,
worktree or current/latest-session selection; no staging, commit, push, fetch,
pull, merge, rebase, branch creation, API, CLI, worker, background service or
Deployment integration. Future Coding Sessions and Deployment work must consume
the frozen contracts explicitly and cannot broaden authority implicitly.

## Freeze gate

`tests/architecture/test_repository_runtime_freeze.py` protects:

- the exact 25-module inventory and 291 public exports;
- canonical, record, schema and migration V1 constants;
- capability states/features and the prohibited operation surface;
- the three allowed integration edges and absence from SCCs.

Any change to these baselines is a frozen-contract change and requires explicit
architectural authorization, updated evidence and a new freeze decision.

## Quality baseline

The authoritative Slice 18 execution records:

| Gate | Frozen baseline/result |
| --- | --- |
| freeze + Repository Runtime boundary | 13 passed |
| Repository Runtime, including E2E/restart/failure paths | 253 passed |
| architecture | 183 passed |
| global regression, 12 deterministic partitions | 3236 passed, 4 skipped, 4 subtests passed |
| Ruff | clean |
| Mypy local | 25 source files, zero errors |
| Mypy global | 655 source files, zero errors |
| runtime import graph | 76 contexts, 270 edges, 1 pre-existing SCC; no Repository Runtime context in it |
| source import graph | 80 contexts, 305 edges, 2 pre-existing SCCs; no Repository Runtime context in them |
| diff integrity | `git diff --check` clean |

These results are the final local bounded-context baseline. The pre-existing SCCs
and four globally skipped tests are not Repository Runtime exemptions. Historical
results do not substitute a future execution after a proposed frozen-contract
change.
