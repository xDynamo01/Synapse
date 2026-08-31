# Coding Sessions durable fencing authority V1

Coding Sessions owns a durable, scope-specific, monotonic generation. Each accepted
ownership transition appends one fact atomically and advances the generation by one.
Generation is neither clock-derived nor TTL-derived. Replay reconstructs history and
does not advance it. Missing or unprovable history fails closed.

The scope binds a session to repository/checkout/worktree and/or Sandbox workspace.
`FencingTokenV1` binds that scope, generation, ownership identity, authority/version,
occurrence, causation/correlation and an optional consumer fingerprint. It contains no
operation authorization.

Validation accepts exact equality with the latest durable generation. Older tokens are
stale; future tokens are invalid; authority, ownership, scope or binding differences are
mismatches. Read-only operations may omit fencing. Mutable operation classes require it.
Fresh read preconditions may record the observed generation, but
`FreshPrecondition != CurrentOwnership`.

The consumer-owned Sandbox and Repository seams can carry a token, but neither applies
mutations in this slice. Repository Runtime and the future concrete Sandbox driver remain
future enforcement targets.

- `Lease != Authorization`
- `FencingToken != Authorization`
- `Fencing != Authorization`
- `Fencing != Idempotency`
- `LeaseValidity != FencingValidity`
- `Replay != GenerationAdvance`
- `FencingAuthorityImplemented != EndToEndFencingEnforced`
