# Activity conversation scope

Status: implemented in the F workspace; automated regression passing.

Operational activity now accepts a conversation scope when an event has no
`project_id`. The projection runtime derives the canonical scope
`conversation:<conversation_id>` from the event payload, preserving exact
conversation isolation without fabricating a project. Project-scoped endpoints
remain unchanged.

The frontend selects the project scope when bootstrap provides one and falls
back to the active conversation scope otherwise. The same normalized snapshot
and stream contracts feed `activityAdapter` and Pixi, so nodes and relations
are derived only from emitted operational events.

Regression evidence: conversation-scoped `agent.started` events produce a
processing Primary Agent entity; project projection tests continue to pass.
