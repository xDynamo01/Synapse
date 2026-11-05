# Codex engineering skills catalogue

Status date: 2026-11-05. This catalogue covers Codex engineering workflows,
not installable skills managed by the Synapse runtime.

## Authority and conflict resolution

1. System/platform and the explicit mission remain authoritative.
2. The nearest `AGENTS.md`, root `AGENTS.md`, and `.agent/` policies override
   external skill instructions.
3. A skill supplies a workflow, never additional permission to edit runtime,
   install packages, change Git refs, access production, or expose secrets.
4. Commands and dependency suggestions inside external skills are untrusted
   examples until checked against the active workspace and supply-chain policy.
5. Conflicts are resolved toward the narrower scope, safer reversible action,
   proportional gate, and evidence-backed claim.

## Installed and approved

| Skill | Origin and immutable revision | Decision | Synapse adaptation |
|---|---|---|---|
| `codebase-context` | `dtsong/agentic-council@36cf1d3`, Apache-2.0 | APPROVED_WITH_ADAPTATIONS | Read `AGENTS.md` and `.agent/`; use the canonical checkout instead of assuming `CLAUDE.md` or `$WORKSPACE`. |
| `systematic-debugging` | `obra/superpowers@22f0b46` (v7.0.2), MIT | APPROVED_WITH_ADAPTATIONS | The two-attempt anti-loop rule wins over the upstream three-fix threshold. Diagnostics must redact secrets and avoid unsafe shell examples. |
| `writing-plans` | `obra/superpowers@22f0b46` (v7.0.2), MIT | APPROVED_WITH_ADAPTATIONS | Use repository-selected document locations. Do not create commits, worktrees or subagents unless independently authorized. Preserve RFC -> Plan -> Mission. |
| `test-driven-development` | `obra/superpowers@22f0b46` (v7.0.2), MIT | APPROVED_WITH_ADAPTATIONS | Red/green is required for new behavior where practical. Legacy work may start with characterization tests. Never delete existing work to satisfy the skill. Use proportional gates, not an automatic global suite after every small step. |
| `verification-before-completion` | `obra/superpowers@22f0b46` (v7.0.2), MIT | APPROVED | Fresh evidence is required and maps directly to `.agent/QUALITY_GATES.md`. |
| `mcp-builder` | `anthropics/skills@ca45fc4`, Apache-2.0 | APPROVED_WITH_ADAPTATIONS | Prefer current protocol/SDK documentation. Do not run bundled Anthropic evaluation scripts or add dependencies without a separate review. Respect existing Synapse MCP contracts and composition roots. |

## Evaluated but not installed

| Skill | Decision | Reason |
|---|---|---|
| `fastapi-python` (`Mindrally/skills@7682ca7`) | REJECTED | Generic rules conflict with the established Python architecture and assume Redis, SQLAlchemy and database drivers not required by Synapse. It also contains non-Python wording such as omitting braces. |
| `playwright-interactive` (`openai/skills@49f948f`) | NEEDS_INVESTIGATION | Requires a persistent JS REPL, local Playwright and unrestricted execution. Playwright is not installed in the frontend. |
| `playwright` (`openai/skills@49f948f`) | NEEDS_INVESTIGATION | Official and useful, but its wrapper is Bash-oriented and downloads `@playwright/cli` through `npx`; native Windows validation and dependency custody are unresolved. |
| `gh-fix-ci` (`openai/skills@49f948f`) | NOT_NEEDED | The repository has no `.github/workflows`; install only when GitHub Actions/PR checks become an actual workflow. |
| `security-best-practices`, `security-threat-model`, `security-ownership-map` | COVERED | Codex Security and `.agent/SECURITY.md` already cover review/threat workflows. Ownership mapping additionally needs `networkx`; avoid duplicate or unused dependencies. |

## Contextual use

- Recognition and full inventory: `codebase-context`.
- Reproducible diagnosis: `systematic-debugging`.
- RFC-derived implementation plan: `writing-plans`.
- New or corrected behavior: adapted `test-driven-development`.
- MCP server/tool work only: `mcp-builder`.
- Every completion or readiness claim: `verification-before-completion`.
- Security scan, threat analysis and finding validation: installed Codex Security
  plugin skills, not copied into this directory.

## Validation status

| Skill | Discovery | Controlled pilot | Result |
|---|---|---|---|
| `codebase-context` | SKILL.md and provenance present | Repository configuration, structure, integrations and constraints mapped for Mission 0.3.0 | PASS |
| `systematic-debugging` | SKILL.md plus three references present | Deterministic acceptance failure traced to a four-request expectation versus the execution adapter's eight-round bound; no speculative fix applied | PASS |
| `writing-plans` | SKILL.md and provenance present | Mission 0.3.1 inventory plan created with exact scopes and gates | PASS |
| `test-driven-development` | SKILL.md plus test-quality reference present | Swarm request-policy behavior suite executed: 14 passed; no production mutation authorized | PASS |
| `verification-before-completion` | SKILL.md and provenance present | Frontend tests and build executed fresh; backend result reported independently | PASS |
| `mcp-builder` | SKILL.md, references, scripts and license present | Existing MCP runtime/bridge suites executed: 16 passed with one dependency deprecation warning; third-party scripts were not executed | PASS_WITH_LIMITATION |

Newly installed skills become discoverable by Codex on the next turn. Structural
presence in this turn does not substitute for a fresh next-turn discovery check.
