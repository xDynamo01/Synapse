# Search Runtime

## Slice 2 foundation and Slice 3 result facts

Search is a first-class bounded context. This slice establishes only its pure,
provider-neutral domain language: opaque identities, canonical serialization,
semantic fingerprints, a closed error/outcome taxonomy and `SearchRequestV1`.
Slice 3 adds deterministic normalized result, result-set, provenance and freshness
facts without adding execution.

**Search request != provider invocation.** A request describes admitted search
semantics. It does not select, configure or call a provider. `SearchInvocationId`
is reserved for a later provider-invocation slice and is deliberately absent from
`SearchRequestV1`.

**Search Runtime != Agent reasoning.** Query decomposition, reformulation,
iterative research, source comparison and answer synthesis remain Agent authority.
The request contains no prompt, reasoning instruction, research plan or Agent
selection.

## Authority and non-authorities

Search owns request identities, provider-neutral constraints, canonical request
semantics, deterministic fingerprints and Search-specific error language. It does
not own provider execution, network egress, HTTP, retrieval, extraction, ranking,
deduplication, citations, persistence, cache, browser automation, Governance,
Perception or presentation.

The package imports only the Python standard library. No existing bounded context
depends on it in this slice, and it has no governed dependency edges.

## SearchRequestV1

`search-request-v1` preserves:

- opaque request, requester and correlation identities;
- explicit query text;
- optional language and locale constraints as validated, lower-case language tags;
- provider-independent result limit, default `10`, bounded from `1` through `50`;
- freshness constraint;
- extensible provider-neutral category references;
- explicit domain include/exclude constraints;
- provider-neutral safe-search mode;
- optional policy reference;
- explicit purpose;
- causation references and occurrence timestamp;
- contract and canonical-format versions.

Construction trims only leading and trailing query whitespace. Internal whitespace
is preserved: the domain performs no stemming, expansion, rewriting or language
inference. This deterministic trim therefore affects both stored semantic content
and its fingerprint.

An empty category tuple means **no category restriction**. It does not mean all
SearXNG engines. Domain constraints lowercase host names, remove one terminal dot,
deduplicate and sort them; this is bounded host validation, not URL normalization.

Safe-search values are `off`, `moderate` and `strict`. Their translation into any
provider representation belongs to a future adapter.

`SearchPurpose` is an explicit neutral reference. A later integration slice owns
its canonical mapping to Intelligence/Governance; Search does not import or
duplicate `ProcessingPurpose`.

## Canonical format and identities

`search-json-v1` uses UTF-8 JSON, stable key ordering, compact separators and
explicit canonical representations for identities, enums and UTC timestamps.
Fingerprints use lower-case `sha256:` values.

Semantic fingerprints include requester, query, language, locale, result limit,
freshness, categories, domains, safe-search, policy and purpose. They exclude
request identity, correlation, causation and occurrence timestamp. Consequently,
two separately occurring requests may be semantically equivalent without being
the same request or occurrence.

Identities are opaque, bounded and never timestamp-derived. Request and invocation
identities have distinct prefixes. References reject whitespace, absolute paths
and traversal.

## Request freshness

`FreshnessConstraint` represents:

- no constraint;
- a positive relative window;
- an absolute lower bound (`after`);
- an absolute upper bound (`before`);
- a valid absolute interval.

All absolute times are timezone-aware and canonicalized to UTC. This constraint is
not a publication date, retrieval occurrence or cache age. Those facts do not
are separate result facts.

## Normalized result semantics

`NormalizedSearchResultV1` preserves an observed provider result without claiming
that Search retrieved or verified its source. Result identity is opaque and is
neither the URL, provider position nor an occurrence timestamp. Source URL,
provider-supplied canonical URL, title, provider snippet, source/provider
references, provider result reference, positions, dates, language, provider-
reported content type, provenance and freshness remain explicit fields.

**SearchResult != RetrievedContent.** Retrieval and extraction do not occur in
this slice. `retrieved_content_reference`, `extracted_text_reference` and
`agent_summary_reference` are reference-only and cannot contain or alias the
provider snippet.

**ProviderSnippet != Evidence.** `provider_snippet` is only text returned by the
search mechanism. It is not retrieved source content, complete-source evidence,
extracted text or an Agent summary.

## Result set and outcome

`SearchResultSetV1` preserves the request identity and semantic fingerprint,
provider and optional future invocation reference, ordered results, Search
occurrence, provenance, safe diagnostics, outcome and format version.

`results` requires a non-empty, consistently ranked sequence. `no_results`
requires an empty sequence and retains request/provider provenance without a
placeholder or transport-failure diagnostic. Operational errors remain typed
errors; they are not fabricated as successful result sets.

Duplicate result identities and provider positions are rejected. Normalized
ranks must be ordered, unique and contiguous from one. Invalid input is never
silently deduplicated.

## Provider position and normalized rank

`provider_position` is the position observed in provider output.
`normalized_rank` is the deterministic order recorded by Search Runtime. This
slice may preserve provider order but implements no reranking or relevance
judgment.

**Provider rank != factual relevance.**

**Normalized rank != Agent relevance judgment.**

## Provenance and publication dates

Structured provenance preserves request identity/fingerprint, provider and
optional invocation reference, result/provider-result identities, source URL,
Search occurrence, provider position and optional correlation/causation. It does
not contain credentials, raw responses, prompts, reasoning or unredacted
diagnostics.

Publication-date provenance distinguishes `provider_explicit`, future
`source_extracted`, and `unknown`. A provider-explicit publication date must match
the separately preserved provider-reported date. Unknown carries no publication
date. Search occurrence is never projected into publication date, and ordering or
URL structure supplies no date.

