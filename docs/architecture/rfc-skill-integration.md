# RFC and Skills integration

Skills Phase 1 remains frozen. Optional manifest fields declare whether a Skill
requires a project, which change classes require an RFC, allowed RFC states,
consumed RFC sections, produced evidence types and required quality gates.

`SkillResolutionRequest` may carry project/RFC/plan classification references.
Skills reads bounded project summaries through `ProjectContextReadPort`; it
does not import `ProjectGovernanceRuntime`, load RFC history or receive a gate
bypass. Skill scripts and quality gates continue through Tool Execution.

No Skill generation, mutation, promotion, benchmarking loop or self-evolution
was introduced.
