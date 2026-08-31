# Platform Policy

`EffectivePolicyRuntime` is the canonical policy service. Its generic boundary is
`evaluate_policy(subject, action, resource, context=None)`; the legacy
`resolve(context, agent_id)` adapter remains stable for frozen agent/tool flows.

Rules use `PolicyRule`: ID, scope, subject, action/resource patterns, effect,
conditions, priority, source, timestamps, expiry, metadata, and revision. Scopes
are system, user, agent, conversation, mission, task, tool, model, voice, and
perception. Effects are allow, deny, require approval, require confirmation,
constrain, and audit only.

Resolution is deterministic. Expired rules are ignored. Explicit deny wins,
then approval/confirmation/constraints, with scope order system → user → agent →
conversation → mission → task → tool → model → voice → perception. Priority and
rule ID break ties. No match is default deny. Every result includes matched
rules, winner, constraints, reasons, trace ID, provenance, and evaluation time.

Autonomy levels are observe-only, suggest, reversible, local, external, and
critical. A requested level above an effective ceiling is denied or requires
approval when an approval rule matches. Revision checking prevents stale rule
updates; each mutation writes immutable history. No policy cache is used, so
stale-cache invalidation is not a failure mode.
