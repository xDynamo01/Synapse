# Search Runtime Slice 17 E2E Readiness Audit

Status: critical audit completed; this document does not declare the bounded
context frozen or the backend ready.

## Inventory

| Package/surface | Modules | Public exports | Classification |
|---|---:|---:|---|
| `search` | 11 | 179 | Pure provider-neutral contracts/domain |
| `search_adapters` | 7 | 34 | SQLite, SearXNG, HTTP Retrieval and Text Extraction adapters |
| `search_integrations` | 6 | 25 | Governance, authorized execution, consumer and source projection |
| `search_composition` | 2 | 12 | Explicit opt-in local wiring and capability health |

Public export lists contain no duplicates. Provider configuration and transport
types are adapter/composition surfaces, not Search domain fields. The persistence
schema is `SEARCH_PERSISTENCE_SCHEMA_VERSION_V1 = 1`; migration identity is
`search-metadata-persistence-v1` and its checksum is derived from the canonical
V1 SQL.

The legacy consumer path is singular: `/search` delegates to `web_search`, the
`WebSearchTool` checks `web.search`, and its consumer delegates to the composed
Search operation. Artemis, Orchestrator and Researcher are the exact Agent
configurations granted `web.search`. Tool permission is not egress authorization.

## Capability matrix

| Capability | Implemented | Current host/config fact | Operational evidence |
|---|---|---|---|
| Search contracts/domain | yes | provider-neutral | contract/correspondence tests |
| SearXNG adapter | yes | implemented | fixtures and controlled server |
| SearXNG transport | yes | implemented | bounded controlled HTTP tests |
| Real provider on host | no configured instance found | unconfigured | no discovery/install/start attempted |
| Governance integration | yes | injected authority required | allow/deny/approval/stale/expired/scope matrix |
| Search consumer | yes | unconfigured without full composition | permission and projection tests |
| HTTP Retrieval | yes | external reachability untested | controlled localhost only |
| Text/HTML Extraction | yes | local/deterministic | plain text/static HTML matrix |
| PDF Extraction | unsupported | unsupported | explicit failure contract |
| SQLite persistence | yes | schema V1, explicit activation | restart/corruption/replay matrix |
| Search/Retrieval/Extraction cache | yes | three namespaces | miss/hit/stale/incompatibility matrix |
| Source evidence projection | yes | reference-only, untrusted | all projection states and lineage checks |
| Local Composition Root | yes | opt-in, no bootstrap | build/restart/partial health tests |

Implemented does not imply configured; configured does not imply reachable;
reachable does not imply authorized; authorized does not imply successful.

## Supported journeys

Controlled localhost tests prove the Search chain from consumer request through
`SearchRequestV1`, Governance authorization, provider invocation, bounded
SearXNG transport, parsing, normalization, URL dedup/ranking and consumer
projection. Identities, fingerprints, request/provider correspondence,
correlation, occurrences and provider provenance remain explicit. An authorized
empty response is `NO_RESULTS`, not a provider failure and not a placeholder.
Negative caching remains policy-controlled.

Retrieval is a separate explicit chain. A selected result creates
`SearchResultRetrievalHandoffV1`, then `RetrievalRequestV1`, then a distinct
`EXTERNAL_RETRIEVAL` assessment. `AuthorizedHttpRetrievalExecutor` validates
operation/requester/source/policy/fingerprint/evidence before invoking the HTTP
adapter. Missing, denied, approval-required, unavailable, stale, expired or
mismatched authorization cannot produce a network attempt or artifact. Search
authorization cannot substitute for Retrieval authorization.

Extraction begins only from an existing retrieved artifact and explicit
`ExtractionRequestV1`. Plain text and static HTML extraction are deterministic;
the provider snippet is never used as extracted text. Artifact and extracted
content have separate checksums. Source projections keep external content
`untrusted` and contain no truth score, trust score, claim verification, Agent
summary or rendered citation.

