# Development Overview

Synapse V2 is large enough that multiple development agents should not work in one checkout. The recommended model is one canonical repository plus separate Git worktrees for major ownership areas.

This document defines the organizational strategy only. It does not introduce scripts, hooks, CI, or product behavior.

## Branch Strategy

Use short-lived topic branches scoped to one ownership area.

Recommended branch names:

- `core/<topic>`
- `ui/<topic>`
- `voice/<topic>`
- `perception/<topic>`
- `docs/<topic>`
- `infra/<topic>`

Branches should stay small enough to review and merge without crossing many ownership boundaries. Cross-cutting changes should be split into coordination commits where possible.

## Worktree Strategy

Keep the primary checkout as the integration baseline:

```text
F:/Projetos/Synapse
```

Create sibling worktrees for parallel areas:

```text
F:/Projetos/Synapse-Core
F:/Projetos/Synapse-UI
F:/Projetos/Synapse-Voice
F:/Projetos/Synapse-Perception
```

Each worktree has its own branch and should focus on its ownership area. This avoids frequent conflicts in the same filesystem checkout and makes it clearer which agent owns which scope.

## Recommended Development Flow

1. Start from an updated integration baseline.
2. Create a worktree for the ownership area.
3. Make scoped changes only in that worktree.
4. Avoid editing integration hotspot files unless the step explicitly requires it.
5. Run the validation checklist for the area.
6. Merge or rebase only after tests pass.
7. Remove the worktree after the branch is merged.

## Worktree Responsibilities

Core worktree:

- Runtime foundations
- Agent Runtime
- Delegation Runtime
- Mission Runtime
- Health and Readiness
- Policies and permissions
- Scheduler and daemon

UI worktree:

- `frontend/`
- UI contracts consumption
- Mission Control UI
- Agent Directory UI
- Chat workspace UI
- Styling and visual shell

Voice worktree:

- Voice Runtime
- STT/TTS abstractions
- Audio session lifecycle
- Wake word boundary

Perception worktree:

- Perception observations and features
- multimodal inference boundaries
- Animation state
- Lip sync boundary

Docs/Architecture worktree:

- ADRs
- Architecture docs
- Roadmap
- Runtime walkthrough
- Development process docs

## Integration Rule

If a change touches more than one ownership area, explicitly call it out in the final report and validate the broader surface. Do not silently expand scope.