## Result freshness facts

`FreshnessFacts` relates the request constraint, known publication date,
provider-reported date and Search occurrence. Its closed states are `satisfied`,
`violated`, `unknown` and `not_requested`. A requested constraint with no known
publication date is `unknown`, never assumed satisfied. These facts annotate
results only; they do not filter or remove them.

Future retrieval occurrence and cache occurrence/age remain absent because no
retrieval or cache authority exists in this slice.

## URL, source and provider metadata limits

URLs receive bounded structural HTTP(S) validation only. Search does not remove
tracking parameters, normalize schemes or queries, resolve redirects, deduplicate
or certify a provider-supplied `canonical_url` as canonical under Search rules.
The safely derived hostname is structural only: it is not reputation,
reliability or publisher authority.

Content type is accepted only as a provider-reported MIME value. Search performs
no retrieval and makes no title/extension inference. Provider-specific metadata
uses deterministic, unique namespace/key entries, cannot overwrite canonical
fields or carry credential-like keys, and is excluded from the result's central
semantic fingerprint.

## Errors, outcomes and diagnostics

`SearchErrorCode` is closed over contract and anticipated operational categories:
invalid query, unsupported capability, policy block, provider configuration/
availability/timeout/malformed response, retrieval/extraction failures,
unsupported content, stale cache and incomplete provenance.

`no_results` is deliberately modeled as `SearchOutcomeCode.NO_RESULTS`, not as an
exception or transport/provider failure.

`SearchDiagnostic` carries only a code, safe bounded message, timezone-aware
occurrence and optional opaque request/capability/detail references. It has no raw
provider payload, credentials, prompt, sensitive query echo or stack trace.

## URL normalization V1

`search-url-normalization-v1` is a pure, deterministic projection. It preserves
the original provider URL, the optional provider-supplied canonical URL and the
Search-normalized URL as three different facts.

**NormalizedURL != PublisherCanonicalURL.** Search normalization is an internal
comparison rule, not evidence of the publisher's official canonical URL.

V1 supports only `http` and `https`; rejects embedded credentials, control
characters, malformed hosts, invalid ports/percent encodings and unsafe schemes;
lowercases scheme/hostname; applies deterministic built-in IDNA encoding; removes
default ports and fragments; represents an empty/root path consistently; decodes
only percent-encoded unreserved characters; and uppercases preserved percent
bytes. A non-root trailing slash is preserved because removing it may change
resource semantics.

No DNS, redirect, HTTP canonical discovery, document inspection, retrieval or
network access occurs.

## Tracking and query policy

`search-tracking-parameters-v1` removes only the closed V1 set `fbclid`, `gclid`
and the `utm_*` family. Unknown parameters are preserved. Query components are
ordered deterministically by normalized key, while repeated values for the same
key retain their original order and are never collapsed.

The rules record changed components, warnings, rules/policy versions and a
fingerprint of the Search-normalized URL. This fingerprint does not replace
`SearchResultId`; distinct results may reference the same normalized URL.

## Factual duplicate assessment

The comparison taxonomy distinguishes exact original-URL duplicate,
Search-normalized-URL duplicate, comparable provider-canonical duplicate,
same-domain-only, unique and not-comparable. Only the three explicit duplicate
classes form duplicate groups.

**SameDomain != Duplicate.** Hostname extraction is structural grouping only. It
does not identify a publisher, establish trust or prove duplicate content.

Every duplicate group preserves member result identities, positions,
Search-normalized URLs and all member provenance. The representative rule is
exactly: lowest existing normalized rank, then lowest provider position, then
stable result identity. It uses no title/snippet quality, trust, reputation,
freshness, semantic similarity or model judgment.

**Dedup != Relevance.** Duplicate grouping is URL correspondence, not a relevance
assessment.

## Full and deduplicated ranking views

`DeduplicatedSearchViewV1` is a separate immutable projection. The factual
`SearchResultSetV1` and every original result remain intact. Its full view retains
all results; its deduplicated view contains representatives plus unique results.
Both views assign deterministic, one-based, contiguous ranks and preserve every
provider position unchanged.

**NormalizedRank != AgentRelevance.** V1 ordering uses existing normalized rank,
provider position and stable identity only. It implements no reranking.

Freshness facts may travel with source results but never alter this ranking:
**freshness != relevance ranking**.

Provider identity is not part of normalized URL identity. Duplicate-group
provenance can therefore preserve contributions from multiple providers in a
future multi-provider result set without changing URL correspondence rules.

## Search provider boundary

`SearchProviderPort` is the consumer-owned, provider-neutral boundary:
`invoke(SearchProviderInvocationV1) -> SearchProviderResultV1`. Both sides contain
only Search contracts. No endpoint, HTTP response, raw transport payload, API key,
headers, prompt or provider-specific engine field crosses the boundary.

The generic `synapse.providers` foundation was audited. Its catalog manifests and
health records are broader discovery/composition contracts and would create a
governed dependency from Search. Search therefore owns its narrow contracts;
future adapters/composition may translate between them without making the Search
domain depend on `providers`.

**SearchRequest != ProviderInvocation.** A request may produce zero, one or
multiple future invocations. Each invocation has its own identity and preserves
the request identity and semantic fingerprint. A retry references the prior
attempt but always uses a new invocation identity; it does not assert external
idempotency.

## Provider capabilities

The closed provider-neutral capability taxonomy covers basic web search,
language/category/domain/freshness constraints, safe-search, result limit and
provider-reported dates. Each declared fact is `supported`, `unsupported`,
`degraded` or `unknown`.

