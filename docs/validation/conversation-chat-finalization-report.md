# Conversation + Chat Finalization Report

Date: 2026-07-10

## Initial State

- Global: `901 collected`, `762 passed`, `139 failed`.
- Focused inventory set: `27 failed`, `51 passed`.
- Primary fixture cause: tests assumed removed prefabricated agents.
- Runtime gaps: duplicate Chat/Conversation flows, heuristic summary, no
  revision/pagination/idempotency, no typed participants/content/attachments,
  and no streaming/cancellation surface.

## Inventory Matrix

| Component | Responsibility | Initial state | Main gap |
| --- | --- | --- | --- |
| `ConversationRuntime` | durable mailbox/messages | partial | simple records and non-atomic append |
| `ChatRuntime` | agent/local generation | partial | independent flow and duplicated persistence |
| `ContextLoader` | identity/memory/policy context | implemented foundation | no explicit conversation port |
| `ModelRouter` | provider-neutral agent generation | in development | provider capabilities vary |
| tool runtimes | guarded calls/intents/results | implemented foundation | results not first-class conversation data |
| API/commands | transports | duplicated | parallel chat entry points |
| summary | context compression | mock heuristic | no real model generation |
| streaming/cancel | generation lifecycle | absent | no public contract |

## Corrections

- Seeded complete agent fixtures only inside tests.
- Added definitive backward-compatible conversation/message contracts.
- Added canonical `submit_turn`, unified API/commands, and explicit context port.
- Added atomic message replacement, pagination, idempotency, revision conflict,
  participants, attachments, archive/restore/delete, and cancellation.
- Added explicit confirmation for physical deletion and SHA-256/size validation
  against the attachment storage reference.
- Removed heuristic summary and added configured-model generation.
- Persisted the model and provider used to generate each summary.
- Added NDJSON streaming without fake tokenization.
- Persisted model/tool/error metadata and structured conversation errors.

## Validation

Focused result before global validation: `97 passed`.

- Global: `908 collected`, `796 passed`, `112 failed` in `475.85s`.
- Conversation + Chat failures in the global run: `0`.
- Ruff: passing repository-wide.
- Compared with the initial baseline, passing tests increased by 34 and failures
  decreased by 27. The additional seven collected tests are regressions added
  during the finalization work.

The 112 remaining failures are outside Conversation + Chat and are grouped in
the backend freeze baseline.
