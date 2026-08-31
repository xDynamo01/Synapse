# Process lifecycle

`LifecycleManager` starts in registration order and closes successfully started
resources in reverse order. Required startup failure rolls back earlier
resources. Optional failure degrades the report. Shutdown continues after an
individual failure, and repeated `start`/`close` returns the original report.

Each resource records name, feature, reason, callbacks, required policy,
startup/shutdown timeout, order and failure behavior.

| Order | Name | Feature | Reason | Start / close | Required | Timeout | Failure behavior |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | `agent-loop` | world-state-and-agent-loop | own persisted loop state for API lifespan | `start` / `stop` | yes | 30 s / 30 s | rollback and fail lifespan |

Stores, models, registries, scheduler-lock wrappers, event emissions and purely
synchronous runtimes are not lifecycle resources. The daemon blocking loop is
an explicit operational action, not auto-started by the API. Scheduler locks
remain per-run locks.

FastAPI builds and starts inside lifespan, publishes application/container and
reports on `app.state`, and closes on shutdown. OpenAPI generation activates no
runtime resource.