Invocation requirements are derived from the complete `SearchRequestV1`.
Unsupported, degraded or undeclared required capabilities are not silently
ignored: they produce an `unsupported_capability` factual result with a safe
diagnostic before any adapter invocation.

## Invocation and provider result envelope

`SearchProviderInvocationV1` preserves invocation/request/provider identities,
semantic request fingerprint, normalized request constraints, required
capabilities, correlation/causation, occurrence, policy reference and a bounded
timeout contract.

`SearchProviderResultV1` distinguishes results, valid no-results, unavailable,
timeout, malformed response, externally reported policy block and unsupported
capability. Success requires a corresponding `SearchResultSetV1`; failures carry
safe diagnostics rather than fabricated successful result sets.

Correspondence validates invocation, request identity/fingerprint, provider,
correlation, capability set and result-set provenance. An identical repeated
observation is idempotent. A different observation for the same invocation is
classified as contradictory and never silently replaces the first fact.

## Timeout, retry and network authority

**ProviderInvocation != NetworkAuthorization.** The port describes capability;
it does not grant egress, prove configuration or contact a provider. External
authorization and network availability belong to future composition/adapters.

**TimeoutObserved != ExecutionTerminated.** A timeout means the admitted waiting
boundary elapsed. Provider completion remains unknown; Search has no process or
network termination authority.

Retry execution is absent. The contracts only require a new invocation identity,
preserving separate provenance for every future attempt.

## Provider health

Provider health distinguishes `unconfigured`, `configured`, `available`,
`degraded` and `unavailable`, with independent facts for capability declaration,
configuration, reachability, supported response format, authorization and network
egress. Unknown future-adapter facts remain unknown.

**AdapterExists != ProviderAvailable.** `available` requires explicit positive
operational facts; a code/adapter reference alone cannot satisfy health. Search
Runtime health can truthfully report that contracts exist while zero providers
are composed.

Health, capabilities, invocation and provider-result fingerprints exclude their
occurrence metadata where occurrence is not semantic. Diagnostics contain only
safe codes/messages and opaque references, never credentials, headers or raw
response bodies.

## SearXNG translation adapter

Slice 6 adds the separate `synapse.search_adapters` bounded package. Direction is
strictly `search_adapters -> search`; the Search domain does not import or know
the adapter.

**SearXNGAdapter != Search Runtime.** The adapter translates provider-neutral
invocations into a typed, adapter-local GET representation and converts JSON
observations into Search result envelopes. SearXNG configuration, category names,
safe-search integers, `time_range`, engines and response fields never enter
`SearchRequestV1` or other central Search contracts.

Configuration owns the provider identity, structurally validated HTTP(S) origin,
safe endpoint path, JSON response format and explicit Search-to-SearXNG category
mapping. It contains no credentials and performs no DNS or reachability check.

**SearXNG configured != SearXNG reachable.** The adapter reports `configured`,
with reachability, authorization and network egress `unknown`. Without an
explicitly injected transport it produces `provider_unavailable`; it never claims
availability merely because configuration or adapter code exists.

## Capability and request translation

Query text is mapped to `q`; validated language or locale is passed only when
explicit; safe-search maps internally as `off -> 0`, `moderate -> 1`, and
`strict -> 2`; result limit remains an explicit adapter parameter. Categories use
only configured mappings. An unknown category is rejected rather than forwarded
as an arbitrary SearXNG category.

Freshness maps only exact windows of one day, 30 days or 365 days to SearXNG
`day`, `month` or `year`. Absolute constraints and other windows are rejected as
unrepresentable; no temporal approximation occurs. Domain constraints are
declared unsupported and cannot be silently dropped.

## Result parsing and projection

The parser requires an object root and a result list. Empty lists become valid
`NO_RESULTS`; malformed roots, lists, entries, URLs or required fields become a
safe malformed-response result, never a placeholder.

SearXNG `content` maps only to `provider_snippet`.
**ProviderSnippet != RetrievedContent.** It creates no retrieved content,
extracted text, evidence or Agent summary.

Explicit parseable timestamps become provider-reported publication dates. Missing
or invalid dates remain unknown; invalid strings add a safe provenance diagnostic
without fabricating a date. Search occurrence remains separate.

Engine lists, engine, category and score are preserved only as bounded
`searxng`-namespaced opaque metadata. **UpstreamEngine != SearchProviderIdentity.**
The principal provider identity remains the configured SearXNG instance.

Every parsed URL is validated and normalized through Search URL normalization V1.
The original URL and explicit provider canonical URL remain preserved. Duplicate
assessment and ranking use the existing Search projection without adapter-specific
rules.

## Transport separation

`SearXNGTransportPort` is an adapter-local protocol for a future transport. The
repository contains only typed request/response representations and fake test
transports—no HTTP implementation, network call, production provider, Docker or
SearXNG process. The adapter does not gain network authority from the port.

The adapter package has three modules and seven deliberate exports. Search itself
remains at eight modules and 89 exports.

## Public surface through Slice 6

The package contains eight modules and 89 deliberate public exports. There is no
generic `search()` facade or provider adapter.

## SearXNG reservations after Slice 6

Production SearXNG transport, invocation execution, HTTP/network access,
retrieval/extraction, cache/persistence, Governance/egress integration,
Agents/Tools and composition remain explicitly outside these contracts. Ranking beyond the
factual V1 ordering, semantic/content deduplication and publisher-canonical
discovery are also reserved. Slice 7 may define the next bounded contract, but
this slice creates no production transport, execution runtime or production wiring.

## Retrieval and extraction sub-boundary

Slice 7 adds pure, explicit lineage contracts inside Search:
`SearchResultReference -> RetrievalRequestV1 -> RetrievedArtifactV1 ->
ExtractionRequestV1 -> ExtractedContentV1`. Construction of one fact never
executes the next step.

