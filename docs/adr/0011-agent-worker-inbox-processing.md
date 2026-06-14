# ADR 0011: Agent Worker Inbox Processing

Date: 2026-06-14

## Status

Accepted

## Context

Agent-to-agent messaging already persists structured messages and human-readable `INBOX.md` projections. Until this decision, pending messages could be listed and marked manually, but no runtime component owned the processing flow.

Synapse needs inbox processing before adding UI, schedulers, mobile surfaces, or autonomous homelab mode. The worker must still respect local-first persistence, effective agent policy, approval gates, and runtime-owned context.

## Decision

Create `AgentWorker` in `backend/synapse/workers/agent_worker.py`.

The worker processes inbox messages explicitly when called by command or API:

1. list pending messages for an agent
2. mark each message as `read`
3. load destination-agent context through `ContextLoader`
4. run the agent through `AgentRuntime`
5. optionally reply through `send_agent_message`
6. mark the original message as `processed` or `failed`
7. emit worker events

Worker events:

- `worker.inbox_checked`
- `worker.message_processing_started`
- `worker.message_processed`
- `worker.message_failed`

Autonomous replies are policy-controlled. The worker sends a reply only when `send_agent_message` is allowed by `AgentEffectivePolicy` and the agent can delegate or explicitly prefers `send_agent_message`.

## Consequences

Positive:

- inbox processing is now a real runtime flow
- tool calls inside inbox processing use the same policy, permission, approval, and event path as chat
- message status transitions are persisted
- commands and API endpoints can trigger worker behavior without owning logic

Tradeoffs:

- there is no scheduler or queue yet
- retries and concurrency controls are not implemented
- request/response threading still relies on task/message metadata rather than a formal conversation id
