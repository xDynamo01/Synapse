# ADR 0017: Communication Runtime V1

Date: 2026-06-19

## Status

Accepted

## Context

Synapse needs its first real utility runtime while preserving the foundation principles: local-first, permission-first, approval-first, and runtime-first. Agents must not access external providers directly.

## Decision

Create `synapse.communication` with:

- provider interface
- offline `MockCommunicationProvider`
- prepared `GmailCommunicationProvider`
- `CommunicationRuntime`
- email and draft models
- Hermes email briefing flow
- communication tools routed through ToolRouter and EffectivePolicy
- communication commands and API endpoints
- scheduler job type `check_email`

V1 supports reading emails, classifying emails, summarizing emails, creating drafts, listing drafts, and generating summaries and Hermes briefings.

V1 explicitly does not implement automatic email sending.

## Consequences

Hermes becomes the first operational agent with a concrete utility domain. Draft creation is available, but sending remains reserved for a future critical-risk `send_email` path with explicit approval. The mock provider keeps tests deterministic and local-first while the Gmail provider boundary exists for later real integration.

Known gaps:

- no Gmail OAuth/token storage
- no provider pagination or sync cursor
- no real send-email implementation
- no draft approval workflow beyond existing approval architecture
- no persistent email cache beyond drafts
