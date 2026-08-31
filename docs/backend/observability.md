# Platform Observability

`EventBus` is the local canonical telemetry port: `start_span`, `record_event`,
`finish_span`, `query_events`, and `query_trace`. Existing `emit`, `tail`, and
`trace` methods remain compatibility adapters. Events include severity, source
module, correlation/trace IDs, parent span, duration, status, error code, and
redacted metadata. Legacy records receive safe defaults when read.

Correlation context crosses chat, tools, approvals, scheduler, durable records,
missions, workers, memory/context, provisioning, and voice boundaries. Trace
queries join event records with durable records without physically merging
domain stores.

Metrics are derived from persisted events and runtime snapshots: counters,
failure counts, duration histogram, scheduler queue depth, approvals, DLQ,
active missions, conversations, and voice sessions when those runtimes are
available. Missing measurements are omitted rather than fabricated. No external
Prometheus service is required.

Central redaction removes secret-key fields, bearer/API tokens, raw audio,
prompts, transcripts, full file content, and absolute paths. Retention cleanup
is bounded by days, supports dry-run, preserves malformed legacy lines for
manual recovery, and is idempotent.
