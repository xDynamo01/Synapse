# Merge Strategy

Parallel worktrees reduce conflicts, but they do not eliminate integration risk. This document defines when to rebase, when to merge, and how to validate.

## When to Rebase

Use rebase for short-lived local branches that are not shared:

```powershell
git fetch
git rebase main
```

Rebase is preferred before opening a merge because it keeps the branch focused and makes conflicts easier to understand.

## When to Merge

Use merge when:

- The branch is shared by multiple agents.
- The branch has already been used as an integration branch.
- Rewriting history would disrupt another active worktree.

## Before Merge

Run the relevant validation:

Backend/core changes:

```powershell
cmd /c py -m unittest discover -s tests
cmd /c py -m ruff check .
```

Frontend changes:

```powershell
cd frontend
npm run test
npm run build
npm run lint
```

Docs-only changes:

- Verify links and filenames.
- Run backend/frontend tests if the step explicitly requires validation or if integration docs were updated after functional changes.

## Conflict Resolution

Resolve conflicts by ownership:

- Core owner resolves runtime conflicts.
- UI owner resolves frontend conflicts.
- Docs owner resolves documentation conflicts.
- Integration owner resolves `backend/synapse/core/app.py`, `backend/synapse/api/routes.py`, `ROADMAP.md`, `docs/architecture.md`, and `docs/validation/runtime-walkthrough.md`.

Do not resolve conflicts by deleting unfamiliar code. Read both sides and preserve behavior unless the owning stage explicitly supersedes it.

## Critical Integration Files

Avoid simultaneous edits to:

- `backend/synapse/core/app.py`
- `backend/synapse/api/routes.py`
- `backend/synapse/commands/runtime.py`
- `docs/architecture.md`
- `ROADMAP.md`
- `docs/validation/runtime-walkthrough.md`
- `frontend/package.json`
- `frontend/src/api/client.ts`
- `frontend/src/api/queries.ts`
- `frontend/src/types/contracts.ts`

These files connect independent modules and frequently accumulate changes from multiple tracks.

## Merge Order

Preferred order:

1. Core contracts and backend runtime foundations.
2. UI contract updates.
3. UI views consuming those contracts.
4. Documentation updates.
5. Cross-cutting integration cleanup.

If two branches require the same integration file, merge the lower-level contract branch first.
