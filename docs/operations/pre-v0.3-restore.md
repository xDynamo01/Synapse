# OPS-0001 — Restore the preserved pre-v0.3 Synapse

## Preserved identity

- Repository: `https://github.com/xDynamo01/Synapse`
- Visibility at preservation: public, explicitly retained by the user
- Commit: `46177e3973ed06a9c71d3bebd3166d587a559d76`
- Annotated tag: `pre-v0.3`
- Development branch created from the same commit: `develop/0.3`

## Restore procedure

```powershell
$restoreRoot = 'C:\path\to\new\Synapse-restore'
git clone https://github.com/xDynamo01/Synapse.git $restoreRoot
git -C $restoreRoot fetch origin tag pre-v0.3
git -C $restoreRoot switch --detach pre-v0.3
git -C $restoreRoot rev-parse HEAD
git -C $restoreRoot fsck --full
```

The printed revision must be exactly
`46177e3973ed06a9c71d3bebd3166d587a559d76`.

To continue 0.3 development instead:

```powershell
git -C $restoreRoot switch develop/0.3
```

## Independently verified result

On 2026-11-05 an independent clone restored the tag to the expected commit,
completed `git fsck --full`, contained 1,905 tracked files and contained no Git LFS
pointers. The following intentionally local items were absent: `.env`,
`artifacts/reports`, `data/project_knowledge`, generated world-state ledgers and
`Synapse.exe`.

## Data outside Git

The following are not restored by Git and require separate local custody or
regeneration: secrets in `.env`, model files, voice models/runtimes, runtime
databases and ledgers, caches, virtual environments, package installations,
generated builds and reports. Never copy these into a public repository without a
separate data/security review.
