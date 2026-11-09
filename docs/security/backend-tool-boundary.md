# Backend tool boundary

Status: design, not evidence of an implemented boundary. Applies to the
integrated Core and the mission and Skill requirements in
`docs/specs/2026-11-06-synapse-0.3-decision-charter.md` (MI-001–007,
SK-001–004, SE-001–006 and QA-001–003).

The OS user controlling the local CLI is the owner. Its approval applies to an
immutable stored mission, not to model output. Worker output and Skill
instructions are data, never approvals or broker calls. A future remote client
needs a separate authenticated boundary. This is not an OS sandbox against
other processes running as the same user.

Before an effect, Core must load the stored contract and current mission state,
require an exact action and resource, and reject a stopped mission. A selected
Skill must bind scope, ID, version and manifest digest in the approved mission;
its declared permissions must be a subset of that mission. Its instructions may
guide an allowed operation, but cannot expand its authority. Registry manifests
are immutable; a newer version does not change a pinned one.

Workspace paths must be relative, bounded and individually allowlisted. Reject
absolute paths, parent traversal, alternate streams and reparse points. Protect
the entire Core state directory, including SQLite, WAL, lock and receipts, even
when it is inside the workspace. String prefix or canonicalization alone is
insufficient: Windows case folding, hard links, short names, junctions and
concurrent rename/reparse changes can create aliases or invalidate an earlier
check. Resolve components through retained directory handles with no-follow
semantics, verify object identity and reparse attributes, and account for hard
links. If a requested filesystem or platform cannot enforce these checks,
return a typed unavailable error rather than using a path-only fallback.

Database commits cannot atomically include an external filesystem change. Commit
an intent binding the request digest, mission, exact target and expected content
digest before creating a file. After a crash, reconcile only a demonstrably owned
effect whose readback matches that intent; ambiguous or partial files must not be
reported as success or blindly overwritten. The final Core-generated receipt
records observed hashes and is committed with the durable request response. A
duplicate request returns that same receipt; a changed payload with the same ID
is rejected. Recheck mission state before a new effect after any restart.
Replacement needs separately owned backups and recovery; it remains unavailable
until those invariants are implemented and tested. Delete, shell, browser,
accounts and external Skill installation also remain unavailable in this stage.

An attacker with OS-owner privileges can modify workspace files or Core state
outside the application; this design does not claim to prevent that. It must
still fail closed on detectable races or ambiguous recovery. Real binary tests
must exercise approvals, revocation, restart, path aliases, readback hashes,
duplicate requests and Skill pinning in temporary roots.

Windows API references: [NtCreateFile](https://learn.microsoft.com/windows/win32/api/winternl/nf-winternl-ntcreatefile)
documents handle-relative names and reparse-point opening;
[reparse point operations](https://learn.microsoft.com/windows/win32/fileio/reparse-point-operations)
documents reparse attributes. Neither reference alone proves the complete
multi-step race and hard-link policy; implementation and tests must do so.
