# Tool Execution

Statuses are pending, awaiting approval, running, completed, failed, cancelled, timed
out, rolled back and rollback failed. Results include call/tool IDs, structured output,
timestamps, duration, errors, side effects, rollback state and redacted logs.

Preview/dry-run never invoke handlers. Active cancellation is coordinated by the
canonical runtime only when the descriptor and adapter implement it; repeated cancel
returns the same terminal result. Terminal calls cannot be cancelled. Timeout,
idempotency, redacted persisted history, restart restoration, retry relationships,
and structured verification are owned by this boundary. No shell or
process tool is seeded; future subprocess adapters must terminate process groups,
limit output, filter environment and enforce sandbox policy. Path-formatted arguments
reject traversal and absolute roots before handlers.