**SearchResult != RetrievedArtifact.** A result merely supplies source identity
and URL facts. **SearchResult presence != Retrieval executed.** Retrieval requires
an explicit immutable request with requester, accepted MIME types, bounded maximum
size, policy reference, correlation/causation and its own occurrence/identity.

## Retrieved artifacts

`RetrievedArtifactV1` separates metadata from payload custody. It preserves source
and optional observed-final URLs, reported and normalized content type, content
length, SHA-256 payload checksum, retrieval occurrence, transport reference,
outcome and an opaque content reference. Raw bytes are never required inline and
are not persisted automatically.

Retrieval outcomes distinguish retrieved, not found, policy blocked, unavailable,
timeout, too large, unsupported content, malformed source and failed. A successful
artifact must carry explicit length, checksum and content reference; unsuccessful
outcomes cannot claim payload facts. Empty payload is represented factually by
length zero with checksum/reference, subject to the future adapter's semantics.

The observed final URL is only a future redirect/transport fact:
**final URL != publisher canonical URL**. Search resolves no redirect.

An artifact checksum fingerprints retrieved payload bytes under an explicit
algorithm. It is neither source identity nor artifact identity, publication
identity or semantic-equivalence proof.

## Extraction contracts

`ExtractionRequestV1` is a separate explicit request over a successfully retrieved
artifact. The minimal capability taxonomy covers plain text, HTML-to-text,
metadata and binary passthrough. PDF-to-text is reserved and rejected as
unsupported. Slice 9 supplies only plain-text and static-HTML capabilities.

`ExtractedContentV1` preserves its own identity, request/attempt/artifact lineage,
capability, outcome, extractor reference/version, occurrence, opaque content
reference, checksum and limitations.

**RetrievedArtifact != ExtractedContent.**

**ExtractedContent != AgentSummary.** An optional Agent-summary reference remains
reference-only and cannot alias or embed extracted text. Likewise, provider
snippets remain independent Search-result facts.

**RetrievalSuccess != ExtractionSuccess.** A retrieved artifact can produce an
unsupported, malformed, unavailable, failed or explicitly empty extraction.

## Provenance, time and multimodal custody

Provenance preserves every identity in the chain from Search request/result through
retrieval request/attempt/artifact and extraction request/attempt/content. Exact
correspondence rejects wrong source/artifact, lineage gaps and stale observations.
Semantic repetition is classified as first, identical or contradictory without
overwriting prior facts; attempts use distinct identities.

Search, retrieval and extraction occurrences remain independent.
**RecentRetrieval != RecentPublication.** Recent extraction also says nothing about
retrieval freshness or source publication.

Image, audio, video, PDF and other binary artifacts remain MIME-annotated opaque
content references. Search performs no multimodal interpretation and imports no
Perception authority.

The contracts contain no headers, cookies, credentials, browser instructions,
prompts, inline secrets, cache or persistence behavior. Search contains nine
modules and 119 deliberate exports; the only cross-context edge remains
`search_adapters -> search`.

## Reservations after Slice 7

HTTP retrieval, redirect execution, HTML/PDF extraction, browser automation,
multimodal interpretation, cache/persistence, Governance/egress, Agents/Tools,
Evidence/citations and production composition remain outside these contracts.

## HTTP retrieval adapter

Slice 8 adds `HttpRetrievalAdapter` to `search_adapters`; dependency direction
remains only `search_adapters -> search`. The Search domain imports no HTTP
library. The adapter uses Python's stdlib transport, performs explicit GET
retrieval and returns only `RetrievedArtifactV1`.

**HTTP Retrieval != Content Extraction.** No HTML/PDF parser, DOM, readability,
OCR, browser automation, JavaScript rendering or `ExtractedContentV1` construction
exists in this adapter. **RetrievedArtifact != ExtractedContent** remains true.

## Schemes, redirects and status outcomes

Only structurally valid `http` and `https` URLs without embedded credentials are
admitted. `file`, `ftp`, `data`, `javascript` and custom schemes fail before
network access.

Redirects are handled manually, with a configured maximum, loop detection,
validation of every destination and rejection of unsafe schemes. The original
source URL, redirect chain and final observed URL are preserved.
**FinalRedirectURL != PublisherCanonicalURL.** No redirect is projected as a
publisher declaration.

HTTP 404 maps to not-found; 401/403 to policy-blocked; 408 to timeout; 429 and 5xx
to unavailable; other failures remain factual failed/unavailable outcomes.
There is no automatic retry. Each explicit execution receives a distinct
retrieval-attempt identity even if payload checksums later match.

## Streaming, size and artifact custody

`Content-Length` is checked before body reading when valid. The body is then read
in bounded chunks and stopped immediately when the request maximum is exceeded,
including responses without a length header. Oversized or unsupported content is
never retained.

Successful bytes live only in a process-local `TransientArtifactContentStore`
under an opaque reference. Consumers explicitly release them. This is neither
durable persistence nor cache and uses no response-derived filesystem path.

SHA-256 is calculated over the decoded representation delivered by the stdlib to
the transient artifact store—the exact bytes returned to the consumer. It is a
payload fact, not source identity, semantic equivalence or trust.

## Content type, timeout and cleanup

Raw `Content-Type` is preserved; the media type before parameters is lowercased
for allowlist comparison. Declared charset remains in the raw fact. Missing type
stays unknown; URL/title extensions are not used for inference. Payload is never
decoded into text by this slice.

Connect and established-socket read timeouts are configured separately where the
stdlib exposes the socket. Responses close deterministically on success, timeout,
size rejection and failures. **Timeout observed != remote execution terminated.**

