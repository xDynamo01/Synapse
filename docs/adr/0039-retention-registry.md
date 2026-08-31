# ADR 0039: Retention Registry

## Status

Accepted.

## Context

Synapse has domain-specific cleanup for notifications and agent admin action requests. More durable domains will need retention later, but creating isolated commands for each domain would make operations harder to discover and automate.

## Decision

Add a central retention registry as a catalog and execution facade.

Initial domains:

- `notifications`
- `agent_admin_requests`

Each domain registers:

- domain id
- description
- policy path
- dry-run support
- default dry-run behavior
- cleanup callable
- status callable

`RetentionRuntime` provides:

- list domains
- inspect a domain
- aggregate retention status
- cleanup one domain
- cleanup all registered domains

`cleanup_all` is dry-run by default.

## Consequences

- Existing domain-specific cleanup logic remains in place.
- Operators and future UI/mobile clients have one catalog for retention capability discovery.
- No audit logs or agent records are deleted by this registry.
- The registry does not create a global cleanup scheduler by default.

## Non-Goals

- No dashboard.
- No global destructive cleanup.
- No Resource Registry.
- No RBAC changes.
- No migration of all persisted domains to retention.
