# ADR 0006: Autonomy, Skill, and Permission Separation

## Status

Accepted.

## Context

An agent knowing how to do something is different from being allowed to do it, and both are different from being allowed to decide to do it without approval.

## Decision

Synapse treats these as separate concepts:

- Skill: the agent can perform or reason about an action.
- Permission: the agent may execute the action.
- Autonomy: the agent may decide to execute the action without a direct user instruction.

Current runtime stores these concepts separately. Full autonomy enforcement remains future work and must be implemented through the permission/runtime boundary, not inside UI.

## Consequences

- Agent capabilities can grow without granting unsafe authority.
- Approval flows can be added without rewriting tools.
- Future schedulers must check autonomy before acting.

