# Dependency rules

Executable rules in `tests/architecture` use AST import analysis:

- neutral `core` depends only on `core` and `observability`;
- domains do not import `api`, `commands`, or `bootstrap`;
- feature builders do not import API or Commands;
- API/Commands add no direct store, storage, or queue dependencies;
- concrete providers are wired only by bootstrap or authorized registries;
- `RuntimeContainer` has one definition and one production construction point;
- bounded-context cycles may not exceed the exact Phase 1 baseline.

Phase 1 freezes rather than hides existing debt. Exact allowed pairs in
`test_dependency_rules.py` cover one Chat-to-Commands edge, one
Commands-to-MemoryStore edge, and pre-existing concrete-provider edges. New
exceptions fail the suite.

Three SCCs remain and block Phase 2 completion: a 36-context component with 157
internal edges; `audio/multimodal/perception/speech_adapters` with 6; and
`attention/world_state` with 2. Phase 1 did not alter Tools, Providers, Storage,
API, or Commands internals and does not claim these cycles were resolved.
