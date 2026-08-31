# Worktree Guide

Git worktrees allow multiple branches to be checked out at the same time from one repository. Use them to let different agents work on Core, UI, Voice, Perception, and docs without sharing one dirty working tree.

## Create a Worktree

From the main repository:

```powershell
cd F:\Projetos\Synapse
git fetch
git worktree add ..\Synapse-UI -b ui/agent-directory-ui
```

For an existing branch:

```powershell
git worktree add ..\Synapse-Core core/delegation-policy
```

## Recommended Structure

```text
F:/Projetos/
  Synapse/          integration baseline
  Synapse-Core/     backend/runtime work
  Synapse-UI/       frontend/UI work
  Synapse-Voice/    voice runtime work
  Synapse-Perception/   perception runtime work
```

## Update a Worktree

Inside the worktree:

```powershell
git fetch
git status
git rebase main
```

Use merge instead of rebase only when preserving branch history is important or when the branch is already shared and rewriting history would disrupt another agent.

## Remove a Worktree

After the branch is merged:

```powershell
cd F:\Projetos\Synapse
git worktree remove ..\Synapse-UI
git worktree prune
```

If the worktree has uncommitted changes, Git will refuse removal unless forced. Do not force-remove a worktree unless those changes are intentionally discarded.

## Synchronize Between Worktrees

Do not copy files manually between worktrees. Use Git:

```powershell
git add .
git commit -m "..."
git fetch
git rebase main
```

If another worktree has a branch you need, merge or cherry-pick from that branch explicitly.

## Best Practices

- One worktree per ownership area.
- One agent per worktree at a time.
- Keep branches short-lived.
- Keep commits scoped.
- Avoid changing integration hotspot files unless necessary.
- Run validation before merge.
- Do not use a worktree as long-term storage for uncommitted work.
- Do not edit generated dependency folders such as `node_modules/` or `frontend/dist/`.
