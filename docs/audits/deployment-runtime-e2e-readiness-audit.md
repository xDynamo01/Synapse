# Deployment Runtime Slice 14 — E2E readiness audit

Decision: **APPROVED FOR A SEPARATE FINAL-FREEZE SLICE**.

This audit reconciles Deployment Runtime Slices 2–13 through controlled local
journeys, failure/restart evidence and current repository gates. It does not freeze
the bounded context, add global composition or activate Deployment in bootstrap.

## Current capability baseline

| Capability | Current result | Boundary preserved |
| --- | --- | --- |
| Local preparation | available | prepared revision is not active revision |
| Local apply | available | apply receipt is not verification |
| Independent observation | available | observation is read-only and is not verification |
| Independent verification | available | only the verifier creates verification evidence |
| Local rollback preparation/apply | available | previous revision is not implicit eligibility |
| Rollback observation/verification | available | rollback receipt is not rollback verification |
| Durable journal/replay | available | replay does not redeploy, rollback or reauthorize |
| Deployment fencing/idempotency | available | fencing, authorization and idempotency remain distinct |
| Sandbox handoff | available for the controlled Windows V1 path | Deployment fencing is not Sandbox fencing |
| Global bootstrap | absent | local capability does not imply global activation |

## Controlled journeys

`tests/test_deployment_e2e_readiness.py` proves two integrated journeys:

1. local preparation and apply followed by a fresh target observation and an
   independent positive verification;
2. explicit rollback from the active revision to a separately eligible revision,
   followed by a fresh observation and independent rollback verification.

Both journeys retain distinct receipt, observation and verification identities.
The active pointer changes only through the fenced local mutation path. A successful
Sandbox start never becomes verification evidence.

The supporting focused suite covers authorization denial/invalidation, stale fencing,
eligibility/correspondence mismatches, idempotency contradiction, preparation residue,
partial and unknown effects, observer unavailability, target mutation, restart during
apply/rollback, corruption and passive replay. Unknown effects remain reconciliation
requirements and are not automatically retried.

## Authority and architecture

- `deployment` remains pure and provider-neutral.
- `deployment_adapters` points inward and owns local/SQLite mechanics only.
- `deployment_integrations` owns the approved consumer edges to Decisions,
  Approvals, Sandbox and the Windows driver.
- Repository Runtime retains Repository/Git mutation authority.
- Coding Sessions, Deployment and Sandbox fencing remain separate.
- Private Evals evidence cannot authorize Deployment.
- No production bootstrap module imports Deployment.

The current governed graphs reproduce 298 runtime edges and 333 source edges, with
Deployment outside every SCC. These are results executed for this audit, not targets
to preserve by convenience.

## Current verification

| Gate | Result |
| --- | --- |
| dedicated Slice 14 E2E | 2 passed |
| Deployment focused + boundary selection | 235 passed |
| architecture suite | 253 passed |
| Ruff, repository-wide | passed |
| Mypy, Deployment source | 28 source files, zero issues |
| authoritative Mypy `backend/synapse` | 758 source files, zero issues |
| global regression, four deterministic partitions | 4,349 passed, 5 skipped, 4 subtests passed |
| global file coverage | 329 enumerated/assigned/unique; zero missing, duplicate or extra |
| Deployment graph guard | passed; 298 runtime / 333 source edges |

The direct Mypy invocation on the new test file was **failed** by nine existing
protocol incompatibilities in imported `FakeApi` usages from
`tests/test_windows_process_driver.py` and `tests/test_deployment_local_apply.py`.
The authoritative source gates above passed. No suppression, test weakening or product
change was made to hide that test-only baseline.

The five global skips are platform capability skips already represented by their tests;
they are not counted as passes and did not affect the Deployment journeys.

## Readiness decision

No product defect, authority leak, reverse dependency, bootstrap activation or
unresolved reconciliation blocker was found. Deployment Runtime is ready for one
separate final audit/freeze slice that freezes only the current V1 surface and records
its deliberate limitations.

This decision does not make Deployment frozen and does not make the backend READY.
