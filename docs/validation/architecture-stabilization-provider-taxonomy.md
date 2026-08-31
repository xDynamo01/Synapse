# Architecture Stabilization — Provider Taxonomy

Date: 2026-07-14. Result: provider taxonomy consolidated; backend remains **NOT
READY**.

## Outcome

One neutral `CanonicalProviderManifest` and one discovery-only `ProviderCatalog`
now project the real providers selected by existing owner domains. Twenty providers
are registered on the measured Windows composition across ten populated domains.
The catalog contains no mock and does not treat the two `not_configured` Vision
null objects as identities.

The implementation adds structured capability, configuration, lifecycle,
availability, identity-conflict and redaction rules. It preserves specialized
execution registries, domain settings stores, domain health, bootstrap lifecycle,
public APIs and Commands. Model settings/execution naming conflicts are represented
as explicit aliases without changing either public ID family.

## Compatibility

The before snapshot is `provider-taxonomy-before.json`. The after snapshot records
the same frozen generic provider, settings, Model Hub, Speech, Vision, Capture,
Desktop, Insight and Notification IDs. Existing mock descriptors remain visible on
the legacy provider listing, but mock resolution is permitted only in explicit test
or development mode. There are no new HTTP or command surfaces.

OpenAPI remains 425 paths, 471 operations and 100 schemas with frozen normalized
SHA-256 `bc0b2a3cab01aa9377bc80b50193089d288edd71901a9f650e3bd02ad48ea72f`.
HealthContributor, Readiness, Context Fusion and Tool Execution were not changed.

## Architectural evidence

- Catalog methods are discovery-only; AST forbids execution/load/store/fallback.
- The manifest imports no concrete runtime.
- Concrete owner descriptors are referenced only by the bootstrap projection.
- Bootstrap constructs exactly one catalog and explicitly performs both projection
  stages.
- Model Hub and System Insight use the neutral discovery facade for manifest
  discovery; their execution paths remain unchanged.
- Generic mock resolution records
  `mock_requires_explicit_development_mode` in production.
- Optional OCR/Camera absence does not fail import or startup and creates no false
  provider ID.

## Measurements

The exact after metrics are in `provider-taxonomy-after-metrics.json`. Specialized
registries remain 4 and concrete platform factory families remain 3; the new
transversal catalog count is 1. The provider-related SCC baseline is unchanged at
25 contexts/76 internal edges; unrelated SCCs remain 4/6 and 2/2. This phase does
not claim cycle reduction.

Five fresh-process compositions measured a median 177.38 ms on this workstation.
Ten thousand deterministic lists over the 20-entry runtime catalog measured a
median 1.76 µs per call. No comparable pre-taxonomy timing was captured, so no
before/after performance improvement is claimed.

## Validation

- Provider taxonomy + architecture + generic compatibility: 21 passed.
- Architecture: 56 passed in 15.87 seconds.
- Focused provider/model/speech/vision/desktop/insight/notification selection: 135
  passed in 94.41 seconds.
- Acceptance: 64 passed in 28.31 seconds.
- Global: 1,060 passed plus 4 subtests in 583.52 seconds; zero failed/skipped.
- Ruff and `git diff --check`: passed.

No physical camera, microphone, GPU or external model service is required by the
new tests. No commit, push or pull request is part of this phase.

## Remaining blockers

Common Storage primitives, remaining SCCs, legacy Agent Creator, DataDir
maintenance and final architectural audit remain open. The backend is explicitly
**NOT READY**.
