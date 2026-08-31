# Agent Kinds

Status: implemented on 2026-07-14. The backend remains **NOT READY**.

Synapse has exactly three operational agent kinds. Kind is a domain fact, never a
name, folder, role or UI inference.

| Kind | Lifetime | Identity authority | Durable agent directory | Long-term memory |
| --- | --- | --- | --- | --- |
| `primary` | persistent | explicit `PrimaryAgentProfile` referring to a persistent agent | yes | yes |
| `persistent` | persistent | `AgentProvisioningRuntime` and `AgentRegistry` | yes | yes |
| `ephemeral` | leased | `EphemeralAgentRuntime`, created only by Mission/Swarm | never | never |

`AgentProvisioningRuntime` rejects any create request whose kind is not
`persistent`. Selecting that identity as primary changes the operational binding,
not its human-editable agent files. Ephemeral IDs use
`ephemeral:<mission_id>:<unique-id>` and are never registered by `AgentRegistry`.

Worker is an executor and TaskAttempt is execution history; neither is an agent
kind. A persistent agent may coordinate other identities without creating a rigid
permanent parent/child hierarchy.
