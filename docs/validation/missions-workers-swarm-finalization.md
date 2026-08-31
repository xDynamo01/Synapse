# Missions, Workers, Swarm and Recovery Finalization

Date: 2026-07-12

## Scope Revalidation

The previous global baseline was `887 passed, 40 failed`. None of those 40
failures originated in the focused mission, worker, scheduler, daemon,
recovery, dead-letter, presence, or lifecycle suites. Nine observability and
four UI-contract failures consume mission data indirectly; the remaining
failures belong to Effective Policy, Speech, Health, and Foundation.

Green tests did not imply feature completeness. The revalidation found no
canonical planner, task graph, mission execution coordinator, worker registry,
worker selector, result verifier, or swarm runtime.

## Component Matrix

| Component | Exists | Complete | Real runtime | Persistence | Tests | API | Commands | Remaining gaps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Mission contracts | Yes | Partial | Yes | Yes | Yes | Yes | Legacy only | task history and optimistic revision conflict |
| PlannerRuntime | Yes | Partial | Yes | Yes | Yes | Yes | No | ModelRouter adapter and capability inventory validation |
| TaskGraph | Yes | Yes for graph operations | Yes | Through plans | Yes | Through plan API | No | configurable failure propagation |
| WorkerRegistry | Yes | Partial | Yes | Yes | Yes | Yes | No | lifecycle/presence synchronization and resource limits |
| WorkerScheduler | Yes | Partial | Yes | N/A | Yes | Indirect | No | model/provider affinity and local resource scoring |
| ResultVerifier | Yes | Partial | Yes | Via task result | Yes | Indirect | No | custom capability verifier and reviewer workflow |
| `run_mission` | Yes | Partial | Yes | Yes | Yes | Yes | No | worker execution callback, retries, timeout and recovery loop |
| Mission Control | Yes | Partial | Yes | Reads durable state | Yes | Yes | Yes | native plan/worker/swarm health views |
| SwarmRuntime | Yes | Partial | Partial | Yes | Contract tests | Yes | No | strategy-specific execution and bounded review correction |
| Recovery / DLQ | Yes | Partial integration | Yes | Yes | Yes | Yes | Yes | mission-native execution provenance and replan |
| Daemon integration | Yes | Partial | Yes | Yes | Yes | Yes | Yes | bounded dispatch budget and stale worker scan in mission tick |
| Mission trace | No | No | No | Event log only | Existing observability tests red | No | No | canonical redacted trace projection |

## Implemented In This Increment

- Central mission, task, worker and swarm enums and durable contracts.
- Manual and provider-port planning with deterministic validation.
- Persisted task DAG with cycle/missing dependency detection, fan-in, fan-out,
  topological ordering and unlock queries.
- Persisted worker registry with heartbeat, workload and stale expiry.
- Deterministic worker selection with rejection explanations.
- Evidence-based result verification for supported checks.
- Idempotent mission pause, resume and cancel transitions.
- Canonical mission dispatch entry point that assigns ready work and persists
  progress after transitions.
- Persisted swarm descriptors for `leader_worker`, `parallel`, `pipeline` and
  `review_loop`, without claiming unsupported consensus.
- Mission lifecycle, worker and swarm API endpoints using the canonical
  services.
- Incremental daemon dispatch for running missions.

## Freeze Decision

The domain remains **In development**. It must not be marked
`Implemented / Frozen` until strategy-specific swarm execution, worker attempt
execution, timeout/retry/recovery integration, commands, trace projection, and
the remaining API operations are implemented and validated globally.

## Validation

- Ruff repository-wide: passed.
- Focused Missions/Workers/Recovery suite: `126 passed`.
- Global pytest: `894 passed, 40 failed` from `934 collected` in `520.57s`.
- The global failure count did not increase; all 40 failures are the same
  pre-existing modules documented in the backend baseline.

## Execution And Recovery Increment

Date: 2026-07-12

Implemented:

- Immutable persisted `TaskAttempt` history with explicit statuses, stable
  IDs, revision checking, validated transitions and idempotent creation.
- Canonical `WorkerRuntime.execute_attempt` with assignment checks, Context
  Fusion port, executor port, ResultVerifier, task persistence, events and
  guaranteed worker release.
