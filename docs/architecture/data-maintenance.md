# Administrative Data Maintenance

Status: **Implemented / NOT READY**.

`DataMaintenanceRuntime` is the only administrative coordinator for inspecting,
planning and executing bounded maintenance over `DATA_DIR`. It coordinates
registered owners; it does not understand domain records and it never accepts a
filesystem path from API or Commands.

## Boundary

- `MaintenanceContributor` is the neutral owner contract.
- `MaintenanceContributorRegistry` is explicit, deterministic and rejects
  duplicate IDs.
- Contributors advertise only implemented capabilities. Backup, restore and
  migration are currently not advertised.
- Foundation and configuration contributors are inspection-only.
- Temporary-files cleanup owns only old, known `*.tmp` files in the explicit
  technical `cache`, `temp` and `tmp` roots. Domain-owned `*.tmp` artifacts are
  not candidates.
- Retention delegates to the existing `RetentionRuntime`; it does not duplicate
  retention rules or record interpretation.
- API and Commands translate transport input into scopes and call the same
  runtime. They contain no filesystem operations or direct `DataDir` access.

## Safety protocol

Inspection precedes planning. A stored plan contains bounded relative
references, an expiry, revision, risk, dry-run flag and canonical checksum.
Execution fails closed unless the caller has `maintenance.admin`, explicitly
confirms the plan, supplies the exact checksum and revision, and policy allows
every contributor resource. High-risk work additionally requires the approval
bound to that plan. One operation lock serializes executions.

Terminal results are idempotent. Partial failures are persisted action by
action. Expired or cancelled plans cannot execute. A restart marks an interrupted
execution as interrupted and never resumes destructive work automatically.
Contributor timeouts and exceptions degrade that contributor without hiding
successful results from the others.

Maintenance status reports the registry, active/stale operation, last
inspection/execution, pending cleanup and degraded contributors through its own
admin facade. The frozen Health/Readiness component registry is intentionally
unchanged because a new health contributor is not necessary for this phase.

## Public scopes

Allowed scope kinds are `all`, `contributor`, `capability`, `domain` and
`category`. Values are registered identifiers, never paths. Public findings use
safe references such as `cache/item.tmp`, `config:system` or
`retention:notifications`; absolute paths and raw domain payloads are forbidden.

The canonical administrative HTTP surface is `/api/maintenance/*`; the matching
Commands surface is `/maintenance-*`. Generic destructive Foundation and
Retention delivery endpoints were removed. Read-only Foundation validation
compatibility remains routed through contributors.

## Deliberate limits

This phase does not redesign `DataDir`, migrate stores, alter Primary or
Ephemeral agent semantics, create a generic filesystem manager, or provide
global backup/restore. Domain-owned Voice, Perception, Notification, Admin and
Ephemeral cleanup stays with its existing owner.

The unrelated measured SCCs remain unchanged at 25 contexts/76 internal edges,
4/6 and 2/2. They remain later architectural blockers; this phase did not attack
them.