## Network authority and health

Every domain request already carries an explicit policy reference, but the
adapter does not treat that reference as a final egress decision. Private and
loopback destinations are blocked by default and require an explicit controlled
adapter configuration, used only by local tests in this slice. It does not create
a second policy engine; final Governance/egress binding remains reserved for
Slice 11.

Health reports adapter/library availability separately from network authority and
external reachability. Local controlled success cannot promote either fact:
**LocalhostSmoke != InternetAvailability**.

After Slice 8 the adapter package had four modules and 12 deliberate exports.
No new cross-context edge or SCC was introduced.

## HTML/text extraction adapter

Slice 9 adds `TextExtractionAdapter` to `search_adapters`. It accepts an explicit
`ExtractionRequestV1` and its corresponding `RetrievedArtifactV1`, reads only the
artifact's existing opaque transient reference and emits `ExtractedContentV1`.
It never revisits the source URL. Released bytes produce the factual outcome
`artifact_unavailable`.

**Extraction != Retrieval.** The extractor imports no network client, opens no
URL, launches no browser and loads no linked resource. HTML is untrusted data
parsed locally with stdlib `html.parser`; script, style, noscript, template,
iframe, comments and attributes are excluded. JavaScript is never executed.

Plain text is decoded without rewriting, summarizing, translating or correcting.
Static HTML preserves visible structural text including title, headings,
paragraphs, list items, link labels, basic table cells and pre/code content.
Spaces within ordinary text are collapsed, block boundaries become at most one
blank line and surrounding whitespace is removed. This is deterministic but not
a semantic readability algorithm: **ExtractedText != MainArticleContent**.

## Charset, limits and checksums

Charset precedence is deterministic: valid transport charset, then valid explicit
HTML charset, then strict UTF-8. Invalid declarations and transport/HTML conflicts
remain limitations. Transport declaration, HTML declaration, used codec and its
provenance source remain separate facts; decoding failure is explicit.

The extracted-character limit is independent from the retrieval byte limit.
Excess returns `output_too_large`, records observed length and delivers no partial
content. V1 never truncates silently. Empty visible output is explicit `empty`.

Extracted text lives only in a process-local store with explicit cleanup. SHA-256
covers UTF-8 bytes of the exact delivered text. The artifact byte checksum remains
independent: **ArtifactChecksum != ExtractedContentChecksum**.

Successful parsing establishes neither safety nor semantic authority.
**ExtractedContent != AgentSummary** and
**ExtractedContent != TrustedInstructions**. Prompt-injection text remains page
content; any future Agent consumer requires its own provenance and authority
boundaries.

PDF, specialized XML, Office documents, archives, images, audio/video, OCR,
JavaScript rendering, browser automation, semantic extraction and main-article
selection remain unsupported. Health reports only implemented plain-text/static-
HTML capability and explicitly reports PDF, JavaScript and browser support false.

The adapter package has five modules and 17 deliberate exports. After Slice 9,
Search had nine modules with 119 exports. Direction remains only `search_adapters -> search`;
no consumer, composition or bootstrap wiring exists.

## Cache contracts and policies

Slice 10 defines three independent namespaces and ports: `SearchCache`,
`RetrievalCache` and `ExtractionCache`. Their keys, entries and ports are typed
separately; there is no generic cache backend and no concrete storage.

**SearchCacheHit != FreshSearch**, **RetrievalCacheHit != FreshRetrieval** and
**ExtractionCacheHit != FreshExtraction**. More generally,
**CacheHit != FreshExternalObservation**.

Search keys combine the request's existing semantic content with an explicit
provider scope. Request identity, correlation, causation and occurrence are
excluded, while query, language, locale, limit, requested freshness, categories,
domain constraints, safe-search, purpose and policy remain semantic. Provider A
entries can never satisfy Provider B lookups.

Retrieval keys use source URL, accepted MIME types, maximum bytes, policy and the
other retrieval semantics, without request occurrence. Extraction keys bind the
artifact identity and checksum, capability, extractor identity/version and an
output-policy fingerprint. Artifact checksum or extractor/config version changes
therefore create a different key.

## TTL, age and stale semantics

`SearchCachePolicyV1` supplies finite, bounded and independently configurable
TTLs for all three namespaces. No infinite default exists. Age derives only from
the supplied cache-write and cache-read occurrences; pure assessment functions
do not read a hidden clock.

Reads classify `hit_fresh`, `hit_stale`, `miss`, `invalid` and `unavailable`.
Fresh-only, stale-allowed, future stale-if-error and revalidate-required policies
are explicit. Stale-allowed may make an expired entry usable, but its status
remains `hit_stale`; stale is never promoted to fresh.

Request freshness participates in the Search semantic key independently of TTL.
A TTL-valid entry for a weaker request is incompatible with a stricter request:
**CacheFreshness != SourceFreshness**.

## Compatibility, provenance and payload custody

Assessments detect provider/key mismatch, policy fingerprint mismatch, TTL-policy
version mismatch, schema mismatch, missing references, artifact-checksum mismatch
and extraction-version/config mismatch. Cached observation versions bind the
original factual object's semantic fingerprint. Same entry identity plus the
same facts is idempotent; contradictory facts are diagnosed and never silently
overwritten.

A read assessment preserves original Search, retrieval or extraction occurrence,
cache-write occurrence, cache-read occurrence and age separately. It does not
mutate or re-date the cached fact:
**CacheReadOccurrence != OriginalOccurrence**.