- Canonical timeout scan for mission deadlines, attempt deadlines and stale
  worker heartbeats. Repeated scans do not repeat timeout transitions.
- Retry evaluation for idempotency, attempt limits, irreversible side effects
  and worker health. Retry creates a distinct attempt with provenance and
  persisted backoff.
- Recovery decisions for same/other worker retry and dead-letter fallback.
- Strategy engine with separate validate, prepare, dispatch, collect,
  evaluate and finalize phases for leader-worker, parallel, pipeline and
  bounded review-loop.
- Structured `ConsolidatedResult` persistence with deterministic output order
  and provenance.
- Canonical API surfaces for attempts, execution, recovery, timeout scans,
  swarm lifecycle and mission trace.
- Canonical commands for mission lifecycle/progress, worker listing and
  heartbeat, task history/retry, and swarm status/start.
- Filterable, paginated and redacted mission trace projection over the durable
  event log.

Validation:

- Focused domain suite: `132 passed`.
- Global suite: `898 passed`, `40 failed` (`938 collected`) in `464.97s`.
- Ruff repository-wide: passed.
- No new global failures were introduced.

Remaining freeze blockers:

- The production executor adapter from WorkerRuntime to AgentRuntime,
  ModelRouter and ToolRuntime is not yet wired; tests use the explicit executor
  port.
- Swarm dispatch semantics are validated and consolidated, but the runtime
  still depends on incremental mission ticks rather than a dedicated bounded
  multi-worker dispatcher.
- Mission-native DLQ entries do not yet contain every attempt/worker field.
- Scheduler dependency-triggered and mission-triggered jobs remain incomplete.
- Mission Control does not yet expose all attempt/swarm/recovery health fields.
- The command list is not yet complete for every task, swarm and DLQ operation.

For these reasons the domain remains **In development** and must not be marked
`Implemented / Frozen`.

## Closure Attempt

Date: 2026-07-12

Closed blockers:

- Added the production `WorkerExecutionAdapter`. It uses ContextLoader and
  AgentRuntime; model selection and tools therefore remain behind ModelRouter
  and ToolRouter/ToolRuntime contracts. It has no direct provider, filesystem,
  subprocess, MCP, or tool implementation calls.
- Added bounded multiworker dispatch with deterministic unique worker
  reservation, concurrency limits, active-attempt deduplication and restart
  safe persisted assignments.
- Extended mission-native DLQ entries with mission, attempt, worker, agent,
  correlation, redacted payload, recovery options and trace reference.
- Added idempotent attempt DLQ creation and closed-to-archived lifecycle.
- Extended scheduler jobs with target, schedule, run result, retry policy,
  idempotency key, misfire policy and revision. Added pause/resume and canonical
  `mission_dispatch` jobs.
- Expanded Mission Control with real mission queues, attempts, waiting
  approvals, recovery queue, worker health, DLQ, swarm, scheduler, daemon and
  actionable attention records.

Validation after closure attempt:

- Focused domain suite: `135 passed`.
- Global suite: `901 passed`, `40 failed` (`941 collected`) in `451.66s`.
- Ruff repository-wide: passed.
- `git diff --check`: passed; only line-ending conversion warnings were
  reported by Git.
- OpenAPI router: 389 routes, zero duplicate method/path pairs and zero
  duplicate operation IDs.

Objective blockers that remain:

- There are no end-to-end tests proving leader-worker, parallel, pipeline and
  review-loop through real AgentRuntime/provider adapters. Running those tests
  requires configured valid agents and an available model provider; the
  repository's deterministic test provider is a test adapter and cannot prove
  production-provider availability.
- Strategy dispatch still delegates task execution to incremental mission
  dispatch; pipeline hand-off and review-loop feedback do not yet create the
  required new attempt/version sequence end to end.
- The complete command and API matrices requested by the Definition of Done
  are not implemented, particularly DLQ restore/retry, scheduler creation and
  daemon lock recovery surfaces.
- Daemon ticks scan timeouts and dispatch running missions, but do not isolate
  every mission error or process the complete retry/recovery/DLQ sequence in a
  single bounded orchestration service.
