# Project Governance + RFC inventory

Date: **2026-07-15**

This inventory was completed before any Project Governance document migration.
It records the authorities that existed at the start of the phase and prevents
RFC, ADR, Mission Plan, evidence and operational documentation from being
collapsed into one concept.

## Concept matrix

| Concept | Current implementation | Format | Authority | Consumers | Persistence | Revision/checksum | Problem | Destination |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `project_id` | Optional correlation field in Chat, Context, Tasks, Approvals, Tools and Skills | string embedded in DTO/metadata | each owning runtime | agents, conversations, context, approvals, tools | owner-specific YAML/JSON | owner-specific; no project revision | no canonical identity or lifecycle | `ProjectManifest` + `ProjectRegistry` |
| `workspace_id` | Primary Agent identity namespace and Skills resolution input | string | Primary Agent / Skills | primary bootstrap, skills resolver | `primary_agents/` and skill records | runtime-specific | workspace is incorrectly usable as a project surrogate | remain a separate namespace |
| Project context | direct reads of `projects/{project_id}/PROJECT.md` and `MEMORY.md` | Markdown | `ContextLoader` filesystem convention | agent context | project directory; currently empty in seed data | none | no validation, provenance, classification or budgeted governance | `ProjectContextReadPort` backed by `ProjectContextRuntime` |
| Project scope in Skills | `SkillScope.PROJECT`, assignment metadata and `load_assigned(project_id=...)` | dataclasses/YAML metadata | Skills Runtime | Context Loader and agents | Skills Storage adapters | assignment revision | project reference is not validated by a project authority | neutral Project/Skills bootstrap integration |
| RFC | no canonical runtime or RFC package exists | scattered prose only | none | maintainers | repository docs | Git history only | proposals cannot be validated, revised, reviewed or gated | human-editable RFC package + `RFCRegistry` |
| ADR | 91 documents under `docs/adr/` | Markdown | architecture maintainers | developers/auditors | repository | filename/history; no runtime checksum | durable decisions are not queryable by project | small `ADRRegistry`; existing ADRs remain historical and are not auto-migrated |
| Implementation plan | `MissionPlan`/`PlannerRuntime` owns executable task DAGs | YAML/dataclasses | Missions | Mission Runtime, workers, swarm | `missions/{id}/plans/` | version only; no RFC binding | execution DAG is not a governance implementation plan | separate `ImplementationPlanRegistry`, optionally bound to Mission |
| Mission objective | `Mission.objective` and task objectives | YAML/dataclasses | Missions | planners/workers/agents | `missions/` | mission revision | no immutable project/RFC/plan tuple | `RFCImplementationBinding` carried in mission metadata/contracts |
| Task plan | `MissionTask`, dependencies and validation | YAML/dataclasses | Missions Planner | scheduler/workers | mission plan files | plan version | no RFC freshness check | Mission remains execution authority; RFC Gate validates its binding |
| Evidence | worker results, attempts, consolidated swarm results and validation reports | nested DTOs, YAML, Markdown | each producer | Mission verifier, operators | mission records and `docs/validation/` | inconsistent | no canonical provenance/classification or acceptance linkage | `EvidenceRegistry` with safe artifact references |
| Acceptance criteria | mission `completion_criteria`, verifier checks and prose DoD sections | dict/prose | mission or document owner | verifiers/humans | mission plan/docs | none or plan version | not individually addressable or waivable | structured `AcceptanceCriterion` records |
| Approval | `ApprovalManager` and Effective Policy | YAML/dataclasses | Approvals / Policy | Tools, agents, admin runtimes | `approvals/` | status history without RFC revision binding | generic approvals do not represent RFC review | reuse approval authority; RFC review stores explicit linked decisions |
| Decision records | `docs/adr`, `docs/decisions/0001-runtime-first-foundation.md`, decision runtime results | Markdown/dataclasses | architecture / Decision Runtime | humans and policy consumers | docs/runtime event data | heterogeneous | policy decisions and architectural decisions are conflated by naming | ADR Registry for architecture; RFC Review for proposal decisions |
| Project memory | direct `projects/{id}/MEMORY.md`; Memory scopes exclude project | Markdown | Context Loader convention | agent context | project file | none | may duplicate source-of-truth content | project-owned indexed summaries with RFC provenance; RFC remains authoritative |
| Project-specific skills | project-scoped Skill assignments | package + assignment records | Skills Runtime | agents/swarm | `skills/` collections | assignment/package revisions and checksum | project existence and RFC requirements are not governed | Skills consumes project/RFC summaries through neutral contracts |
| Repository paths | `DataDir` relative paths; docs mention repository/worktrees | relative path strings | DataDir and each runtime | filesystem adapters | local filesystem | none | no safe public root reference and Git cannot be assumed | opaque/relative `root_reference` resolved only by bootstrap adapter |
| Hardcoded project references | `ContextLoader` uses `projects/{project_id}/PROJECT.md` and `MEMORY.md`; test metadata uses `synapse` | relative convention/test fixture | Context Loader/tests | agents/test suite | DataDir/test data | none | implicit structure without registry | replace consumption with project context port; preserve compatibility adapter |
| Quality gates | pytest, Ruff, architecture checks, OpenAPI snapshots and tool definitions | commands/docs/tool descriptors | existing Tool Runtime and maintainers | CI/manual validation | logs/reports | execution-specific | no plan/RFC descriptor or evidence link | `QualityGateDescriptor` references executed through Tool boundary |
| Evals | no Private Evals Runtime | none | none | none | none | none | future acceptance criteria lack a safe reference contract | reference-only `EvalReference`; private payload export prohibited |

## Existing document classification

| Class | Existing material | Classification result | Migration decision |
| --- | --- | --- | --- |
| A. Real RFC | none found | no Markdown + structured manifest + revisions/reviews package exists | create the canonical format; do not relabel old documents |
| B. ADR | 91 files in `docs/adr/`; one foundation decision in `docs/decisions/` | durable architectural decisions | retain in place; register new project ADRs prospectively |
| C. Implementation plan | Mission plans under runtime data; planning prose in audits/roadmaps | executable DAGs or informal plans, not RFC-bound implementation plans | keep Mission plans distinct; create a new registry |
| D. Validation report | 64 files in `docs/validation/` including Markdown, JSON and CSV evidence | phase reports and frozen validation artifacts | retain as historical evidence; never auto-import payloads |
| E. Current architecture | 23 files in `docs/architecture/`, root architecture/backend/security/API docs | current normative technical documentation | keep as current documentation; reference from RFCs/ADRs when needed |
| F. Historical snapshot | JSON/CSV in `docs/audit/` and reports in `docs/audits/` | point-in-time graph, surface and project-state snapshots | retain unchanged unless a new authorized baseline replaces them |
| G. Operational documentation | `docs/development/`, `docs/contributing.md`, `docs/roadmap.md`, runtime walkthroughs | operator/developer guidance | remain documentation, not RFC authority |
| H. Ungoverned content | empty `data/projects/` convention and scattered project metadata | implicit, owner-specific content | govern prospectively through manifests and registries |

## Authority decisions

- Project, RFC, ADR, Implementation Plan, Evidence and Eval remain separate
  records with separate lifecycle and ownership.
- Git, IDEs, frontend frameworks and repository mutation are not dependencies.
- Human-editable Markdown/YAML is authoritative for project packages; Storage
  Primitives retain only operational metadata, indexes and activation pointers.
- Existing documents are not migrated automatically in this phase.
- Generic Approval, Policy, Tool Execution, Skills, Missions and Memory remain
  their existing bounded contexts and are integrated only through neutral ports
  and bootstrap adapters.
