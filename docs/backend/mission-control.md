# Mission Control

Mission Control is a read-only operational projection over durable runtimes.
It exposes active, queued, paused, blocked, overdue and failed missions;
waiting approvals and active attempts; stale and overloaded workers; recovery
and DLQ queues; swarm, scheduler and daemon state; and actionable attention
records. Values are derived from persisted records and are not decorative.