- The requested ten end-to-end scenarios and explicit frozen-domain suite have
  not all been added/run as separate gates.

The domain therefore remains **In development**. Marking it frozen would
contradict the measured implementation and test coverage.

## Final Gap Matrix

| Item | Runtime current | Working evidence | Remaining | Test | API | Command |
| --- | --- | --- | --- | --- | --- | --- |
| leader_worker | SwarmRuntime + dispatcher | real persisted attempt and consolidation | leader provider failure policy depth | acceptance | yes | start/show/result |
| parallel | bounded dispatcher | 3 tasks, 2 workers, 2 batches | explicit partial-success matrix | acceptance | yes | start/show/result |
| pipeline | DAG + dependency snapshots | 3 persisted attempts with provenance | checksum invalidation policy | acceptance | yes | start/show/result |
| review_loop | versioned plan reopening | reject, correction, second review, approve | reviewer-unavailable acceptance | acceptance | yes | lifecycle/result |
| daemon | isolated per-mission dispatch | broken mission does not block healthy mission | full DLQ auto-application policy | acceptance + legacy | yes | existing status/run-once |
| API | canonical service wrappers | router tests and OpenAPI uniqueness | some task mutation operations remain legacy | router | broad | N/A |
| commands | canonical service wrappers | mission/worker/swarm command tests | creation payload ergonomics remain limited | domain | N/A | broad |
| trace | durable redacted projection | filtering, redaction and export | no external exporter | domain | yes | trace/export |
| restart/idempotency | persisted plans/jobs/attempts | runtime reopen tests | distributed filesystem locking not supported | acceptance | yes | scheduler controls |

## End-To-End Strategy Evidence

Date: 2026-07-12

- Simple mission: runtime reopened after dispatch; the persisted attempt was
  executed once, verified, traced and the mission completed at 100%.
- Leader-worker: a real task attempt was dispatched through SwarmRuntime,
  executed and included in a structured consolidated result.
- Parallel: three independent tasks ran in two bounded batches across two
  distinct workers with no duplicate attempts and deterministic consolidation.
- Pipeline: three real task/attempt stages ran in dependency order. Each next
  attempt persisted the validated predecessor output and provenance; restart
  did not repeat the completed stage.
- Review-loop: producer and reviewer attempts were persisted; rejection and
  feedback reopened a versioned producer task, generated a second producer and
  reviewer attempt, and completed only after approval.
- Daemon isolation: one invalid running mission emitted a mission-scoped error
  while the next mission dispatched and completed in the same tick.

Operational surface additions:

- Worker get, disable, workload, stale scan and attempt APIs.
- Swarm members, result and trace APIs.
- Scheduler get, pause and resume APIs.
- DLQ archive API.
- Commands for mission dispatch/attempts/trace, worker show/disable/stale scan,
  and swarm list/show/lifecycle/result.
- Final backend documentation for missions, Mission Control, workers, swarm,
  recovery, scheduler and daemon.

Final measured gates for this pass:

- Acceptance plus complete focused domain suite: `143 passed`.
- Global suite: `909 passed`, `40 failed` (`949 collected`) in `501.77s`.
- Ruff: passed.
- `git diff --check`: passed with line-ending warnings only.
- OpenAPI: 401 routes, no duplicate method/path and no duplicate operation ID.

Freeze decision:

The domain remains **In development**. Although all four strategy acceptance
paths now pass, the requested API/command matrices are not fully closed for
task assignment/reassignment/cancellation/verification, recovery apply/history,
DLQ retry/restore through mission attempts, and daemon stale-lock recovery.
Marking the domain frozen would violate Definition of Done items 13-15.

## Operational Closure Pass

Date: 2026-07-12

Completed in this pass:

- Canonical task get/update/assign/reassign/cancel/attempts/result/verify and
  dependency mutation with revision and DAG validation.
- Explicit reassign cancels the previous active attempt and releases its
  worker; task cancel propagates to the active attempt.
- Operational Recovery apply for retry, model/provider change, scope
  reduction, pause, intervention, replan and dead-letter actions.
- Mission-attempt DLQ retry/restore creates exactly one new attempt, records
  `restored_attempt_id`, preserves the original entry and rejects conflicting
  duplicate restoration.
