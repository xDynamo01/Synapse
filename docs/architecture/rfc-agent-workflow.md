# RFC agent workflow

Primary Agent coordinates requested RFC creation/review, presents finite
clarification questions and exposes bounded project context. Persistent Agents
may author or review within assignments and scopes. Ephemeral Agents receive
project/RFC/plan references with their Mission lease, may analyze and produce
evidence, and cannot approve permanently.

The governed flow is:

`RFC -> Implementation Plan -> Mission -> Tasks -> Workers/Agents -> Attempts -> Evidence -> Acceptance -> implemented`.

Swarm may plan, review, implement, verify and collect evidence. It cannot
approve a critical RFC alone, change active scope, rewrite the RFC during
execution or ignore a stale plan. Cleanup retains only required evidence and
audit metadata.
