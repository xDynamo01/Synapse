# Attention Engine

Status: **Implemented / Frozen**.

`AttentionRuntime` turns selected events into a durable, bounded attention
inbox. It does not execute dispositions.

An `AttentionItem` records source event IDs, entity references, severity,
urgency, relevance, confidence, expiry, status, suggested dispositions,
policy context, correlation/provenance, redacted metadata, deduplication key,
occurrence count, and suppression/defer details. Supported statuses are
`pending`, `acknowledged`, `suppressed`, `deferred`, `processing`, `resolved`,
`expired`, and `failed`. Critical items cannot be manually suppressed.

## Explainable scoring

Scoring is deterministic and returns every weighted factor and threshold.
Factors include severity, urgency, current task/conversation/mission relation,
recency, confidence, repetition, user preference/availability, risk,
resolution capability, and a DND penalty. Recommendations are bounded to
`ignore`, `record_only`, `notify`, `suggest`, or `require_approval`; scoring
alone never grants execution authority.

## Noise control

- explicit or derived stable deduplication keys;
- aggregation into an active item with a bounded source-event list;
- occurrence counts and relevance escalation;
- low-score suppression with an explicit reason;
- suppressed items reopen when later evidence is critical or materially more
  relevant;
- per-item cooldown, hourly proactive action limit, notification budget, quiet
  hours, and concurrency/risk ceilings in disposition policy;
- critical events bypass non-critical DND and suppression behavior but always
  require approval before an action.

Items are persisted under `DATA_DIR/attention/items/`; the event ledger makes
event ingestion idempotent across restart.
