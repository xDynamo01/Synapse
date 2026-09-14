# Project Knowledge RAG

Project Knowledge retrieval is explicit by default. A conversation being linked
to a project is scope, not authorization to query project knowledge.

## Contract

`synapse.retrieval_intent.RetrievalIntent` is the provider-neutral contract used
before any retrieval work. Current values are:

- `NONE`
- `PROJECT_KNOWLEDGE`
- `FILE_SEARCH`
- `WEB_SEARCH`

The active policy mode is equivalent to `EXPLICIT`. `AUTO` is reserved for a
future design and is not enabled in this slice.

## Text and voice affordances

Text can produce project retrieval intent with:

- `/project <query>`

Voice can produce the same internal intent only for conservative explicit
phrases such as:

- “pesquise nesse projeto ...”
- “procure nos arquivos ...”
- “consulte os documentos do projeto ...”
- “busque no conhecimento do projeto ...”

Generic project-related phrasing does not trigger RAG. Examples that stay as
ordinary chat:

- “como funciona esse projeto?”
- “me explique essa arquitetura”
- “o que você acha desse projeto?”

## Decision boundary

The final decision is made by Chat Runtime:

`RetrievalIntent.PROJECT_KNOWLEDGE + valid project scope => project knowledge may be queried`

Otherwise, Context Fusion receives `include_project_knowledge=false`, and the
knowledge scope is not queried.

Voice Runtime does not import or execute Knowledge/RAG/vector-store behavior. It
only passes a normalized retrieval directive to Chat Runtime.

## Provenance

Retrieved project knowledge remains external retrieved content. It must keep
provenance metadata and must not become a trusted system/operator instruction.

Required invariants:

- `ProjectAssociation != RetrievalAuthorization`
- `SlashCommand != RetrievalAuthority`
- `VoiceIntent != RetrievalExecution`
- `RetrievedContent != TrustedInstruction`
- `NoExplicitRetrievalIntent => NoProjectKnowledgeQuery`

## Ingestion lifecycle

Project attachments are not treated as retrievable knowledge at upload time.
Upload can only schedule ingestion. The ingestion lifecycle is persistent and
restart-safe:

1. `QUEUED`: an attachment was accepted for a project, but no index is ready.
2. `READING`: source bytes are being read from the backend-owned attachment.
3. `CHUNKING`: source text is being split into deterministic chunks.
4. `INDEXING`: chunk index entries are being produced.
5. `READY`: the document version, chunks, and index entries are retrievable.
6. `FAILED`: ingestion failed and remains inspectable.
7. `STALE`: a newer ready version superseded this version.
8. `REMOVED`: the document is intentionally unavailable for retrieval.

Scheduled does not mean indexed. Only `READY` document versions are returned by
retrieval.

## Identity model

Project Knowledge keeps separate identities for separate responsibilities:

- `ProjectDocument`: stable project-level document identity.
- `ProjectDocumentVersion`: immutable source checksum and parser/chunker/indexer
  version facts for a specific ingest.
- `DocumentChunk`: source offsets and text content.
- `IndexEntry`: retriever-owned lookup state for a chunk.
- `RetrievedEvidence`: temporary evidence returned to Chat/Context Fusion.

The lexical baseline uses deterministic index entries so retrieval can be
validated without an external provider. Canonical vector similarity and learned
semantic retrieval are optional and local-first. This does not change the
retrieval policy and does not enable automatic RAG.

## Retrieval and mutation boundaries

Retrieval is project-scoped and ready-only. Context Fusion can read the
`knowledge` memory scope only when Chat Runtime has already accepted explicit
Project Knowledge retrieval intent and a valid project scope exists.

Document removal marks the document, ready versions, lexical index entries, and
semantic index entries as removed. Reindexing creates a new ready version from
the current ready chunks and stales the previous ready version. Reindex is not
replay, and replay is not retrieval authorization.

## Retrieval quality pipeline

Project Knowledge retrieval is a deterministic pipeline:

`explicit retrieval intent -> scoped retrieval -> candidate generation -> ranking -> deduplication -> evidence selection -> context budget -> provenance-preserving projection`

The lexical index remains the baseline candidate generator. Canonical similarity
and learned semantic candidates are generated separately when their capabilities
are available. Hybrid retrieval fuses lexical candidates with learned semantic
candidates first; when learned semantic retrieval is unconfigured or unavailable,
the legacy canonical similarity path remains an auxiliary fallback. Raw lexical,
canonical, and learned scores are not added directly.

Current ranking facts are explicit:

- `lexical_score`: query terms matched by the indexed chunk.
- `semantic_score`: cosine similarity from the optional local embedding index,
  or `null` when there was no semantic hit.
- `lexical_rank` and `semantic_rank`: independent candidate ranks before fusion.
- `lexical_rrf` and `semantic_rrf`: reciprocal-rank values used for fusion.
- `fusion_strategy`: currently `reciprocal_rank_fusion`.
- `freshness_contribution`: current ready document versions receive the freshness
  contribution because historical versions are excluded from normal retrieval.
- `locality_contribution`: earlier chunks receive a small deterministic locality
  contribution to preserve stable structural ordering.
- `diversity_contribution`: currently explicit and zero; diversity is enforced by
  selection limits rather than invented corroboration.
- `duplicate_penalty`: applied when multiple candidates normalize to the same
  duplicate key.
- `final_ranking_score`: weighted sum used only for deterministic ordering.

The semantic seam is `IndexedCandidate -> ranking facts -> RetrievedEvidence`.
No remote embedding/vector provider is required or active in this slice.

## Semantic capability and embedding identity

Semantic retrieval is controlled by factual capability state:

- `available`
- `unconfigured`
- `unavailable`
- `degraded`
- `incompatible`
- `failed`

The current embedding mechanism is `synapse-local-canonical-embedding`.
It is deterministic, local, and offline. It maps normalized/canonical terms into
a fixed-size vector and stores the vector in SQLite. It is not a learned
semantic embedding model. It establishes the provider-neutral vector index
contract without introducing OpenAI, Gemini, Ollama, LM Studio, FAISS, Chroma,
Qdrant, or network dependency.

Learned local embeddings live behind the separate `synapse_learned_local`
provider seam. Production startup does not require the learned model to load.
The Composition Root enables the provider only when
`SYNAPSE_PROJECT_KNOWLEDGE_LEARNED_EMBEDDINGS` is explicitly truthy. If no local
learned model path/runtime is configured, the provider reports `unconfigured`,
and retrieval continues through lexical/canonical fallback without claiming
learned semantic success.

The first measured learned provider target is `intfloat/multilingual-e5-small`
through the optional `sentence-transformers` runtime. Model location is
configurable with:

- `SYNAPSE_PROJECT_KNOWLEDGE_EMBEDDING_MODEL_ID`
- `SYNAPSE_PROJECT_KNOWLEDGE_EMBEDDING_MODEL_VERSION`
- `SYNAPSE_PROJECT_KNOWLEDGE_EMBEDDING_MODEL_PATH`
- `SYNAPSE_PROJECT_KNOWLEDGE_EMBEDDING_DIMENSION`
- `SYNAPSE_PROJECT_KNOWLEDGE_EMBEDDING_DEVICE`

When no explicit path is supplied, Synapse looks under
`data/models/embeddings` and can resolve a Hugging Face snapshot cache path. E5
`query:` and `passage:` prefixes are applied inside the provider adapter only;
stored chunks and user queries are not mutated with provider-specific text.

Every semantic index entry is bound to:

- document version;
- chunk;
- embedding model id;
- embedding model version;
- embedding dimension;
- normalization/configuration version through the content fingerprint;
- semantic index version;
- source checksum;
- normalized content fingerprint.

This preserves:

- `ChunkIndexed != EmbeddingCurrent`
- `LexicalScore != SemanticScore`
- `CanonicalVectorSimilarity != LearnedSemanticEmbedding`

