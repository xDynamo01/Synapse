# Skills Runtime Phase 1 — current-state inventory

Date: **2026-07-15**

This inventory was completed before any Skills Runtime migration or production
implementation. It is the classification baseline for Phase 1.

## Inventory matrix

| Component | Current responsibility | Format | Consumers | Persistence | Loading | Scope | Permissions | Problem | Phase 1 destination |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `data/agents/*/SKILLS.md` | Short per-agent competence list | Markdown | identity runtime, context loader, model prompt | agent directory | entire file, eager | agent only, implicit | none | duplicated labels; no identity/version/package boundary | preserve as agent-specific legacy instructions; pilot reusable entries as assignments |
| `CONFIG.yaml.skills` | Descriptive skill labels | JSON-compatible YAML list | `AgentConfig`, API serialization, primary-agent capability summary | agent directory | eager with config | agent only, implicit | none | conflates reusable workflow with labels/capabilities | accept legacy read; add structured `skills.assignments` without granting tools |
| `AgentConfig.skills` | List of strings | dataclass field | agents/runtime/API/tests | in-memory projection | eager | agent | separate `permissions` field | no version, status or provenance | compatibility field only; canonical assignments live in Skills Runtime |
| `AgentIdentity.skills` | Raw `SKILLS.md` content | string | ContextLoader, model adapters | file-backed | entire file, eager | agent | none | prompt bloat and no progressive loading | retain only agent-specific instructions; resolved skill instructions supplied through a port |
| `ContextLoader` | Adds `SKILLS.md` as identity context | context section | workers/model request | transient | eager whole file | agent/project task request | existing context policy | bypasses discovery, resolver and budget | consume neutral skill-context port; load selected instructions only |
| model adapters | Append raw identity skills to system prompt | string | model providers | transient | eager | request | none | treats skills as a prompt blob | render only resolved, budgeted skill context plus legacy agent instructions |
| agent provisioning | Creates/updates `SKILLS.md` from focus areas | Markdown | provisioning/admin | staged agent directory | write at provisioning | agent | provisioning policy/approval | copies labels; no assignment validation | optionally declare validated assignments; never copy package contents |
| AgentRegistry | Ensures an empty `SKILLS.md` exists | file convention | identity/runtime | agent directory | none | agent | none | registry is not a skill authority | remain agent authority; Skills Registry is separate |
| Primary Agent | Reports `agent.skills` as capabilities | list | bootstrap/profile API | transient | eager | primary | none | capability/skill terminology leak | expose assignment summaries and availability through port |
| Ephemeral Agent runtime | No skill model | ephemeral instance records | swarm/mission execution | ephemeral runtime files | none | task/mission | resource limits | cannot express bounded reusable workflow | `SkillLease`; audit minimum only after cleanup |
| Ephemeral workforce planner | Plans roles/objectives/resources | dataclasses | swarm | transient/mission plan | eager | mission/task | resource limits | cannot request skills or report gaps | add requested skill IDs; resolver remains external via port |
| Missions/Swarm | Coordinate work and agents | runtime DTOs | agent runtimes | domain stores | normal domain loading | mission/task | existing policy | must not import SkillsRuntime | consume neutral resolution/lease ports wired in bootstrap |
| Capability Runtime | Functional capability registry/policy | structured models | agents/tools/delegation | config/runtime | metadata | agent/system | capability policy | historically confused with skills in docs | classification **E**; remains independent requirement input |
| Tool Runtime | Executable side-effect authority | definitions/execution records | all execution consumers | operational storage | metadata + execution | actor/task | ToolExecutionPort, policy, approval | must not be granted by a skill | classification **D**; scripts execute only through a skill script port backed by ToolExecutionPort |
| Policy/Approval | Permission and risk decisions | policies/requests | privileged operations | operational files | on request | actor/operation | canonical authority | no skill-specific parallel policy allowed | Skills orchestration calls neutral policy/approval ports/adapters |
| Storage Primitives | Generic operational records | FileCollection | bounded contexts | files with revision/checksum | on demand | collection | path validation/locking | no skills collection yet | metadata, assignment, lease, validation and installation records only |
| Existing scripts/resources | No canonical skill packaging | scattered files | domain-specific runtimes | repository/data files | domain-specific | implicit | domain-specific | no safe package-relative contract | package descriptors, checksums, allowlists and progressive loading |
| Seeded agent directories | Six manually authored agents | CONFIG/SOUL/SKILLS/MEMORY/INBOX | bootstrap/runtime/tests | `data/agents` | eager identity | agent | existing permissions | reusable labels duplicated in two files | small documented pilot; preserve all original files/content |
| Documentation/tests | Describe skill as competence text | Markdown/Python | maintainers | repository | n/a | n/a | n/a | no professional runtime contract | replace with explicit SOUL/ROLE/SKILL/TOOL model and executable tests |

## Seeded content classification

| Agent | Existing entries | Classification | Reason / destination |
| --- | --- | --- | --- |
| Artemis | planning, coordination, briefings, delegation | C/F, with delegation partly E | reusable workflows are pilot candidates; delegation authority remains capability/policy |
| Atlas | library, organization, knowledge management | C/F | reusable knowledge-organization workflow candidates; agent preferences stay local |
| Hermes | drafting, summarization, communication triage | C/F; messaging remains D/E | reusable textual workflows; messaging access is not granted by a skill |
| Orchestrator | coordinate_tasks, route_messages, use_core_tools | mostly D/E/G | task/message/tool authority is not a skill; labels are legacy/duplicated |
| Researcher | research, synthesis, analysis | C/F | suitable controlled pilot for a reusable research workflow |
| Vigil | security triage, event reporting, alerting | C/F; camera/tool access remains D/E | reusable triage workflow; sensor/tool authority remains separate |

Classification legend: **A** SOUL, **B** ROLE, **C** reusable SKILL,
**D** executable TOOL, **E** capability, **F** agent-specific instruction,
**G** obsolete or duplicated content.

## Hard boundaries derived from the inventory

- SOUL/personality remains in `SOUL.md`; role remains in agent/workforce DTOs.
- A Skill package is shared and referenced; it is never copied into an agent.
- Capability, permissions, autonomy and tools remain independent authorities.
- Legacy `SKILLS.md` files are preserved until an explicit, evidenced migration.
- Discovery reads manifest metadata, not all `SKILL.md` bodies.
- Context Fusion/agents/missions/swarm receive neutral ports and never import a
  concrete Skills Runtime.
- Phase 1 contains no generation, mutation, evaluation, promotion or
  autoevolution mechanism.
