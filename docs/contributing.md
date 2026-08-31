# Contributing to Synapse

## Project Standard

Contributions must preserve Synapse as a local-first, backend-authoritative
agent runtime. Passing tests are necessary but do not justify bypassing policy,
weakening validation, duplicating state in a client, or promoting planned work
as implemented.

During the current Backend Freeze, stabilization takes precedence over feature
expansion and architectural refactoring.

## Canonical References

Read [architecture.md](architecture.md), the relevant domain specification, and
[development.md](development.md) before changing behavior. Documentation has
three levels:

1. canonical top-level specifications define current and target architecture;
2. ADRs record accepted decisions and their rationale;
3. validation reports record evidence from a specific point in time.

When they conflict, do not silently choose the newest filename. Determine
whether implementation, canonical specification, or historical record is stale
and update the authoritative layer explicitly.

## Change Scope

Keep each change bounded to one root cause or coherent capability. Avoid moving
files, extracting routers, adding abstractions, or renaming public contracts
while repairing an unrelated domain. Preserve unrelated local worktree changes.

A new architecture is justified only by a concrete invariant or repeated
failure that existing boundaries cannot safely express. Record significant,
hard-to-reverse decisions in an ADR before implementation.

## Development Workflow

1. Reproduce the behavior with a focused command.
2. Inspect domain code, fixtures, persisted schema, and relevant ADRs.
3. State the invariant and classify the root cause.
4. Add or preserve a failing regression test.
5. Make the smallest production or fixture correction.
6. Run focused tests, the global suite, and Ruff.
7. Update canonical docs, API docs, migrations, and validation evidence as
   required.

Setup and exact commands are in [development.md](development.md).

## Workspace Caches and Generated Artifacts

Tool caches belong under `.cache/`: Mypy uses `mypy/global` by default,
focused Skills checks use `mypy/skills`, Pytest uses `pytest`, Ruff uses
`ruff`, and Coverage uses `coverage`. Stable audit-only Mypy caches may use
`.cache/mypy/audit/<bounded-context>`; do not create timestamped, corrective,
or trial cache directories in the repository root.

Generated LinkedIn images, generated reports, and disposable files belong in
`artifacts/linkedin`, `artifacts/reports/generated`, and
`artifacts/temporary`. They are not committed by default. Run
`python scripts/clean_workspace.py --dry-run` before cleanup and omit
`--dry-run` only after reviewing the allowlisted paths. Add
`--include-artifacts` only when generated artifacts should also be removed.
Quality commands are available through `python scripts/run_quality_gates.py`;
all supported modes keep their caches under `.cache/`.

## Backend Rules

- Domain runtimes own state transitions and policy-relevant behavior.
- Routes, commands, schedulers, and clients are adapters.
- `RuntimeContainer` composes shared services.
- `DataDir` resolves operational persistence.
- Cross-domain access uses runtime interfaces, not another domain's files.
- Errors are typed and mapped consistently at adapter boundaries.
- Side effects follow permission, effective policy, and approval checks.
- Multi-file mutations define atomicity or rollback.

Do not add a new router merely to reduce file length. Router extraction follows
stable domain ownership and contract tests.

## Agent and Policy Rules

Agent identity must satisfy the canonical contract in [agents.md](agents.md).
Capabilities describe ability; permissions and policy authorize use. Fixtures
must contain the minimum valid identity rather than depending on permissive
runtime defaults.

Never relax real identity, timeout, retry, approval, path, or permission
validation solely to make an old fixture pass.

## API Rules

Public endpoints need validated input, actor context, stable error semantics,
resource authorization, idempotency where retries are possible, and contract
tests. Update [api.md](api.md) with public changes.

Clients do not call internal runtime methods or infer backend state transitions.
Any future renderer must access the backend only through governed typed API modules.

## Persistence Rules

New persisted structures require versioning, read/write validation, atomicity,
migration strategy, malformed-data tests, and retention classification. Do not
hardcode developer-specific paths or mutate repository seed data during tests.

Generated caches, provider models, recordings, logs, test outputs, credentials,
and local databases do not belong in source control.

## Testing Rules

- A production defect receives a regression test.
- A fixture defect receives a test or shared factory that preserves the
  canonical invariant.
- Tests are deterministic and isolated from developer services.
- Mocks are explicit and cannot establish production readiness.
- Focused success is followed by the global suite.
- The global failure count may not increase during freeze stabilization.
- Skips and expected failures include a concrete tracked reason.

At the current documentation freeze, the global suite is not green. Follow the
domain-by-domain baseline process rather than hiding failures with broad marks
or reduced collection.

## Code Style

Python targets 3.12 and uses Ruff with a 100-character line length. Prefer
typed dataclasses or Pydantic transport models consistent with the surrounding
domain. Keep functions focused, names domain-specific, and comments limited to
non-obvious constraints.

Do not add dependencies when the standard library or an existing dependency
meets the requirement. New runtime dependencies need security, license,
packaging, and platform analysis.

## Documentation Rules

Use the status vocabulary exactly:

- **Implemented** means executable code plus direct passing evidence;
- **In development** means partial, unstable, or under stabilization;
- **Planned** means target behavior that callers cannot rely on;
- **Legacy** means retained but not the V3 direction.

Write project-specific contracts, file locations, state transitions, failure
semantics, and completion criteria. Avoid aspirational lists without ownership
or validation gates.

## Review Checklist

Reviewers prioritize correctness, security, behavioral regressions, persistence
compatibility, and missing tests. Before integrating a change, verify:

- the root cause is fixed rather than masked;
- authority remains in the backend;
- permissions and approvals cannot be bypassed;
- failure and recovery behavior are explicit;
- focused and global validation evidence is recorded;
- status claims match the working implementation;
- no secrets, transient files, or unrelated edits are included.

## Commits and Remote Work

Use concise commits that represent one coherent change only when the active task
authorizes commits. Publishing branches, opening pull requests, and updating
remote services require explicit instruction. Documentation or implementation
work may intentionally remain entirely local.
