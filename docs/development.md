# Development Guide

Any new provider, external Tool/MCP, Speech/Vision adapter, export or fallback
must declare its `ProcessingBoundary`, create classified InformationAssets and
call `EgressGatePort` immediately before transport. Never infer locality from
localhost, log payloads, reuse a manifest for another provider, or add bypass
commands. Add an active TrustProfile through controlled administration.

Use an RFC for architectural, contract, persistence, lifecycle, policy,
permission, destructive/removal, relevant Skill/Tool/Provider or multi-agent
flow changes. Typos, non-normative docs, extra tests and proven-equivalent local
repairs normally need no RFC. Start from `docs/templates/RFC-template.md` and
record tests/linters as Evidence rather than treating the RFC as a quality gate.

Skill packages require `SKILL.md` and `manifest.yaml`, stable ID, explicit
SemVer and relative declared files. Add packages under `data/skills/packages`
or inspect/install a candidate under DATA_DIR; never rely on import side effects.

## Testing agent kinds

Use AgentProvisioning fixtures for every durable test identity, then assign Primary
explicitly. Create ephemeral instances only through Mission/Swarm authority in
tests, use controlled Resource Pressure/Model Capability doubles, and assert no
`agents/<ephemeral-id>` directory or residual context remains. Never seed a default
Primary or reintroduce reusable agent templates.

## Choosing storage

Keep human-editable configuration/content in current YAML or Markdown. Use
`FileCollection` only for small or bounded independent operational records and use
the canonical atomic writer/lock for singleton documents. Do not duplicate atomic
replace or locking in a new store. Growing histories, complex queries, sustained
concurrency and multi-record transactions require an explicit SQLite decision
instead of stretching the file primitive.

## Adding a provider

Add execution behavior to the owning domain contract/registry, give the
implementation a stable explicit ID, and add a thin bootstrap projection into the
canonical catalog. Declare only tested capabilities and lifecycle behavior. Never
put secrets or absolute paths in manifest metadata, register by import side effect,
or use the general catalog to invoke domain methods. Mocks require explicit test or
development mode.

## Scope

This guide defines the local engineering workflow for Synapse V3. The backend
is the active executable foundation. The removed Electron ADE is retired and no
frontend implementation is currently present.

## Prerequisites

