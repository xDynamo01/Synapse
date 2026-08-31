# Platform Health and Readiness

`HealthRuntime` aggregates registered `HealthContributor` snapshots. Each
component reports state, configured/available/ready/degraded flags, last check,
latency/error when known, dependencies, recommendations, and redacted metadata.
States are not_configured, ready, degraded, unavailable, misconfigured,
starting, and stopping.

Bootstrap explicitly registers ten bounded-context contributors in one
`HealthContributorRegistry`. Agents, conversations/context, memory,
models/providers, tools, missions, voice, perception, world state, insight and
platform operations contribute through public runtime boundaries. The
aggregator does not open hardware or invent provider readiness.

The collector applies a five-second timeout per contributor, redacts exceptions,
rejects invalid/duplicate component IDs and continues collecting other
contributors. Missing optional contributors are `not_configured` and do not
degrade the backend; missing required contributors are explicit warnings.

Readiness answers whether startup is possible, which features are degraded or
disabled, and which action is required. It imports the neutral
`HealthSnapshotSource` contract rather than a concrete runtime or domain. A
missing dependency degrades only an enabled feature that requires it. The
existing readiness policy and recommendations remain unchanged.

Diagnostics expose all 32 component snapshots and their dependency graph
without frontend dependencies or secrets. Contributors must be read-only: no
storage access, device opening, provider startup, recovery or global readiness
decisions.