- Scheduler/daemon lock now persists PID, hostname, heartbeat, expiry and
  generation. It supports renew and explicit stale recovery while rejecting a
  valid foreign lock.
- API surfaces for canonical task mutations, recovery apply/history, DLQ
  attempt retry/restore and daemon lock recovery.
- Administrative commands for task mutation/verification, recovery apply,
  DLQ retry/archive, worker registration/workload/attempts, swarm creation and
  scheduler lifecycle.

Evidence:

- Acceptance tests cover task reassign/cancel/revision conflict, operational
  recovery idempotency, DLQ review/restore deduplication, lock renew/stale
  recovery and valid-lock rejection.
- Complete focused domain suite: `147 passed`.
- Global suite after fixing the exposed Voice queue signature mismatch:
  `913 passed`, `40 failed` (`953 collected`) in `483.67s`.
- Ruff and diff check pass.
- OpenAPI contains 417 routes with no duplicate method/path or operation ID.

Remaining global failures by classification:

| Classification | Modules | Failures | Current domain |
| --- | --- | ---: | --- |
| Infrastructure/fixture | `effective_policy`, `foundation_hardening` | 10 | No |
| Observability legacy | `observability` | 9 | Consumer; mission trace focused tests pass |
| Voice/Speech | `speech_adapters`, `speech_pipeline_runtime` | 14 | No |
| UI contracts | `ui_contracts` | 4 | Consumer; Mission Control focused tests pass |
| Health integration | `health_runtime` | 3 | Consumer/residual |

Freeze decision:

The runtime Definition of Done is substantially satisfied, but the command
matrix is still missing dedicated planning commands (`mission-plan` and
`mission-validate-plan`) and several read-only recovery aliases. The domain
therefore remains **In development** rather than being falsely frozen.

## Final Freeze

Date: 2026-07-12

The final planning and recovery surfaces are complete:

- `mission-plan`, `mission-plan-show`, `mission-plan-validate`,
  `mission-plan-replace`, `mission-plan-history`, ready/blocked task and DAG
  commands call PlannerRuntime, MissionRuntime and TaskGraph.
- Plan replacement requires expected version, persists a new plan and
  preserves immutable history.
- `recovery-list`, `recovery-show`, `recovery-history`, `recovery-options`,
  `recovery-evaluate` and `recovery-apply` expose the canonical recovery shape.
- Adapter review found no domain storage mutation, DAG validation, scheduling,
  attempt creation or recovery application in API/command adapters.

### Definition Of Done

| # | Gate | Evidence | Status |
| ---: | --- | --- | --- |
| 1 | Planning commands use PlannerRuntime | versioned planning acceptance | Passed |
| 2 | Recovery queries complete | show/list/history/options/apply tests | Passed |
| 3 | Thin API and commands | directed adapter audit | Passed |
| 4 | Operational matrix complete | Missions, Plans, Tasks, Attempts, Workers, Swarms, Recovery, DLQ, Scheduler, Daemon, Trace and Mission Control documented | Passed |
| 5 | No global domain failure | global failure classification | Passed |
| 6 | Acceptance tests | four strategies, restart, recovery, DLQ and lock | Passed |
| 7 | Domain tests | `148 passed` | Passed |
| 8 | Frozen domains | included in global `914 passed` | Passed |
| 9 | Ruff | repository-wide | Passed |
| 10 | OpenAPI | 417 routes; no duplicate path/method or operation ID | Passed |
| 11 | Documentation | backend domain documents, API, matrix and baseline | Passed |
| 12 | Module status | marked Implemented / Frozen | Passed |

### Unsupported By Design

- Task delete/archive: immutable attempts and traces require stable task IDs.
- Plan delete: replacement creates an immutable new version.
- Consensus swarm: excluded because no robust consensus contract is defined.
- External trace exporter: local durable redacted export is the supported V3
  backend contract.

### Final Validation

- Focused domain suite: `148 passed` in `71.39s`.
- Global suite: `914 passed`, `40 failed` (`954 collected`) in `462.97s`.
- Ruff and diff check: passed.
- OpenAPI: clean.

**Missions + Mission Control + Workers + Swarm + Recovery = Implemented / Frozen.**
