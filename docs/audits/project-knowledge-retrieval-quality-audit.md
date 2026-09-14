# Project Knowledge Retrieval Quality Audit

Date: 2026-09-08

Scope: Project Knowledge / RAG — Retrieval Quality Evaluation + Semantic
Capability Validation.

## Implementation audited

`synapse-local-canonical-embedding` is not a learned semantic embedding.

The vector is produced by:

1. lowercasing the text;
2. extracting word-like terms;
3. applying a small explicit synonym/canonicalization map;
4. hashing each canonical term with SHA-256;
5. assigning each term to one of 32 deterministic vector buckets;
6. adding deterministic per-term weight;
7. L2-normalizing the vector;
8. comparing query/document vectors with cosine similarity.

Technical classification: deterministic synthetic lexical/vector similarity
with a tiny hand-authored synonym map. It can recover only relations encoded by
normalization/canonicalization or accidental hash-bucket similarity. It does not
learn meaning from data.

## Corpus

Synthetic Project Knowledge corpus:

| Project | Document | Purpose |
| --- | --- | --- |
| project-a | exact-rollback.txt | exact lexical match |
| project-a | vehicle-repair.txt | paraphrase/synonym target |
| project-a | module-failure.txt | synonym/concept target |
| project-a | vehicle-distractor.txt | similar vocabulary but wrong answer |
| project-a | duplicate-a.txt | duplicate content |
| project-a | near-duplicate.txt | near duplicate |
| project-b | cross-project-dog.txt | relevant only outside queried project |

Query categories:

- exact lexical;
- paraphrase;
- synonym/concept;
- distractor;
- weak/unknown;
- cross-project.

Each query was executed with fixed parameters in three modes:

- lexical only;
- semantic only;
- hybrid RRF.

Evaluation is performed after ranking, deduplication, diversity limits, and
context budget. This means `CandidateRecall != ContextRecall`.

## Metrics

Global selected-context metrics:

| Mode | HitRate@1 | HitRate@3 | HitRate@5 | MRR | Precision | Recall@5 | Zero-result correctness |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lexical | 0.50 | 0.50 | 0.50 | 0.50 | 0.50 | 0.42 | 1.00 |
| semantic | 1.00 | 1.00 | 1.00 | 1.00 | 0.88 | 0.83 | 1.00 |
| hybrid RRF | 1.00 | 1.00 | 1.00 | 1.00 | 0.88 | 0.92 | 1.00 |

Category HitRate@1:

| Category | Lexical | Semantic | Hybrid |
| --- | ---: | ---: | ---: |
| exact lexical | 1.00 | 1.00 | 1.00 |
| paraphrase | 0.00 | 1.00 | 1.00 |
| synonym/concept | 0.00 | 1.00 | 1.00 |
| distractor | 1.00 | 1.00 | 1.00 |
| weak/unknown | 0.00 | 0.00 | 0.00 |
| cross-project | 0.00 | 0.00 | 0.00 |

Zero-result correctness:

| Category | Lexical | Semantic | Hybrid |
| --- | ---: | ---: | ---: |
| weak/unknown | 1.00 | 1.00 | 1.00 |
| cross-project | 1.00 | 1.00 | 1.00 |

## Hybrid analysis

Hybrid RRF improved recall over lexical baseline on this corpus:

- lexical Recall@5: 0.42;
- semantic Recall@5: 0.83;
- hybrid Recall@5: 0.92.

Hybrid did not degrade top-1 in this corpus:

- lexical HitRate@1: 0.50;
- hybrid HitRate@1: 1.00.

Hybrid produced results different from lexical for paraphrase and synonym/concept
queries. It did not merely reorder the same lexical candidates.

Known limitation: paraphrase precision was 0.50 because the semantic vector also
selected `vehicle-distractor.txt`. This shows the current mechanism can recover
hand-canonicalized relations, but does not reliably separate close distractors.

## Weak-query behavior

Weak/unknown and cross-project queries returned no selected evidence in all
modes.

This preserves:

- `NearestCandidate != RelevantEvidence`
- `NoExplicitRetrievalIntent => NoProjectKnowledgeQuery`
- `RetrievedContent != TrustedInstruction`

## Provenance and trust

The evaluation checks selected evidence for:

- document id;
- version id;
- chunk id;
- source checksum;
- project isolation;
- `trusted_instruction=false`.

Project B content did not leak into Project A semantic retrieval.

## Performance

Approximate local measurements on the synthetic corpus:

| Measurement | Result |
| --- | ---: |
| indexing cost for 7 documents | 763.036 ms |
| ready semantic index entries | 7 |
| cache entries before restart | 6 |
| semantic first query after restart | 8.999 ms |
| semantic repeated query after cache hit | 1.165 ms |
| lexical evaluation latency | 3.134 ms |
| semantic evaluation latency | 58.891 ms |
| hybrid evaluation latency | 9.723 ms |

The cache did not grow on the repeated semantic query:

- after first query: 7 cache entries;
- after second query: 7 cache entries.

## Threshold assessment

The semantic candidate threshold is conservative enough to avoid the weak and
cross-project false positives in this corpus. It is not enough to distinguish
the vehicle repair target from the vehicle distractor. Threshold tuning alone is
unlikely to make the current deterministic embedding robust because the vector
does not model meaning beyond canonicalized terms.

## Decision

Classification:

`SEMANTIC_CAPABILITY_LIMITED`

Reason:

The current mechanism improves retrieval for the hand-covered paraphrase and
synonym/concept cases where lexical alone fails. However, it is a deterministic
synthetic lexical/vector similarity mechanism, not a learned semantic embedding.
It should remain optional and should not be presented as robust semantic
understanding.

Recommended next slice if better semantic behavior is required:

Evaluate a local-first learned embedding model behind the same provider-neutral
embedding port, keeping the current lexical baseline and fallback. Do not remove
the lexical baseline.
