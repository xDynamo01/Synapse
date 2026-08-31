# Deployment Runtime — final freeze audit

Decision: **IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN**.

Scope: Deployment Runtime Slices 2–15. This decision freezes the current local V1
domain, adapters and consumer-owned integrations. It does not activate Deployment in
global bootstrap, create a production deployment provider or make the backend READY.

## Frozen inventory

| Package | Frozen modules | Frozen public exports |
| --- | ---: | ---: |
| `synapse.deployment` | 15 | 261 |
| `synapse.deployment_adapters` | 6 | 13 |
| `synapse.deployment_integrations` | 7 | 25 |

`tests/architecture/test_deployment_freeze.py` freezes the exact module sets and
sorted public-export fingerprints. New public surface, modules or removals require an
intentional unfreeze review rather than an incidental baseline update.

## Frozen V1 contracts

- canonical format: `deployment-json-v1`;
- journal record format: `deployment-journal-json-v1`;
- journal schema version: `1`;
- journal migration: `deployment-journal-v1` with its current checksum;
- fencing/idempotency migration: `deployment-authority-v1` with its current checksum;
- fencing authority: `deployment-fencing-authority-v1`;
- fencing token: `deployment-fencing-token-v1`;
- idempotency record: `deployment-idempotency-record-v1`.

Both SQLite histories are append-only and checksum-protected. Schema or record-format
changes require a versioned migration; frozen migrations are not edited in place.

## Frozen lifecycle and authority boundaries

The local Deployment V1 lifecycle supports explicit preparation, apply, observation
and independent verification. Rollback independently prepares an exact intended
revision, applies it, observes current state and verifies it.

- `DeploymentIntent != DeploymentAuthorization`.
- `ArtifactEligible != DeploymentAuthorized`.
- `EvalPass != DeploymentAuthorization`.
- `FencingToken != DeploymentAuthorization`.
- `Fencing != Idempotency`.
- `ApplyReceipt != DeploymentVerification`.
- `Observation != Verification`.
- `RollbackApplied != RollbackVerified`.
- `CodingSessionsFencing != DeploymentFencing`.
- `DeploymentFencing != SandboxFencing`.
- `Replay != Redeploy`, `Replay != Rollback`, `Replay != Reauthorization`.

Deployment owns its lifecycle facts, journal and generation/fencing authority.
Decisions/Approvals retain authorization authority; Sandbox retains execution and
containment authority; Repository Runtime retains Repository/Git mutation authority;
Private Evals emits evidence only.

## Frozen dependency and activation baseline

The only governed Deployment edges are:

- `deployment_adapters → deployment`;
- `deployment_integrations → deployment`;
- `deployment_integrations → approvals`;
- `deployment_integrations → decisions`;
- `deployment_integrations → sandbox`;
- `deployment_integrations → sandbox_drivers`.

Current graphs contain 298 runtime edges and 333 source edges. Deployment is outside
every SCC. These counts are frozen with the edge set and must not be changed merely to
preserve a historical number.

Global bootstrap imports no Deployment package. The local V1 path remains opt-in and
test-controlled. Freeze does not transfer composition or activation authority.

## Operational guarantees and deliberate limitations

Available:

- local single-host service/application preparation;
- fenced local apply through the controlled Windows Sandbox driver path;
- factual receipts and atomic active-revision pointer;
- independent local observation and verification;
- explicit local rollback through independent verification;
- append-only restart/replay and reconciliation facts.

Not provided by this frozen bounded context:

- global Composition Root or bootstrap activation;
- remote, cluster, container or cloud deployment provider;
- rollout-stage execution, promotion execution or automatic canary control;
- Repository checkout/branch/stage/commit/push;
- automatic retry of partial or unknown external effects;
- automatic artifact eligibility, authorization or eval promotion;
- Backend READY or production readiness.

## Final verification

| Gate | Current result |
| --- | --- |
| dedicated freeze guard | 5 passed |
| freeze + boundary + E2E selection | 13 passed |
| complete Deployment selection | 240 passed |
| architecture suite | 258 passed |
| Ruff, repository-wide | passed |
| authoritative Mypy `backend/synapse` | 758 source files, zero issues |
| global regression, four deterministic partitions | 4,354 passed, 5 skipped, 4 subtests passed |
| global file coverage | 330 enumerated/assigned/unique; zero missing, duplicate or extra |
| residual controlled DB/temp review | none found |
| staged files | zero |

The test-only Mypy limitation recorded by the Slice 14 audit remains separate from the
green authoritative source gate. No suppress, skip or contract weakening was added.

## Freeze governance

Any public-contract, module, schema, migration, authority, edge, provider capability or
global activation change requires explicit unfreeze governance and proportionate
critical gates. Internal fixes may proceed only when they preserve this baseline.

The next macro phase is Global Composition Root, but its exact authority must be
resolved before implementation. This freeze does not authorize production wiring.
