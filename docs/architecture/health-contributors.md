# Health Contributor Boundary

## Contract and registry

`HealthContributor` is a neutral protocol. A contributor receives a
`HealthCheckContext` containing timestamp, correlation ID, mode, timeout budget,
diagnostics flag and redacted metadata, and returns `HealthContribution`.
Contributions contain ordered canonical `ComponentHealth` values, partial
`HomelabHealthSummary` fields, ordered `HealthCheckItem` values and gauges.

`HealthContributorRegistry` is the only registry. Bootstrap registers every
production contributor explicitly; registration order is deterministic and
duplicate or mismatched IDs are rejected. Required and optional empty slots are
explicit. There is no import-side discovery.

## Contributors

Ten contributors own the existing health surface: Platform, Agents,
Delegation, Missions, Models/Providers/Insight, Voice/Audio/Speech,
Perception/Vision, Tools/Execution, Context Fusion, and World/Desktop. They call
already-built public runtimes and translate their read-only status into the
canonical models. Contributors do not import stores, API, Commands or bootstrap,
construct runtimes, open devices, start providers or decide global readiness.

The Agent Creator availability flag still combines dependencies from more than
one context. It remains an explicitly preserved finding in the Agents
contributor; this phase does not redesign Agent Creator.

## Aggregation and isolation

`HealthRuntime` imports no domain implementation. It iterates the registry,
applies the configured per-contributor timeout, isolates exceptions and invalid
results, rejects duplicate component IDs, sorts components/checks by their
contract order, builds `HomelabHealthSummary`, calculates structural severity
and emits the existing `health.checked` event.

Failure details are redacted. A failed required contributor produces an
explicit unavailable component and warning; a missing optional contributor is
`not_configured` and does not degrade health. Collection uses daemon worker
threads so a timed-out check cannot block the global report. Contributors are
required to be side-effect free because timed-out work cannot be forcibly
cancelled safely in Python.

## Readiness

`ReadinessRuntime` depends on `HealthSnapshotSource`, not `HealthRuntime` or any
domain. It still applies the existing readiness policy to the unchanged
`HomelabHealthSummary`. Optional camera, GPU, OCR, external provider and speech
semantics remain contributor metadata/state; Readiness was not redesigned.

The public surface remains 32 ordered component IDs and 82 summary fields.
Endpoints, Commands and OpenAPI are unchanged.

The backend remains **NOT READY**. Tools/Provider consolidation, Storage,
Agent Creator and the remaining domain SCCs are outside this phase.
