# ADR 0065: Development Worktree Strategy

## Status

Accepted.

## Context

Synapse V2 now contains many independently evolving areas: backend runtimes, policies, mission/delegation systems, UI contracts, frontend shell, Mission Control UI, Agent Directory UI, and Voice/Perception work. A single checkout creates avoidable conflicts and makes it harder for multiple development agents to work safely in parallel.

## Decision

Use Git worktrees as the default infrastructure for parallel development.

Recommended sibling worktrees:

- `Synapse` for integration baseline
- `Synapse-Core` for backend/runtime work
- `Synapse-UI` for frontend work
- `Synapse-Voice` for voice runtime work
- `Synapse-Perception` for perception runtime work

Ownership documents define which areas belong to each worktree. Integration hotspot files require coordination before edits.

## Rationale

Worktrees allow multiple branches to be checked out simultaneously without copying the repository. This keeps local state isolated, reduces accidental cross-scope edits, and makes branch ownership explicit.

## Benefits

- Lower conflict frequency.
- Clearer ownership by area.
- Safer parallel work by multiple agents.
- Easier validation per worktree.
- No new CI, scripts, hooks, or dependencies required.

## Limitations

- Worktrees do not replace review discipline.
- Cross-cutting files still need coordination.
- Long-lived branches can still drift.
- Manual validation remains required until CI is added in a future stage.

## Future Strategy

Future stages may add CI, pre-merge validation, or service wrappers. Those are intentionally out of scope for this ADR. This stage only standardizes documentation and development workflow.
