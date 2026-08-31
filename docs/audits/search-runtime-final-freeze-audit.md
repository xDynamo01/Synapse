# Search Runtime Final Freeze Audit

Final bounded-context classification:

**Search Runtime — IMPLEMENTED / ARCHITECTURALLY COMPLETE / FROZEN**

This classification is limited to the Search Runtime bounded context. The
backend remains **NOT READY** and Search Runtime as a whole is not classified as
operationally complete because no live SearXNG provider is configured on this
host.

## Architecture summary

Search Runtime consists of a pure provider-neutral domain, concrete adapters,
consumer-owned Governance/execution integrations and an explicit local
Composition Root. Search owns request/result/source/provenance facts. Agents own
selection, relevance, comparison and conclusions. Conversation/UI owns final
citation rendering. No global bootstrap activates Search.

Final dependency direction:

- `search_adapters -> search`
- `search_integrations -> search`
- `search_integrations -> search_adapters`
- `search_integrations -> intelligence_boundary`
- `search_composition -> search`
- `search_composition -> search_adapters`
- `search_composition -> search_integrations`

There are no reverse Search dependencies and no Search package belongs to an
SCC.

## Capability classification

| Capability | Classification | Evidence/limitation |
|---|---|---|
| Search domain/contracts | ARCHITECTURALLY COMPLETE | Pure immutable V1 contracts |
| Request/result/provenance models | OPERATIONALLY COMPLETE | Correspondence and canonical fingerprint tests |
| Deterministic URL normalization | OPERATIONALLY COMPLETE | Explicit normalization policy and warnings |
| Deterministic dedup/ranking | OPERATIONALLY COMPLETE | Stable representative selection; no relevance authority |
| Provider abstraction | ARCHITECTURALLY COMPLETE | Provider-neutral port/capability/result contracts |
| SearXNG adapter | IMPLEMENTED | Fixture and controlled E2E coverage |
| SearXNG transport | IMPLEMENTED | Bounded localhost HTTP path proven |
| Governance egress integration | ARCHITECTURALLY COMPLETE | Search and Retrieval purposes/scopes separated |
| Search authorization path | OPERATIONALLY COMPLETE | Invalid evidence gives zero network attempts |
| Search consumer/tool integration | OPERATIONALLY COMPLETE | Single permission-gated execution path |
| `/search` | OPERATIONALLY COMPLETE | Delegates only to `web_search` and preserves factual status |
| Search persistence | OPERATIONALLY COMPLETE | SQLite V1 append-only/replay/restart/corruption tested |
| Search cache | OPERATIONALLY COMPLETE | Independent namespace and negative-cache policy |
| HTTP Retrieval | IMPLEMENTED | Controlled localhost execution; public reachability untested |
| Retrieval authorization path | OPERATIONALLY COMPLETE | Authorized executor required by Composition Root |
| Retrieval cache | OPERATIONALLY COMPLETE | Reference/checksum/policy compatibility enforced |
| Plain-text extraction | OPERATIONALLY COMPLETE | Deterministic local extraction |
| Static HTML extraction | OPERATIONALLY COMPLETE | Deterministic non-browser extraction; active content inert |
| Extraction cache | OPERATIONALLY COMPLETE | Artifact/extractor/version/reference invalidation |
| Source/evidence projection | ARCHITECTURALLY COMPLETE | Reference-only, untrusted, no conclusions/rendering |
| Local Composition Root | ARCHITECTURALLY COMPLETE | Explicit, opt-in, partial, build has no execution |
| Restart/replay | OPERATIONALLY COMPLETE | Metadata recovery with zero external re-execution |
| SearXNG live provider | UNCONFIGURED | No explicit host/repository configuration found |
| Live external Search on host | UNCONFIGURED | Requires an explicitly configured provider and authority |
| PDF extraction | UNSUPPORTED | Explicitly rejected |
| OCR | UNSUPPORTED | No implementation |
| Browser/JS-rendered content | UNSUPPORTED | Static extraction only |
| Autonomous research | INTENTIONALLY OUT OF SCOPE | Agent responsibility |
| Citation rendering | INTENTIONALLY OUT OF SCOPE | Conversation/UI responsibility |
| Perception interpretation | INTENTIONALLY OUT OF SCOPE | Perception responsibility |

## Frozen surface inventory

| Package | Modules | Public exports |
|---|---:|---:|
| `search` | 11 | 179 |
| `search_adapters` | 7 | 34 |
| `search_integrations` | 6 | 25 |
| `search_composition` | 2 | 12 |

Every `__all__` is duplicate-free. The domain surface contains V1 request,
result, provider, Retrieval, Extraction, persistence and cache contracts/ports.
SearXNG configuration and HTTP transport remain adapter surfaces. Local wiring
remains composition-owned.

Persistence baseline:

- schema version: `1`;
- migration identity: `search-metadata-persistence-v1`;
- migration checksum:
  `922d895d5bad66e5cf2672b198f920258d0d50e971f1ad40c7ed7d39d4b2b9a7`;
- append-only update/delete triggers required;
- three independent cache namespaces: Search, Retrieval and Extraction.

