# ADR 0047: Delegation Completion Signal

## Status

Accepted.

## Context

Delegations are durable responsibility records, while worker responses are still free-form text. Inferring completion from text would make agent collaboration brittle and hard to audit.

## Decision

Synapse adds a structured `DelegationCompletionSignal` persisted beside the delegation task:

```text
DATA_DIR/delegation/{task_id}.completion.yaml
```

Only the assigned agent can submit a completion signal by default. Signals support `completed`, `failed`, and `needs_followup`.

Submitting a signal does not apply it automatically. `apply_completion_signal()` is an explicit runtime action:

- `completed` moves the delegation to `completed`.
- `failed` moves the delegation to `failed`.
- `needs_followup` keeps the delegation in progress and stores the follow-up request.

The worker may submit a signal only when `AgentRuntime` returns a recognized structured payload:

```json
{
  "delegation_completion": {
    "task_id": "optional-task-id",
    "status": "completed",
    "summary": "Short summary",
    "result": "Optional result"
  }
}
```

Plain text responses never complete delegations.

## Consequences

- Delegation closure is explicit and auditable.
- Long-running collaborations can separate response generation from final state transition.
- Future UI or Mission Control can review/apply completion signals without parsing text.
- This is not a workflow engine, planner, or automation policy.

## Runtime Surface

- `DelegationRuntime.submit_completion_signal()`
- `DelegationRuntime.get_completion_signal()`
- `DelegationRuntime.apply_completion_signal()`
- `/delegation-completion <task_id>`
- `/apply-delegation-completion <task_id>`
- `GET /delegations/{task_id}/completion`
- `POST /delegations/{task_id}/completion`
- `POST /delegations/{task_id}/completion/apply`
