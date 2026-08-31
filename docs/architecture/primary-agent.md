# Primary Agent

`PrimaryAgentRuntime` owns one explicit primary binding per workspace/profile. It
references a valid persistent agent and one durable main conversation. It does not
execute models, tools, chat turns, missions, Agent Loop cycles, voice capture or UI.

`PrimaryAgentProfile` stores agent/workspace IDs, status, assignment time,
conversation ID, interaction/proactive modes, voice preference, activity times,
revision and redacted metadata. It does not copy CONFIG, SOUL, SKILLS or memory.

Canonical sequence:

1. Provision a persistent agent through `AgentProvisioningRuntime`.
2. Explicitly assign or replace the workspace primary.
3. Create one conversation through `ConversationRuntime` and persist its ID.
4. Read `PrimaryInteractionBootstrap` to resume client state.
5. Pause/resume the conversation explicitly; never start microphone, camera or an
   action as a bootstrap side effect.

If no persistent agents exist, state is `primary_agent_required`. If agents exist
without a primary, state is `primary_selection_required`. A missing/corrupt target
is `misconfigured`; another agent is never selected silently. Admin cannot
deactivate, archive or delete the active primary until explicit replacement.

The bootstrap is frontend-agnostic: identity, conversation, bounded status/counts,
capabilities, warnings and a revision resume token. It contains no pane, tab,
layout, theme or framework state. Restart reloads profile/conversation but does not
restart voice capture or generate a message.
