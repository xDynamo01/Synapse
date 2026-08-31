# Synapse Frontend

Status: **NOT IMPLEMENTED**.

The old Electron ADE implementation is **REMOVED / RETIRED** under
[ADR 0119](adr/0119-retire-electron-ade.md). The repository currently has no active
frontend source tree, desktop package target, installer, launcher or frontend release
artifact.

Backend-owned capabilities remain reusable:

- Operational Projection;
- Command Authority;
- Voice, Audio and Perception contracts;
- model/provider, agent, conversation, mission and runtime APIs.

These backend capabilities do not imply an active frontend implementation. A future
frontend must start from a clean governed baseline, define its own source layout and gates,
and consume backend contracts without duplicating backend authority.

Historical Electron ADE ADRs, audits and validation records are retained only as
superseded evidence.
