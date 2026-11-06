# DOC-0001 — Synapse 0.3 documentation foundation

## Baseline inventory

The pre-0.3 snapshot contained 381 Markdown documents:

| Area | Count | Initial assessment |
|---|---:|---|
| ADR | 95 | Strong decision volume; needs status/supersession verification. |
| Audits (`audits/` + `audit/`) | 77 | Rich evidence history; many reports are slice-specific and not a current system view. |
| Architecture | 58 | Broad coverage; requires reconciliation with the current composition roots and runtime wiring. |
| Backend | 55 | Many bounded contexts documented; implementation status must be re-established from code. |
| Validation | 51 | Useful evidence, but inherited results cannot be treated as current PASS. |
| Root/project documents | 16 | Multiple entry documents overlap and declared version remains `0.1.0`. |
| Voice | 8 | Material coverage with recent local-provider changes. |
| Frontend | 6 | Product/contracts/theme docs exist; end-to-end consumer mapping remains incomplete. |
| Development | 6 | Workflow and ownership guidance exists; clean-room reproduction is absent. |
| Other | 9 | Providers, MCP, operations, roadmap, templates, references and legacy. |

The inventory is evidence of documentation volume, not completeness or accuracy.

## Separation rule

Every normative document declares one of:

- `CURRENT_STATE`: confirmed against the cited revision and symbols;
- `TARGET_0_3`: proposed architecture, not an implementation claim;
- `HISTORICAL`: evidence of a past decision or execution;
- `PROCEDURE`: reproducible instructions with validation status.

Unsupported retrospective history is prohibited. Unknowns remain explicit.

## Stable identifiers

| Prefix | Meaning |
|---|---|
| `PRJ` | vision, requirements, roadmap and project governance |
| `ARCH` | system architecture, boundaries, contracts and composition |
| `CAP` | capability or relevant module/service/tool |
| `DEV` | environment, build, packaging and recovery procedure |
| `TEST` | quality strategy or test catalogue |
| `EVD` | an executed evidence record |
| `OPS` | operational, backup or restoration procedure |
| `SEC` | security model, boundary or assessment |

Existing ADR numbers remain stable and are not renumbered.

## Proposed information architecture

```text
docs/
  project/          PRJ vision, requirements, principles, roadmap
  architecture/     ARCH current-state and target-state views
  capabilities/     CAP documents using capability-template.md
  development/      DEV environment, build, providers and troubleshooting
  testing/          TEST strategy, catalogue and operational gates
  evidence/         EVD current reproducible runs
  operations/       OPS backup, restore and packaged-runtime procedures
  security/         SEC trust boundaries and threat/risk documents
  engineering/      Codex engineering workflow and skill catalogue
  templates/        stable document and evidence templates
  v0.3/             mission control documents for the restructuring
```

Existing documents are not moved in Mission 0.3.0. Mission 0.3.1 first maps each
document to this structure, confirms consumers and marks duplicate/superseded
material before any consolidation.

## Gap matrix

| Required coverage | Existing evidence | Gap / next action |
|---|---|---|
| Vision, requirements and principles | README, roadmap and product spec | Reconcile naming/version and separate current behavior from 0.3 goals. |
| System overview and bounded contexts | `docs/architecture*`, backend docs and 95 ADRs | Produce one code-grounded context map and dependency graph. |
| Contracts/adapters/composition roots | Architecture tests and many module docs | Trace actual registrations and consumers; identify orphan ports/adapters. |
| States and lifecycle | Per-context docs and tests | Normalize state-machine and recovery evidence per capability. |
| Frontend-to-runtime flows | Frontend contracts and Electron tests | Map every visible control through IPC/API to a real final consumer. |
| Security/trust boundaries | `docs/security.md`, sandbox/security tests | Refresh threat model after full entrypoint/integration inventory. |
| Providers/models/voice | Provider, model and voice docs | Separate configured/discovered/available/operational states. |
| Memory/RAG/persistence | Memory docs and recent implementation | Trace storage ownership, schemas, replay, lifecycle and operational persistence. |
| Skills/tools/MCP | Runtime docs, tests and engineering catalogue | Keep runtime skills separate from Codex skills; map tool receipts and permissions. |
| Clean environment reproduction | Partial development/build documents | Build and later validate `SYNAPSE_FROM_ZERO.md` in an independent environment. |
| Test catalogue and evidence | 380 Python test files plus frontend tests | Assign requirement/capability IDs and distinguish mock/static/integration/operational proof. |
| Windows build/package/recovery | Scripts and historical audits | Reproduce from clean clone and validate the final executable, startup and restart. |

## Capability documentation contract

Relevant capabilities use `docs/templates/capability-template.md` and must identify
responsibility, files/symbols, implementation state, inputs/outputs/contracts,
dependencies/consumers, registration, initialization, flows, states, permissions,
failures, observability, configuration, examples, tests, evidence and limitations.
Trivial private helpers remain documented through their owning capability rather
than receiving redundant documents.

## Documentation plan

1. Mission 0.3.1 inventories code, tests and current documents without refactoring.
2. Create current-state capability records and integration matrix from code evidence.
3. Mark historical evidence and superseded documents without deleting them.
4. Approve target 0.3 architecture through RFCs and ADRs.
5. Update capability docs and evidence alongside each bounded mission.
6. Complete and independently execute `SYNAPSE_FROM_ZERO.md` before release.
