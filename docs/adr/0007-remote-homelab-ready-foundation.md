# ADR 0007: Remote and Homelab Ready Foundation

## Status

Accepted.

## Context

Synapse should start local, but it must evolve into a 24/7 homelab service with remote clients and device-aware access.

## Decision

The foundation includes:

- configurable API host and port
- Docker Compose with `DATA_DIR` volume mount
- event log
- task persistence
- initial device registry with trusted, untrusted, and revoked devices

Direct internet exposure is not assumed. Remote access should go through VPN or a secure tunnel and a future Synapse gateway.

## Consequences

- Homelab deployment can evolve without changing the core persistence model.
- Device records are ready before full login/session support.
- API hardening remains a required phase before remote exposure.

