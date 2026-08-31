# Synapse V2 Agent-Agnostic Audit

Date: 2026-06-19

Scope: search for hardcoded references to `artemis`, `hermes`, `atlas`, `vigil`, and `researcher` across runtime code, seeds, tests, docs, and ADRs. This audit does not implement fixes.

## Executive Summary

Most runtime layers are agent-agnostic: Worker, Lifecycle, Presence, Tools, EffectivePolicy, Approval System, Agent-to-Agent Communication, and most API routes operate on `agent_id` inputs rather than fixed agents.

Update: the Communication/email path no longer treats `hermes` as the default communication agent. Runtime calls, commands, API routes, and scheduler `check_email` jobs now require an explicit agent id or resolve `communication.default_agent_id` from `data/config/communication_policy.yaml`. The default seed policy sets this value to null.

No critical architectural error was found in Worker, Lifecycle, Presence, EffectivePolicy, Approval System, or generic Tools.

## Classification Key

1. OK seed/demo/test
2. OK documentation/example
3. Risk conceptual
4. Architectural error

## Runtime Occurrences

| Location | Occurrence | Classification | Risk | Recommendation | Correct Now |
|---|---:|---|---|---|---|
| `backend/synapse/core/data_dir.py` | Base seed agents `artemis`, `researcher`, `atlas`, `hermes`, `vigil` | 1. OK seed/demo/test | Low | Keep as bootstrap seeds, but document that they are replaceable examples. | No |
| `backend/synapse/core/data_dir.py` | Artemis seed rule "Delegate research tasks to Researcher" | 1. OK seed/demo/test | Low | Acceptable as seed personality content. Avoid using this rule outside seed data. | No |
| `backend/synapse/communication/runtime.py` | Former `create_draft(..., created_by_agent="hermes")` | 3. Risk conceptual | Medium | Corrected: caller must pass `created_by_agent` or configure `communication.default_agent_id`. | No |
| `backend/synapse/communication/runtime.py` | Former `generate_briefing(agent_id="hermes")` | 3. Risk conceptual | Medium | Corrected: caller must pass `agent_id` or configure `communication.default_agent_id`. | No |
| `backend/synapse/communication/runtime.py` | Former briefing text `Hermes analyzed ...` | 3. Risk conceptual | Medium | Corrected: summary uses `Communication agent <agent_id> analyzed ...`. | No |
| `backend/synapse/commands/runtime.py` | Former `/check-email` hardcoded Hermes | 3. Risk conceptual | Medium | Corrected: `/check-email --agent <agent_id>` or configured default. | No |
| `backend/synapse/api/routes.py` | Former `DraftRequest.created_by_agent = "hermes"` | 3. Risk conceptual | Medium | Corrected: no hardcoded default. | No |
| `backend/synapse/scheduler/runtime.py` | Former `check_email` fallback to Hermes | 3. Risk conceptual | Medium | Corrected: `payload.agent_id` or configured default required. | No |

## Runtime Areas Without Fixed-Agent Coupling

| Area | Result | Notes |
|---|---|---|
| Agent-to-Agent Communication | Agent-agnostic | Message APIs use `from_agent_id` and `to_agent_id`. References in tests use Artemis/Researcher as fixtures. |
| Notification Runtime | Agent-agnostic | Event mappings are based on event type and payload, not fixed agents. |
| Worker | Agent-agnostic | Processes `agent_id` supplied by command/API/scheduler. Test names use Researcher/Atlas fixtures only. |
| Lifecycle | Agent-agnostic | Methods take `agent_id`; references are test fixtures and docs. |
| Presence | Agent-agnostic | State is persisted by supplied `agent_id`; references are test fixtures and docs. |
| Tools | Mostly agent-agnostic | Builtin tools use `PermissionContext.actor_id`. `create_email_draft` now passes the current actor as draft creator. |
| EffectivePolicy | Agent-agnostic | Resolves by supplied `agent_id`; tests use Artemis as fixture. |
| Approval System | Agent-agnostic | ApprovalRequest stores `agent_id` from context. No hardcoded named agents found. |
| Generic API routes | Agent-agnostic | Agent routes use path/body agent ids. Communication draft request no longer defaults to a seeded agent. |

## Seeds and Local DATA_DIR

