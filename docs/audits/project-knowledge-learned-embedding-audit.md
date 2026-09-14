# Project Knowledge Learned Embedding Audit

Date: 2026-09-08

## Findings

The legacy `synapse-local-canonical-embedding` remains classified as deterministic
canonicalization plus hashed vector similarity. It is not a learned semantic
embedding model and is retained only as canonical similarity fallback/diagnostic
support.

The learned local provider was provisioned and benchmarked with a real local
model. Retrieval quality improved for paraphrase and synonym/concept queries
when calibrated at threshold `0.82`, while weak/unknown and cross-project queries
remained controlled in the benchmark corpus.

## Provider provisionado

Provider: `synapse_learned_local`

Model: `intfloat/multilingual-e5-small`

Revision/version measured:
`614241f622f53c4eeff9890bdc4f31cfecc418b3`

Runtime: `sentence-transformers` local adapter, lazy-loaded.

Dimension: `384`

Normalization: provider-level normalized embeddings with E5 prefixes:

- query text: `query: <text>`
- chunk text: `passage: <text>`

Local snapshot measured at:
`data/models/embeddings/models--intfloat--multilingual-e5-small/snapshots/614241f622f53c4eeff9890bdc4f31cfecc418b3`

Measured snapshot footprint: `2174.57 MiB`. This is a full Hugging Face snapshot
and includes extra artifacts beyond the minimal PyTorch path.

## Capability probe

Measured capability:

- status: `available`
- provider: `synapse_learned_local`
- model: `intfloat/multilingual-e5-small`
- version: `614241f622f53c4eeff9890bdc4f31cfecc418b3`
- dimension: `384`
- learned semantic: `true`
- configured before load: `true`
- loaded before first embedding: `false`
- loaded after first embedding: `true`
- measured device: `cpu`

The adapter preserves:

- `ModelConfigured != ModelLoaded`
- `ModelLoaded != SemanticQualityValidated`

The Composition Root enables learned embeddings only when
`SYNAPSE_PROJECT_KNOWLEDGE_LEARNED_EMBEDDINGS` is explicitly truthy.
The device preference is configurable through
`SYNAPSE_PROJECT_KNOWLEDGE_EMBEDDING_DEVICE`; the measured run used CPU.

## Benchmark

Corpus: same evaluation categories as the prior Project Knowledge benchmark:

- exact lexical;
- paraphrase;
- synonym/concept;
- distractor;
- weak/unknown;
- cross-project.

Modes compared:

- lexical;
- canonical;
- learned;
- hybrid.

Calibrated threshold: `0.82`.

| Mode | HitRate@1 | HitRate@3 | HitRate@5 | MRR | Precision | Recall@5 | ZeroResultCorrectness |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lexical | 0.50 | 0.50 | 0.50 | 0.50 | 0.50 | 0.42 | 1.00 |
| canonical | 1.00 | 1.00 | 1.00 | 1.00 | 0.88 | 0.83 | 1.00 |
| learned @ 0.82 | 1.00 | 1.00 | 1.00 | 1.00 | 0.71 | 0.92 | 1.00 |
| hybrid @ 0.82 | 1.00 | 1.00 | 1.00 | 1.00 | 0.71 | 0.92 | 1.00 |

Selected-context recall is represented by `Recall@5` after retrieval,
deduplication, diversity, and context budget selection. This preserves:

- `CandidateRecall != ContextRecall`
- `NearestCandidate != RelevantEvidence`

## Paraphrase / synonym quality

At threshold `0.82`:

- paraphrase HitRate@1: `1.00`
- synonym/concept HitRate@1: `1.00`

Lexical baseline failed both categories. Learned retrieval therefore demonstrates
real semantic improvement on the evaluation corpus.

## Distractor / weak-query behavior

At thresholds `0.70` and `0.75`, learned retrieval returned too many weak and
cross-project-adjacent candidates. Those thresholds were rejected.

At threshold `0.82`:

- weak/unknown ZeroResultCorrectness: `1.00`
- cross-project ZeroResultCorrectness: `1.00`
- distractor HitRate@1: `1.00`
- distractor Precision: `0.50`

The distractor precision is lower than canonical similarity, but the top result
remains correct and the weak/cross-project gates are controlled.

## Performance cold/warm

Provisioning:

- model download/resolve: `90775.103 ms`
- local snapshot size: `2174.57 MiB`

Cold model measurement:

- RSS before load: `25.26 MiB`
- cold load + first embedding: `90288.812 ms`
- embedding dimension: `384`
- RSS after load: `826.33 MiB`
- warm embedding: `18.274 ms`

Benchmark runtime after provisioning:

- batch document indexing: `10404.838 ms`
- lexical evaluation: `4.181 ms`
- canonical evaluation: `75.898 ms`
- learned evaluation: `202.147 ms`
- hybrid evaluation: `20.623 ms`

Offline/restart/cache measurement:

- `HF_HUB_OFFLINE=true`
- `TRANSFORMERS_OFFLINE=true`
- cache rows before query: `12`
- cache rows after first learned query: `13`
- learned first query after indexed cache: `33.076 ms`
- hybrid query after runtime restart: `2.591 ms`

## Offline behavior

After local provisioning, learned and hybrid retrieval worked with Hugging Face
and Transformers offline flags enabled. No query-time remote API is required.

## Packaging impact

`sentence-transformers` is kept as an optional `rag` dependency. Adding it to
the core dependency set pulls Torch and large transitive packages, including CUDA
artifacts in the lock graph. The desktop sidecar should not embed the learned
model snapshot or force the optional runtime into the default package without a
separate distribution decision.

The default sidecar build explicitly excludes:

- `sentence_transformers`
- `transformers`
- `torch`
- `sklearn`
- `scipy`

Measured sidecar build result:

- output: `backend/dist/synapse_backend`
- size: `587.55 MiB`
- `torch` present: `false`
- `transformers` present: `false`
- `sentence_transformers` present: `false`

This is a packaging/distribution decision, not a semantic retrieval failure.

## Fallback

If the learned provider is unconfigured, unavailable, incompatible, or failed,
Project Knowledge falls back to lexical retrieval, with canonical similarity
remaining available for compatibility/diagnostics when enabled. The runtime does
not report canonical results as learned semantic success.

## Decision

`LEARNED_SEMANTIC_RETRIEVAL_VALIDATED`
