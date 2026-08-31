# Ownership Map

This document defines the default ownership boundaries for parallel Synapse development. Ownership is a coordination rule, not a security boundary.

## Core

Primary areas:

- `backend/synapse/core/`
- `backend/synapse/agents/`
- `backend/synapse/delegation/`
- `backend/synapse/delegation_execution/`
- `backend/synapse/delegation_inbox/`
- `backend/synapse/delegation_recovery/`
- `backend/synapse/missions/`
- `backend/synapse/health/`
- `backend/synapse/readiness/`
- `backend/synapse/policies/`
- `backend/synapse/scheduler/`
- `backend/synapse/daemon/`
- `backend/synapse/tools/`

Typical work:

- Runtime behavior
- Persistence behavior
- Permission and policy enforcement
- Scheduler/daemon behavior
- Health/readiness logic

## UI

Primary areas:

- `frontend/`
- UI-facing docs and ADRs for frontend stages
- UI contract consumption

Typical work:

- React/TypeScript app shell
- Tailwind styling
- Mission Control UI
- Agent Directory UI
- Future Chat UI
- Future Settings UI

UI must not implement runtime policy or duplicate backend decisions.

## Voice

Primary areas, when created:

- `backend/synapse/voice/`
- future frontend voice surfaces
- voice ADRs

Typical work:

- Voice Runtime
- STT abstraction
- TTS abstraction
- Audio session lifecycle
- Wake word boundary

## Visualization and animation

Frontend owns visualization and animation. Backend Voice publishes factual
voice states/events and Perception owns multimodal observations, features and
inferences. No backend Avatar or Embodiment Runtime is an owned target area.

## Communication

Primary areas:

- `backend/synapse/communication/`
- `backend/synapse/notifications/`

Typical work:

- Communication Runtime
- Draft approval flow
- Outbound send authorization
- Notification runtime

External providers must remain mock/prepared unless a stage explicitly authorizes real integration.

## Documentation and Architecture

Primary areas:

- `docs/adr/`
- `docs/architecture.md`
- `docs/validation/runtime-walkthrough.md`
- `ROADMAP.md`
- `docs/development/`

Typical work:

- ADRs
- Architecture summaries
- Roadmap updates
- Runtime walkthrough
- Development process

## Cross-Cutting Ownership

Some files are integration surfaces and require coordination before edit. See `merge-strategy.md` and `development-checklist.md`.