## Failure and repetition evidence

The provider matrix covers unconfigured, Governance unavailable, denied,
approval required, stale/expired/mismatched evidence, wrong actor/request/provider/
destination, timeout, malformed UTF-8/JSON/provider shape, HTTP 400/403/429/5xx,
oversized response and redirect escape. Every authorization validation failure
is asserted before the first network attempt.

Provider result contracts distinguish identical repetition, contradiction,
late/stale observations and new invocation identities. No retry is automatic and
historical attempts are not overwritten.

HTTP Retrieval covers unsafe/credentialed/private destinations, unsafe and
excessive redirects, 403/404/429/5xx, timeout, excessive payload and unsupported
content. Blocked authorization never returns a fictitious artifact.

Extraction covers missing transient artifacts, wrong lineage, checksum mismatch,
malformed bytes, unsupported PDF/capability, charset conflict, invalid charset,
empty/excessive output and tolerant malformed HTML. Hostile markup containing
script, tool-like or command-like text remains inert data and causes no network
fallback.

## Cache and fresh observation

Search, Retrieval and Extraction caches are separate namespaces. Tests cover
miss, fresh/stale hit, backend/schema unavailability, semantic/provider/policy
mismatch, missing transient reference, artifact checksum mismatch, extractor
version/output-policy mismatch and negative Search caching. Cache assessments
preserve original, write and read occurrences plus cache age.

`CacheHit != FreshExternalObservation`. Cache lookup never invokes a provider;
an explicit new provider invocation retains a new invocation/occurrence and can
observe a different external fact even for the same semantic query.

## Restart, replay and transient loss

SQLite tests persist Search request/invocation/result, Retrieval, Extraction and
optional cache metadata, reconstruct stores on the same database and replay the
same facts without provider, Retrieval, Extraction or cache refresh calls:
`Replay != ExternalReexecution`.

Payload bytes and extracted text are transient. After their removal/restart,
persisted references remain historical while current artifact/extracted-content
availability is explicitly false. The evidence projection reports
`source_reference_unavailable`; incomplete lineage reports
`provenance_incomplete`. Neither state is promoted to success and neither causes
automatic recovery I/O.

Corruption tests cover incompatible schema, migration checksum mismatch, missing
append-only trigger, malformed record, contradictory identity, sequence/lineage
gaps and unavailable database. No repair is silent.

## Health and partial composition

Build performs zero network, Search, Retrieval, Extraction or Governance calls
and does not create/discover a provider. Partial scenarios cover missing provider,
Governance, persistence, Retrieval and Extraction. A configured provider remains
reachability/API `untested`; missing Governance makes external Search degraded,
never authorized. Local Extraction can be available while Search is unavailable,
and PDF stays unsupported. There is no aggregate `ready` boolean.

## Privacy and security

Persistence stores metadata and the explicitly admitted provider snippet only.
It does not automatically persist raw SearXNG JSON, HTTP bodies, raw HTML,
extracted text, credentials, cookies, authorization headers or Agent prompts.
Diagnostics contain safe codes and references rather than queries, bodies,
headers or extracted content.

Retrieved and extracted content are untrusted facts. Prompt injection, tool
instructions, shell commands and configuration-looking text are never executed
or reinterpreted as authority.

## Architecture

Baseline after Slice 16 remains 287 runtime edges and 322 source edges. Search
composition owns exactly three allowed edges: to `search`, `search_adapters` and
`search_integrations`. Search-related reverse imports are absent, bootstrap does
not import Search composition, and no new SCC exists.

## External limitations and conclusion

No real SearXNG instance is configured on this host. This is an external
operational limitation, not an architectural blocker: the complete path is
proved against a controlled localhost-compatible server without public internet.
No provider fallback, installation, container, auto-start or active probe was
performed.

The evidence supports proceeding to a separate final freeze audit. It does not
declare Search Runtime frozen, activate global bootstrap or change backend-wide
`NOT READY` status.