Search entries are metadata-only. Retrieval and extraction entries may describe
transient or explicitly cacheable references, but V1 rejects the reserved
explicit-persistence mode. Metadata whose referenced content has disappeared is
invalid rather than a usable hit:
**CachedMetadata != PersistedWebContent**.

Opaque validator references may state that revalidation is possible. They are
not publication metadata and no HEAD/GET, ETag header or Last-Modified transport
is executed. The three storage ports expose lookup, append and append-oriented
assessment recording; they define no destructive overwrite implementation.

`NO_RESULTS` is cacheable only under explicit Search policy. Provider unavailable,
timeout, malformed response and other operational errors cannot be represented as
a successful cached result set and receive no V1 negative-cache semantics.

After Slice 10, Search had ten modules and 155 deliberate exports and the adapter
package had five modules and 17 exports. No new cross-context edge, consumer,
network authority or SCC was introduced.

## Durable metadata persistence V1

Slice 11 adds `SearchSQLiteDatabase` and append-only metadata stores under
`search_adapters`. The Search domain contains only immutable record, replay,
restart, health and port contracts; dependency direction remains
`search_adapters -> search`.

SQLite V1 uses an explicit absolute controlled path, schema version 1 and a
deterministic migration checksum. Separate tables own requests, provider facts,
results, retrieval, extraction, each cache namespace and cache assessments.
Every factual table and schema/migration history has triggers rejecting both
`UPDATE` and `DELETE`. Writes use bounded `BEGIN IMMEDIATE` transactions,
parameterized values, exact identity/fingerprint reads and optimistic per-stream
sequence checks.

Same record identity and factual fingerprint is idempotent. The same identity or
idempotency key with contradictory facts is rejected. Lineage must exist when
appended; ordered history and replay expose later corruption, missing sequence or
missing lineage instead of repairing it.

## Durable facts and content custody

The typed canonical envelope stores Search requests, provider invocations and
outcomes, normalized result/result-set metadata, retrieval/extraction requests
and observations, cache entries and read assessments. Round-trip reconstruction
runs the original immutable contract validation and verifies canonical payload,
payload checksum and factual fingerprint.

`provider_snippet` remains durable only because it is already an explicitly
bounded field of `NormalizedSearchResultV1`. Persistence adds no raw provider
payload or broader retention surface.

Retrieved bodies, raw HTML/plain text and extracted text are never columns or
automatic payloads. Only identities, checksums, MIME/charset facts, sizes,
limitations, custody/availability facts and opaque references are durable:
**DurableMetadata != DurableWebContent** and
**PersistedReference != AvailablePayload**.

Persisted availability means only what was observed at write time. Restart takes
an explicit current set of available references and emits separate availability
facts. A vanished transient reference remains unavailable; no request is retried
and no historical record or timestamp is changed.

## Replay, restart and integrity health

Replay reconstructs only persisted facts in deterministic `(sequence, record_id)`
order. It never invokes a provider, HTTP retrieval, extractor, cache refresh or
external system: **Replay != External Re-execution**.

Missing sequences, lineage or non-complete records make replay incomplete and
`reconciliation_required`. They never create a successful terminal observation:
**MissingEvidence != Success**.

Persistence health distinguishes schema existence/compatibility, migration
checksum, complete append-only protections, database readability, SQLite
integrity, stored-record encoding/checksum and replay capability. Merely opening
an existing database does not make it healthy.

The three concrete cache adapters preserve separate Search, Retrieval and
Extraction tables and implement append/idempotency, exact semantic-key lookup and
append-only read-assessment history. Lookup never performs revalidation or turns
metadata into available content.

Search now has eleven modules and 179 deliberate exports. The adapter package has
six modules and 25 exports. No consumer, Composition Root or bootstrap wiring is
added.

## Governance, trust and egress integration

Slice 12 adds the consumer-owned `search_integrations` boundary. Its only runtime
edges are `search_integrations -> search` and
`search_integrations -> intelligence_boundary`; neither authority nor Search
imports the other. `ProcessingPurpose.EXTERNAL_SEARCH` and
`ProcessingPurpose.EXTERNAL_RETRIEVAL` extend the taxonomy at its authoritative
owner instead of duplicating it in Search.

The integration maps an immutable Search or Retrieval intent to classified asset
references, policy and capability references, provider/destination scope,
original and disclosed fingerprints, and the authoritative egress request. The
query classifier, minimizer, redactor, provider trust profile, policy decision,
approval and ledger remain owned by Intelligence Boundary. Search never infers
trust and never authorizes itself.

Search provider invocation and source retrieval are different operations and
purposes. Their evidence is bound to operation, request, actor, provider,
destination, purpose, policy, classification, semantic fingerprint and disclosed
payload checksum. A Search authorization therefore cannot authorize an arbitrary
retrieval. Expired, mismatched, stale or invalid evidence fails closed; replay of
a historical `allowed` fact requires current manifest validation.

An `allowed` assessment is emitted only after the authoritative gate returns a
manifest. Denial and approval-required preserve safe codes and opaque decision or
manifest references without policy internals. Missing or unavailable authority
is `unavailable`, never an implicit allow, and approval is never created or
awaited by this pure integration.

`web.search` remains a legacy high-level capability permission and an explicit
prerequisite reference, not an egress grant. In the current worktree the default
permissions file no longer assigns it to agents, while agent configuration and
the legacy builtin still reference it; migration/removal belongs to a later
consumer slice. No permission file is changed here.

A local SearXNG endpoint is represented separately from possible upstream
external processing. Local deployment does not infer provider trust or fully
local processing. Structural destination/SSRF checks in the future HTTP adapter
also remain separate from Governance authorization.

The governing distinctions are:

- **SearchRuntime != NetworkAuthority**
- **EgressAuthorization != ExternalExecution**
- **SearchAuthorization != RetrievalAuthorization**
- **LocalSearXNG != FullyLocalProcessing**
- **AdapterSafetyCheck != GovernanceAuthorization**

No provider invocation, retrieval, HTTP, DNS, cache revalidation, approval wait,
Composition Root wiring or bootstrap activation is added.

## Reserved after Slice 12

HTTP revalidation, background refresh, production composition,
Evidence/citations, Agents/Tools, Perception, raw-content persistence and
unsupported-format extraction remain outside this integration.

## Authorized operational SearXNG transport

Slice 13 adds an explicitly composed stdlib HTTP transport under
`search_adapters` and a consumer-owned executor under `search_integrations`.
The executor validates current Search authorization evidence before handing the
already translated request to the transport. Missing, denied,
approval-required, unavailable, expired, stale, mismatched or invalid evidence
raises a safe blocked result before the first network attempt:
**AuthorizationValidationFailure => ZeroNetworkAttempt**.

Evidence is additionally bound to the provider invocation identity. Request,
actor, provider, configured origin, purpose, policy, disclosed payload and
semantic fingerprint correspondence are checked before execution. Retrieval
authorization cannot be substituted for provider-search authorization.

The transport accepts only the existing SearXNG GET/JSON representation, emits
only `Accept: application/json` and a controlled User-Agent, applies the
invocation timeout and a configurable bounded response read, and performs no
retry. It checks Content-Length when present and enforces the same limit while
streaming. JSON is decoded strictly as UTF-8 and semantic parsing remains solely
in `SearXNGAdapter`.

Redirects are handled explicitly without urllib auto-follow. Same-origin
redirects are bounded; scheme, host or port changes fail closed because the
authorization is scoped to the configured SearXNG origin. Structural transport
safety does not replace Governance authorization.

Transport outcomes distinguish policy-blocking 401/403, unavailable 429/5xx,
timeout, malformed encoding/JSON, invalid SearXNG shape and excessive payload.
`NO_RESULTS` remains a valid successful provider observation. Timeout records
only that the admitted wait elapsed: **TimeoutObserved != RemoteExecutionTerminated**.

Operational health keeps implementation, configuration, authorization
integration, reachability, JSON/API usability, operational Search and possible
upstream external processing as separate facts. Code presence does not promote
unknown runtime facts:

- **TransportImplemented != ProviderReachable**
- **ProviderReachable != SearchAuthorized**
- **SearchAuthorized != SearchSucceeded**
- **LocalSearXNG != FullyLocalProcessing**

Controlled local HTTP server tests prove successful results/no-results, status
and malformed-response mapping, size and timeout bounds, redirect scope and zero
network attempts for every rejected authorization class. No raw provider JSON or
credential is retained by the execution result. Invocation/result persistence
continues to use the existing metadata-only append semantics; authorization
ledger ownership remains with Intelligence Boundary.

No configured SearXNG environment variable or repository endpoint was found
during this slice, so no real-instance smoke was attempted. The implementation
does not install, start or select a public SearXNG instance.

## Reserved after Slice 13

Agents/Tools and legacy `web.search` migration, `/search`, research loops,
automatic source retrieval, Evidence/citations, cache refresh, global
Composition Root and bootstrap activation remained outside Slice 13. The
pre-existing permission mismatch was reserved for the following consumer slice.

## Search Tool and command consumers

Slice 14 replaces the definitive `WebSearchTool` placeholder with a narrow,
consumer-owned `SearchToolPort`. The builtin tool performs the existing
`web.search` permission check and delegates exactly one operation; it imports no
Search provider, Governance implementation, HTTP transport, ranking or research
logic. The concrete `SearchToolConsumer` creates `SearchRequestV1`, while
`ConfiguredSearchOperation` selects one configured provider reference, obtains
Governance assessment and delegates to the authorized execution boundary.

Agents continue to decide whether and what to search. Reformulation, repeated
queries, source comparison and synthesis require separate explicit Agent
decisions: **SearchTool != ResearchAgent**. Neither Agents nor Tools knows
SearXNG or performs HTTP.

Tool output preserves request/result/invocation/provenance references, title,
source URL, provider snippet, deterministic rank, publication date and freshness.
It explicitly leaves retrieved content and evidence absent:
**SearchToolResult != RetrievedSource**. A provider snippet is not promoted to
source content, evidence or final citation.

The `/search` delivery handler continues to call only `web_search`, but now
preserves factual states including `unconfigured`, `unavailable`, `denied`,
`approval_required`, `provider_unavailable`, `timeout`, `malformed_response`,
`no_results` and `results`. It no longer maps an unconfigured provider to
`not_implemented`: **ProviderUnconfigured != NotImplemented**.

`web.search` remains the single canonical public capability permission. The
authoritative permissions file now grants it exactly to the three current Agent
configurations that declare it: Artemis, Orchestrator and Researcher. This only
permits requesting the tool; every external query still requires a separate
Governance decision: **ToolPermission != EgressAuthorization**.

When no Search consumer/provider is locally composed, the default boundary
returns granular factual unconfigured health and performs no fallback, public
provider selection or network access. Global Search Composition Root and
bootstrap wiring remain absent.

## Reserved after Slice 14

Research planning/loops, answer synthesis, final citation rendering, automatic
source retrieval, Perception handoff, real SearXNG configuration and global
Search Composition Root/bootstrap remain outside this slice.

## Explicit retrieval and source evidence projection