- Python 3.12 or newer;
- [`uv`](https://docs.astral.sh/uv/) for Python environments and commands;
- Git for local source control;
- Node.js only when a future governed frontend requires it;
- optional local providers such as Ollama, LM Studio, Faster Whisper models, or
  Piper only for their explicit integration tests.

No cloud account is required for the deterministic backend suite.

## Environment Setup

From the repository root:

```powershell
uv sync --extra dev
```

Runtime configuration is environment-driven where necessary:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SYNAPSE_DATA_DIR` | `./data` | persistence and configuration root |
| `SYNAPSE_HOST` | `127.0.0.1` | backend bind host |
| `SYNAPSE_PORT` | `8717` | backend port |
| `SYNAPSE_DEFAULT_ACTOR_ID` | `local_owner` | local actor fallback |
| `SYNAPSE_ENV` | empty | environment-specific model behavior |
| `SYNAPSE_LOG_LEVEL` | `info` | sidecar log level |

Use a temporary `SYNAPSE_DATA_DIR` for tests, experiments, and destructive
manual workflows. The repository `data/` tree is development seed data, not a
disposable test directory.

## Running the Backend

```powershell
uv run uvicorn synapse.main:app --app-dir backend --host 127.0.0.1 --port 8717
```

The backend exposes readiness and health contracts through FastAPI. A process
being alive is not equivalent to runtime readiness; provider and migration
failures must remain visible.

## Validation Commands

For architecture work, run guardrails, focused regressions, the global suite,
then the global lint gate:

```powershell
uv run --extra dev pytest tests/architecture -q
uv run --extra dev pytest tests/test_<domain>.py -q
uv run --extra dev pytest
uv run --extra dev ruff check .
git diff --check
uv run --extra dev mypy backend
```

Ruff and pytest are the current freeze gates. Mypy is configured and should be
used for touched domains, but repository-wide type cleanliness must not be
claimed until a validation record proves it.

The Backend Freeze suite is green. Exact counts, duration, OpenAPI inventory,
and cleanup evidence live in `docs/validation/backend-freeze-baseline.md`.

## Backend Freeze Workflow

For any future backend change, validate one domain at a time:

1. Run only the target test module or tightly related domain set.
2. Inventory every failure before editing.
3. Classify each failure as incomplete fixture, incorrect expectation, runtime
   defect, or contract mismatch.
4. Fix the smallest root cause without weakening real validation.
5. Preserve or add a regression test for the identified cause.
6. Rerun the focused domain.
7. Run the complete pytest suite and Ruff.
8. Record previous result, cause, correction, new result, and remaining modules
   in `docs/validation/backend-freeze-baseline.md`.

Do not use broad router extraction, file movement, new architecture, or
unrelated behavior changes as a stabilization technique. A fixture should be
fixed when the runtime is correctly enforcing a documented invariant.

## Test Isolation

Tests that persist state must create a temporary data root and seed only the
minimum valid records needed by the scenario. Shared factories may encode
canonical minimum identity, but scenario-specific policy stays visible in the
test.

Mock providers must be explicitly selected. Tests may not pass because a real
provider happened to be installed or running on the developer machine. Live
provider tests are opt-in and report prerequisites clearly.

## Backend Organization

New domain behavior belongs in `backend/synapse/<domain>/`. FastAPI routes and
slash commands translate inputs and errors; they do not own policy. Cross-domain
composition is wired through `RuntimeContainer`. Persistence paths resolve
through `DataDir`.

Do not read another runtime's files to bypass its interface. Do not introduce a
second source of truth in a route, worker, scheduler, or client.

Application construction belongs only to `synapse.bootstrap`. Feature builders
return typed facades, lifecycle resources, health contributors and ports; they
must not import API or Commands. Importing `synapse.main` must remain free of
runtime bootstrap side effects.

New HTTP operations belong in the existing bounded-context router under
`synapse.api.routers`; do not add handlers to `api/routes.py`. Register new
bounded routers only through `api/router_registry.py`. HTTP DTOs stay near the
router, while domain models remain in their domain. Routers must not import
stores, concrete providers or bootstrap; instantiate runtimes; access DataDir;
or implement policy. Run `tests/architecture/test_api_routing_boundaries.py`
and compare the complete OpenAPI snapshot for structural refactors.

New slash commands belong in the existing bounded-context module under
`synapse.commands.handlers` and must be explicitly included by
`build_command_handlers()`. Add `CommandMetadata`, positive/error/malformed
input tests and any policy/approval regression. Run
`tests/architecture/test_command_boundaries.py` and compare the frozen command
surface; never add dispatch branches back to `commands/runtime.py`.

New domain health belongs in a side-effect-free contributor registered by the
composition root. Contributors return canonical `ComponentHealth`, summary
facts and checks; they must not access stores, open devices, start providers or
import API/Commands/bootstrap. Add failure, timeout, optionality, duplicate-ID
and snapshot regressions, then run
`tests/architecture/test_health_contributor_boundaries.py`.

Context Fusion sources implement small read protocols owned by
`synapse.context_fusion.contracts`. Owner conversion adapters belong in
`synapse.bootstrap.adapters` and are injected once. Never import an owner
runtime, store, API, Commands or bootstrap from Context Fusion. Run
`tests/architecture/test_context_fusion_port_boundaries.py`.

New tools register one `ToolDefinition` in `RuntimeToolRegistry` and execute only via
`ToolExecutionPort`. Technology adapters may perform their protocol operation but
must not import Policy/Approval, persist global history, or expose a parallel public
identity. Consumers must not import adapters or call MCP/Desktop/builtin executors
directly. Run `tests/architecture/test_tool_execution_boundary.py` plus the focused
tool/MCP/consumer suites.

Custom agent creation must use `AgentProvisioningRuntime`; do not introduce
prefabricated agents, inheritance catalogs, or alternate creation paths.

## Persistence Changes

Persisted records require:

- a declared schema or record version;
- validation at read and write boundaries;
- atomic writes for replaceable records;
- a migration or explicit compatibility strategy;
- rollback behavior for multi-file operations;
- tests using older and malformed fixtures;
- documentation of retention and sensitive fields.

Manual edits under a developer's data root are not migrations.

## API Changes

Reuse domain input/output types where transport constraints permit. Validate
actor context, resource scope, idempotency, and error mapping. Update
[api.md](api.md) in the same change when public behavior changes. New endpoint
families should not be added merely to mirror internal methods.

## Future Frontend

No frontend is active. New frontend work starts from a clean governed baseline
according to [frontend.md](frontend.md); it must not restore the removed Electron ADE,
the removed React/Tauri shell, or move visual state into the backend.

## Documentation Discipline

Canonical specifications are the top-level documents linked from the README.
ADRs explain decisions and validation reports preserve evidence. When behavior
and a canonical specification diverge, implementation work stops until the
discrepancy is classified and one authoritative direction is chosen.

Use **Implemented**, **In development**, **Planned**, and **Legacy** exactly as
defined in [architecture.md](architecture.md). Never mark a domain implemented
solely because files or mocks exist.

## Completion Checklist

Before a local change is considered complete:

- focused tests pass;
- the global failure count does not increase;
- Ruff passes repository-wide;
- no developer paths, secrets, or transient logs are introduced;
- public API and persisted state changes are documented;
- status labels remain truthful;
- unrelated worktree changes are preserved.

For DataDir administration, add behavior through a registered
`MaintenanceContributor`; do not call `DataDir` or filesystem mutation APIs from
HTTP/Command delivery. Add architecture, policy-denial, path-safety,
idempotence and restart tests, and keep backup/restore capabilities false until
a real owner implementation exists.
