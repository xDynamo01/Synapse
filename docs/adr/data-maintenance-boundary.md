# ADR — Contributor-owned administrative DataDir maintenance

Date: 2026-07-14

Status: Accepted

## Context

Administrative DataDir behavior was split between `DataDir`, a Foundation API
adapter, Retention delivery endpoints and slash commands. Delivery code could
reach filesystem-aware operations directly, while a future generic cleanup
surface would risk interpreting data owned by unrelated domains.

## Decision

Introduce one domain-neutral `DataMaintenanceRuntime`, an explicit contributor
registry and a small `MaintenanceContributor` protocol. Concrete owners remain
responsible for inspection and action execution. The coordinator stores bounded
plans/results and enforces permission, policy, confirmation, checksum, revision,
expiry, approval, locking, idempotence and restart reconciliation.

Remove the generic destructive Foundation/Retention API and Command operations.
Keep read-only compatibility through the canonical runtime. Do not claim
backup, restore or migration until real contributors exist.

## Consequences

Delivery layers no longer import filesystem primitives or access `DataDir`.
Domain interpretation remains with owners and destructive work is plan-bound.
The new protocol adds explicit registration work for future owners. There is no
automatic destructive restart recovery and no arbitrary-path maintenance API.