Slice 15 adds a consumer-owned, reference-only handoff from a selected normalized
Search result to the existing `RetrievalRequestV1`. The handoff binds Search
request and result-set fingerprints, result/source identity, original and
normalized URL facts, provider provenance, requester, purpose, correlation,
causation, retrieval constraints and a distinct Retrieval policy reference.
Selection validates request, result-set, result, source and provenance
correspondence before a Retrieval intent can be constructed:
**SearchResultAvailable != RetrievalRequested**.

Construction of the handoff and projection performs no HTTP, retrieval,
extraction, cache revalidation or production wiring. The resulting Retrieval
request must pass the existing `EXTERNAL_RETRIEVAL` Governance flow; the Search
policy and any Search authorization evidence are neither copied nor accepted as
Retrieval authority: **SearchAuthorization != RetrievalAuthorization**.

`SearchSourceEvidenceV1` is local to `search_integrations` because the repository
has no generic public Evidence authority suitable for source metadata. Project
Governance Evidence is RFC-scoped and Private Evals Evidence is evaluation-scoped;
neither is repurposed and no second Evidence system is created. The projection
contains only source, provider, occurrence, artifact, checksum, extraction,
cache and provenance references: **SourceMetadata != EvidenceConclusion**.

Projection states distinguish `search_only`, `retrieval_requested`, `retrieved`,
`retrieval_failed`, `extraction_unavailable`, `extracted`, unavailable source
reference and incomplete provenance. A snippet-only projection explicitly states
that source content was not retrieved and extraction is unavailable. A retrieved
artifact without extraction remains an uninterpreted artifact. Completed
extraction preserves extractor/version, content reference/checksum and
limitations, but makes no correctness claim:
**ExtractionComplete != ClaimVerified**.

Publication date, Search occurrence, Retrieval occurrence and Extraction
occurrence remain separate. A recent retrieval never makes an old publication
fresh. When supplied, cache provenance keeps namespace, original observation,
write/read occurrences, age and entry reference. Duplicate results for the same
source preserve every supplied result/provider provenance rather than erasing
origin through representative selection.

The minimum future-citation metadata is source reference/URL, title, provider
and provider-result provenance, publication date when known, occurrences,
artifact checksum/reference and extracted-content checksum/reference. No
Markdown, MLA, APA or other citation text is generated:
**CitationMetadata != CitationRendering**.

External artifact and extracted-content references are always projected as
`untrusted`. No page text becomes an operational instruction, Agent conclusion,
truth score or trust score:
**RetrievedSource != TrustedInstructions** and
**ExtractedContent != TrustedInstructions**.

Metadata-only replay can rebuild the projection from persisted facts without
performing retrieval or extraction again. Raw bodies, extracted text and Agent
claims are not added to persistence by this slice.

## Reserved after Slice 15

Final citation rendering, answer synthesis, autonomous result/evidence selection,
automatic retrieval, browser/PDF processing, Agent research loops, Evidence
submission, global composition, bootstrap and Search Runtime freeze remain
reserved for later explicit slices.

## Local Search Composition Root and capability health

Slice 16 adds the separate, opt-in `search_composition` package. Its only
purpose is local wiring through `build_search_runtime(config, dependencies)`;
neither importing the package nor building a runtime opens a database, performs
Governance assessment, calls a provider, retrieves a source, extracts content,
starts a thread or changes global bootstrap: **Build != Execute**.

Configuration keeps persistence, provider/transport, Retrieval, Extraction and
consumer exposure separate. Provider-specific origin and transport limits stay
in the existing SearXNG adapter configs rather than entering the Search domain.
External Governance is injected. Its absence never creates a permissive fake:
a configured provider without Governance remains degraded and the consumer
returns factual `unconfigured` without network access.

Composition is partial by design. Contracts, adapter and transport can be
implemented while provider configuration is absent. Persistence can be wired
without initializing its schema. Search can be configured while reachability and
API usability remain untested. Retrieval adapter presence keeps external
reachability untested and does not authorize a request. Local plain-text/static
HTML extraction can be available while PDF remains unsupported.

Health is a granular capability projection, not a global `ready` boolean. It
separately reports domain contracts, persistence configuration/schema,
SearXNG adapter/transport/configuration, Governance, per-operation authorization,
reachability, API usability, Search operational state, Retrieval, Extraction,
the three cache namespaces, consumer integration and source evidence projection.
The governing distinctions are:

- **Implemented != Configured**
- **Configured != Reachable**
- **Reachable != Authorized**
- **Authorized != Successful**
- **AdapterImplemented != ExternalCapabilityAvailable**

Provider reachability is not probed by build. The current host expectation
therefore remains provider `unconfigured` unless a caller explicitly supplies a
local configuration; even a supplied origin is `untested` until an explicitly
authorized operation is requested. There is no provider discovery, fallback,
installation or auto-start.

SQLite construction is lazy. `initialize_persistence(occurrence)` is an explicit
local activation that creates/verifies the V1 schema, while
`probe_persistence()` explicitly checks an existing database. Rebuilding over
the same database recovers metadata health without provider, Retrieval,
Extraction or cache-refresh execution.

The controlled composition tests prove an explicitly requested, authorized
Search against the local SearXNG-compatible server for both results and
no-results. Retrieval adapter, Extraction adapter and source projection are
composed independently; Search results never trigger them automatically.
External content remains untrusted throughout the chain.

The only new dependency directions are
`search_composition -> search`, `search_composition -> search_adapters` and
`search_composition -> search_integrations`. There are no reverse imports and
bootstrap does not import the composition package.

## Reserved after Slice 16

Global bootstrap activation, auto-start, provider installation/discovery,
background probes/jobs, autonomous retrieval, research loops, final citation
rendering, Perception interpretation, Deployment Runtime and Search freeze remain
reserved for later explicit work.