## Hybrid fusion and fallback

Hybrid retrieval uses Reciprocal Rank Fusion. Lexical and learned semantic
candidates produce independent ranks; the ranker combines those ranks and then
applies the same deterministic deduplication, diversity, neighborhood, and
context-budget rules as lexical retrieval. The calibrated learned threshold for
the current corpus is `0.82`; the canonical similarity threshold remains separate
at `0.55`.

If semantic capability is disabled, unavailable, degraded, incompatible, failed,
or stale, retrieval falls back to lexical mode when explicit Project Knowledge
retrieval was already authorized. Absence of semantic search is not treated as
absence of RAG.

Query embeddings are generated only inside Project Knowledge retrieval after
explicit retrieval intent and project scope have already been accepted upstream.
Ordinary chat does not request query embeddings.

This preserves:

- `NoExplicitRetrievalIntent => NoQueryEmbedding`
- `HybridCandidates != ContextPayload`

## Project Files UI

The frontend exposes `Arquivos do Projeto` as a project-scoped management
surface. It is available through the side rail and the `/project.files` composer
command. Opening the surface lists backend Project Knowledge document facts for
the active project; it does not run retrieval, does not inspect the filesystem,
and does not generate query embeddings.

The list endpoint is `/api/project-knowledge/documents`. It returns document
records with:

- display name;
- document status;
- current version when available;
- chunk count;
- ingestion/readiness facts;
- safe failure facts;
- Project Knowledge capabilities.

The UI maps only factual lifecycle states:

- `queued`
- `reading`
- `chunking`
- `indexing`
- `ready`
- `failed`
- `stale`
- `removed`

`READY` means the backend reports the document version as retrievable. It is not
a claim that the document content is correct.

The surface also shows a compact learned semantic provider fact, such as local
semantic search being ready, loading, unavailable, incompatible, failed, or not
configured. Learned semantic failure does not block the document list and is not
reported as full RAG failure when lexical retrieval remains available.

The UI supports explicit `Reindexar` and `Remover` actions through the existing
Project Knowledge mutation routes. Reindex disables duplicate accidental clicks
while an operation is active. Removal requires confirmation and marks the
document unavailable for project retrieval according to backend semantics.

This preserves:

- `UploadCompleted != DocumentIndexed`
- `ReindexRequested != ReindexCompleted`
- `ProjectAssociation != RetrievalAuthorization`
- `OpeningProjectFiles != ProjectKnowledgeQuery`
- `ListingDocuments != QueryEmbedding`
- `SemanticUnavailable != RagUnavailable`

## Semantic cache and reindex semantics

The embedding cache key is:

- normalized content fingerprint;
- embedding model id;
- embedding model version;
- embedding dimension.

The normalized content fingerprint is provider/model/config bound, so canonical
vectors and learned vectors cannot share a cache entry. Embeddings from
incompatible versions are not reused. A model, dimension, or semantic index
version mismatch marks semantic entries stale/reindex-required for the current
semantic index without requiring rechunking.

This preserves:

- `EmbeddingReindex != DocumentRechunk`

## Deduplication and diversity

Deduplication happens before final projection. Identical and near-identical text
normalize to a duplicate key; only one selected evidence item is projected, while
duplicate source provenance remains in `duplicate_sources`.

This preserves:

- `IndexedCandidate != SelectedEvidence`
- `DuplicateEvidence != SameSource`
- `MultipleResults != IndependentCorroboration`

Source diversity is enforced with `max_chunks_per_document`, so one document
cannot fill the entire selected context when other relevant documents exist.

## Context budget and neighborhood

Retrieval has an explicit context budget before the model sees evidence:

- `max_chunks`
- `max_characters`
- `max_chunks_per_document`

Highly relevant chunks can include adjacent chunk context only when the neighbor
belongs to the same document and version, is not duplicated, and fits the same
budget. The LLM context limit is not the first or only budget control.

This preserves:

- `RetrievedCandidates != ContextPayload`
- `RetrievedContent != TrustedInstruction`