| Location | Classification | Risk | Recommendation | Correct Now |
|---|---|---|---|---|
| `data/agents/*` | 1. OK seed/demo/test | Low | Current workspace data can contain seeded agents. Runtime must continue to work if different agents exist. | No |
| `data/config/permissions.yaml` | 1. OK seed/demo/test | Low | Local permissions are expected to name actual local agents. | No |
| `data/config/system.yaml` | 1. OK seed/demo/test | Low | `default_agent_id = artemis` is local config, not runtime logic. | No |

## Tests

Tests contain many references to Artemis, Researcher, Atlas, Hermes, and Vigil. These are acceptable fixtures because the tests validate seeded identities, communication flows, worker inbox processing, scheduler jobs, lifecycle, presence, and policy behavior.

Classification: 1. OK seed/demo/test.

Risk: Low. The only test risk is cultural: tests may accidentally hide future hardcoded defaults by always using seeded names. Add one future regression test with arbitrary agent ids before refactoring agent creation.

Recommendation: keep current tests, but add agent-agnostic regression coverage when custom agent creation/config migration exists.

## Docs and ADRs

Docs and ADRs reference named agents heavily because the walkthrough and ADRs explain the seeded scenario.

Classification: 2. OK documentation/example.

Risk: Low to medium. The docs sometimes describe "Hermes briefing" and "user talks to Artemis" as the canonical flow. That is fine for examples, but docs should explicitly state these are seeded examples, not runtime requirements.

Recommendation: future doc pass should rename some headings to "example: Artemis" or "seeded Hermes communication agent" to avoid implying architectural dependence.

## Architectural Findings

### Finding A: Communication Runtime Had Hermes Defaults

Classification: 3. Risk conceptual.

Affected files:

- `backend/synapse/communication/runtime.py`
- `backend/synapse/commands/runtime.py`
- `backend/synapse/api/routes.py`
- `backend/synapse/scheduler/runtime.py`

Risk:

Communication was framed as Hermes-owned behavior. If another agent needed email briefing or draft creation, callers had to override defaults manually. Scheduler `check_email` could run as Hermes when the recurring job omitted `agent_id`, making homelab behavior depend on a seeded agent.

Recommendation:

Implemented a small communication policy/config value:

```yaml
communication:
  default_agent_id: null
```

Then replace hardcoded defaults with explicit config resolution, or require `agent_id` in commands/API/scheduler jobs.

Correction required now: Completed. The default value is null, so communication work must provide an agent or intentionally configure one.

### Finding B: Communication Summary Text Names Hermes

Classification: 3. Risk conceptual.

Affected file:

- `backend/synapse/communication/runtime.py`

Risk:

Previously, if `generate_briefing(agent_id="some_agent")` was called, the returned summary still said "Hermes analyzed ...".

Recommendation:

Implemented summary formatting from the resolved `agent_id`.

Correction required now: Completed.

### Finding C: Seeds Are Embedded in Bootstrap Code

Classification: 1. OK seed/demo/test.

Affected file:

- `backend/synapse/core/data_dir.py`

Risk:

Low. This is acceptable as bootstrap seed data, not runtime branching. The important constraint is that runtime services must not special-case these ids.

Recommendation:

Keep seeds for local-first onboarding. Future custom agent creation should make seed installation optional/idempotent and documented.

Correction required now: No.

## Module-by-Module Verdict

| Module | Verdict |
|---|---|
| Communication Runtime | Agent-agnostic after correction; requires explicit/configured communication agent. |
| Notification Runtime | Agent-agnostic. |
| Scheduler | Agent-agnostic after correction; `check_email` requires explicit/configured communication agent. |
| Worker | Agent-agnostic. |
| Lifecycle | Agent-agnostic. |
| Presence | Agent-agnostic. |
| Commands | Agent-agnostic after correction; `/check-email` accepts `--agent`. |
| API | Agent-agnostic after correction; draft request has no seeded creator default. |
| Tools | Agent-agnostic at execution time. |
| EffectivePolicy | Agent-agnostic. |
| Approval System | Agent-agnostic. |
| Docs and ADRs | Example-heavy; acceptable, but should be clarified over time. |

## Critical Findings

No classification 4 architectural errors were found.

Highest-severity finding was corrected: Hermes is no longer the implicit default communication agent in Communication Runtime, Command Runtime, API draft creation, or Scheduler `check_email`.

## Recommendations

1. Keep `communication.default_agent_id` null by default unless the user explicitly chooses a communication agent.
2. Add custom-agent creation tests once agent creation is implemented.
3. Add a short note in future user docs that Artemis/Hermes/etc. are seeds, not runtime dependencies.
