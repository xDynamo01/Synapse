# ADR 0001: Local-First DATA_DIR

## Status

Accepted.

## Context

Synapse must work on one local machine before it grows into a homelab service. Critical runtime state cannot depend on cloud services.

## Decision

All persistent runtime state starts under one local `DATA_DIR`:

- config
- memory
- agents
- projects
- skills
- tasks
- logs
- library
- chats
- devices

Runtime services must not create parallel persistence roots.

## Consequences

- Local backup and inspection are straightforward.
- Docker can mount one volume for runtime state.
- Sensitive generated state must be ignored by Git.
- Future storage engines must still be represented through this boundary.

