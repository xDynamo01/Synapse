# Application bootstrap

Phase 1 established one canonical path: `synapse.main.create_app` -> FastAPI
lifespan -> `build_application` -> `create_runtime` -> feature builders ->
`RuntimeContainer`.

`RuntimeContainer` is defined in `bootstrap/container.py` and instantiated once,
in `bootstrap/application.py`. `core/app.py` is a compatibility re-export only.
Importing `synapse.main` creates the inert FastAPI object but does not build the
runtime, create `DATA_DIR`, open devices, load models, start subprocesses, or
acquire locks.

## Feature builders

The root coordinates twelve typed builders:

1. `foundation`: data root, configuration, events, permissions;
2. `models-and-providers`: model routing, provider facades, model hub, insight;
3. `platform`: agents registry, policy/capability facades, approvals and migrations;
4. `multimodal-interaction`: audio, voice, vision and perception;
5. `agents-and-delegation`: administration, conversations, delegation and worker;
6. `missions-and-swarm`: missions, attempts, worker execution and supervision;
7. `automation`: scheduler, daemon, decisions and permission bridge;
8. `integration`: health/readiness, execution, MCP and Context Fusion;
9. `skills`: the existing globally wired Skills runtime surface;
10. `project-governance`: governed project/RFC application and delivery bindings;
11. `intelligence-boundary`: controlled Intelligence Trust Boundary bindings;
12. `world`: world projection, attention and Agent Loop.

Each returns `BuiltFeature[T]`: a typed public value plus lifecycle resources,
health contributors and offered ports. Builders do not import API or Commands.
Commands and Chat remain wired at the root because their decomposition belongs
to Phase 2 and was explicitly excluded here. Dependencies are explicit; there is
no generic service locator.

## Global binding inventory

Global Composition Root Slice 1 adds a typed, immutable inventory in
`bootstrap/bindings.py`. The inventory is factual metadata: it does not import,
construct, start or close any local Composition Root and grants no production
activation authority.

Each declaration separates:

- readiness requirement: required or intentionally optional;
- factual availability: available, capability-limited or unavailable;
- current binding mode: global, local opt-in, legacy-global-only or absent;
- activation authority and factual activation state.

`build_application()` exposes the canonical tuple in
`Application.metadata["global_binding_inventory"]`. Required declarations remain
readiness blockers until their mode becomes `global` through a separately governed
slice. Optional capability limitations remain visible and are never widened by a
fallback.

Required entries are Private Evals, Coding Sessions, Skills Runtime Phase 2, Sandbox
Execution Boundary, Repository Runtime and Deployment Runtime. The final frozen root
globally owns five of them through inert construction, explicit lifecycle and neutral
Health projections. Sandbox remains local/inert because no canonical operational
admission policy exists; bootstrap does not invent security policy. Concrete Sandbox
Driver and Search remain optional local bindings. Voice / Audio / Perception remains
optional legacy-global and active. Capability limitations never trigger fallback.

Lifecycle order is explicit: feature resources, Deployment, Private Evals, Coding
Sessions, Skills Phase 2 and Repository Runtime. Repository startup is capability-
conditional: a non-Git project root degrades Health without preventing unrelated
services. All Health contributors consume neutral immutable facts and do not own
lifecycle or bounded-context operations.

## Compatibility

- `synapse.core.app` re-exports canonical construction and builds nothing.
- `synapse.core.model_router` re-exports `synapse.models.router` with no duplicate logic.
- `synapse.core.__init__` lazily exposes compatibility names without bootstrap.