Consumer permission baseline grants `web.search` exactly to Artemis,
Orchestrator and Researcher. Permission permits requesting the tool; it is not
Search or Retrieval egress authorization.

## Domain and authority freeze

The `search` package imports no Synapse bounded context, SearXNG, HTTP/network,
SQLite, Agent, Tool, Governance, Perception or Composition implementation.
`SearchRequestV1` contains no SearXNG endpoint/engine/credential fields.
Normalized results preserve provider metadata without depending on raw SearXNG
payload shape.

Search contains no autonomous planner, LLM reasoning, query-decomposition loop,
answer synthesis, truth judgment, research orchestration or citation renderer:
`Search != Agent reasoning`.

Stages remain distinct:

- `SearchResult != RetrievedArtifact`
- `RetrievedArtifact != ExtractedContent`
- `ExtractedContent != AgentSummary`
- `SearchResultAvailable != RetrievalRequested`
- `RetrievalSuccess != ExtractionSuccess`

No stage automatically starts the next stage.

## Ranking, freshness and evidence semantics

Normalization and representative selection are deterministic. Provider position
is preserved separately from normalized rank. Same-domain URLs are not duplicates
by that fact alone, and neither dedup nor normalized rank is Agent relevance.

Publication date, provider-reported date, Search occurrence, Retrieval
occurrence, Extraction occurrence and cache read/age remain independent:
`RecentRetrieval != RecentPublication` and
`CacheFreshness != SourceFreshness`.

Provider snippets are neither retrieved content nor evidence. Extraction does
not verify a claim. Source metadata does not become an Evidence conclusion.
Search creates no truth, trust or relevance score and renders no citation.

Retrieved and extracted content always remains untrusted. HTML prompt injection,
tool-like instructions, shell commands and configuration-like text are inert
input data and cannot alter tool/configuration authority.

## Execution and health freeze

Provider invocation is not network authorization. Authorized Search execution
requires current matching evidence before transport. Authorized Retrieval uses a
separate executor and `EXTERNAL_RETRIEVAL` evidence; Search authorization is
rejected. Adapter destination safety is defense in depth, not Governance.

A local SearXNG endpoint does not imply fully local processing or trusted
upstream engines. Provider trust and upstream external processing remain explicit
facts.

Health distinguishes implemented, configured, reachable, authorized, API usable
and operational states. Adapter implementation does not imply external capability
availability. The current live provider and external Search states remain
unconfigured rather than promoted to success.

## Persistence, cache, restart and privacy

Persistence freezes exact reads, append/idempotency, contradiction rejection,
lineage, integrity health and replay. Replay reconstructs metadata and never
reexecutes provider, Retrieval, Extraction or cache refresh.

Historical references do not assert current payload availability. Loss of
transient artifact/extracted content remains unavailable after restart without
automatic network or extraction recovery. Missing/incomplete evidence never
becomes success.

Default persistence does not automatically retain raw SearXNG JSON, HTTP bodies,
raw HTML, extracted text, cookies, Authorization headers, credentials or Agent
prompts. The explicitly admitted provider snippet remains result metadata only.
Cached metadata is not persisted web content and a cache hit is not a fresh
external observation.

## Consumer and Composition Root freeze

`/search -> web_search -> SearchToolConsumer -> configured Search operation` is
the single path. Agents and Tools do not import SearXNG, HTTP adapters or Search
composition directly. The old parallel placeholder is absent.

`build_search_runtime()` is local, explicit, opt-in and partial. Import/build
does not open network, execute Search/Retrieval/Extraction, evaluate Governance,
initialize persistence or start/discover a provider. Persistence initialization
and probes are explicit methods. Bootstrap does not import Search composition:
`Build != Execute`.

## Architecture baseline

- runtime graph: **287 edges**;
- source graph: **322 edges**;
- Search composition: exactly three authorized outgoing edges;
- Search-related SCCs: **0**;
- new SCCs: **0**.

## Freeze gate and final status

`tests/architecture/test_search_runtime_freeze.py` protects package/module and
public export baselines, V1 contracts, domain purity/provider neutrality,
stage/authority separation, ranking/freshness/evidence semantics, untrusted
content, authorized executors, persistence/cache/privacy, consumer migration,
Composition Root isolation, graph edges and SCC baselines.

Unsupported and externally unconfigured capabilities are explicit non-blockers;
they were not presented as implemented or operational. No internal blocker
remains in the frozen surface.

## Final verification

Executed on the freeze checkout:

- dedicated Search freeze gate: 10 passed;
- complete Search Runtime/adapters/integrations/composition campaign: 400 passed;
- complete architecture suite: 237 passed;
- global Ruff: passed;
- authoritative global Mypy, non-incremental: 711 source files, no issues;
- global deterministic regression: 3,949 passed, 4 skipped and 4 subtests;
- discovered/union/unique test files: 297/297/297;
- omitted/duplicates/timeouts: 0/0/0;
- `git diff --check`: passed.

The global regression used absolute normalized paths, ordinal sorting and index
modulo `N=8`. All operations involving HTTP used controlled localhost servers;
no public internet endpoint was selected or contacted.
