# Primary, Persistent and Ephemeral Agent Finalization

Date: 2026-07-14. Status: phase complete. Backend remains **NOT READY** because
this phase does not close the remaining backend architectural blockers.

The before matrix is `primary-ephemeral-agent-surface-before.json`. It established
one implicit persistent kind, one canonical creation runtime, no Primary binding,
no ephemeral lifecycle and one legacy API adapter. The adapter was completely
removed rather than retained behind an alias.

The result has exactly three explicit `AgentKind` values. Provisioning remains the
only persistent authority. Primary owns only workspace binding, main conversation
and frontend-neutral bootstrap. Ephemeral owns bounded temporary identity, lease,
result and cleanup; it cannot write agent directories or spawn children directly.
Mission/Swarm owns workforce creation, Resource Pressure bounds concurrency, Model
Capability records explicit selection, Workers execute and TaskAttempts preserve
history.

API delta is intentional: 425→438 paths, 471→485 operations and 100→103 schemas.
Commands are 339→351, adding seven Primary and five ephemeral diagnostic/admin
commands. There is no public or command spawn surface.

The requested gates are green: 71 architecture tests; 97 focused
Agents/Provisioning/Primary/Ephemeral tests; 170 Missions/Workers/Swarm/Delegation
tests; all 72 acceptance tests, including the eight requested flows; and 86 frozen
domain tests with one intentional skip. The global suite passed with 1,099 tests,
one skip and four passing subtests. Ruff and `git diff --check` also pass.

The deterministic cleanup measurement created two ephemeral agents, destroyed both
in 130.601 ms and left zero active agents, cleanup-pending records, temporary
contexts, scratchpad references or permanent ephemeral agent directories. Exact
before/after facts, OpenAPI hash, commands and scope guards are recorded in
`primary-ephemeral-agent-after-metrics.json`.
