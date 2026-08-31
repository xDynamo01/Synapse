# Dynamic Swarm Workforce

`EphemeralWorkforcePlanner` decides whether a mission needs temporary specialists.
Inputs are the mission objective/DAG, capability/tool requirements, persistent
agents, Workers, resource pressure, model capabilities and conservative limits.

A simple task without specialist requirements returns `persistent_only`. Complex
or explicitly specialist work yields `EphemeralWorkforcePlan`: reason, specs,
bounded concurrency, execution order, strategy, resource estimate, warnings and
approval requirement. Critical resource pressure defers creation; high/moderate
pressure can reduce the plan to sequential execution.

The applied flow is:

`Mission plan → workforce decision → EphemeralAgentInstance → Worker assignment → TaskAttempt → verified result → Swarm consolidation → cleanup`

Swarm records temporary member IDs and annotates matching mission tasks. Dispatch
uses the ephemeral operational identity while preserving Worker as executor and
TaskAttempt as execution history. Results contain references, evidence,
verification and provenance; scratchpads are never concatenated into the primary
agent's memory. Existing Memory Commit Policy remains the authority for any later
durable consolidation.
