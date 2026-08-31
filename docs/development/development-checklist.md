# Development Checklist

Use this checklist before finishing any implementation stage.

## Scope

- [ ] The branch/worktree matches the ownership area.
- [ ] The implementation stayed within the requested scope.
- [ ] No unrelated refactor was included.
- [ ] No product feature was added during infrastructure-only stages.
- [ ] No runtime/API/frontend changes were made during docs-only stages.

## Tests and Quality

- [ ] Backend tests passed: `cmd /c py -m unittest discover -s tests`
- [ ] Backend lint passed: `cmd /c py -m ruff check .`
- [ ] Frontend tests passed, if frontend changed: `npm run test`
- [ ] Frontend build passed, if frontend changed: `npm run build`
- [ ] Frontend lint passed, if frontend changed: `npm run lint`

## Architecture Docs

- [ ] ADR added or updated when a durable decision was made.
- [ ] `docs/architecture.md` updated when architecture changed.
- [ ] `ROADMAP.md` updated when a phase status changed.
- [ ] `docs/validation/runtime-walkthrough.md` updated when runtime flow changed.
- [ ] Development docs updated when process changed.
- [ ] `docs/development/workflow.md` updated when the validation sequence changed.

## Ownership and Integration

- [ ] Did not edit another worktree owner area without reason.
- [ ] Critical integration files were touched only when necessary.
- [ ] Any cross-cutting file edits are listed in the final report.
- [ ] No generated folders were committed.
- [ ] No secrets or local DATA_DIR state were added.

## Final Report

- [ ] Files changed are summarized.
- [ ] Tests executed are listed with results.
- [ ] Known warnings are reported.
- [ ] Remaining gaps are explicit.
- [ ] Next recommended step is stated.
