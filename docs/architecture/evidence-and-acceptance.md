# Evidence and Acceptance

`EvidenceRegistry` stores bounded metadata and safe artifact references for
tests, lint, static analysis, architecture checks, benchmarks, manual checks,
screenshots, log excerpts, migrations, acceptance and reviews. Records preserve
project/RFC/plan/mission/task/attempt provenance, revision, checksum,
classification and correlation. Large payloads remain in controlled artifacts.

Each `AcceptanceCriterion` is independently addressable and is `pending`,
`satisfied`, `failed` or `waived`. A waiver requires reason, actor, policy and
approval. Required criteria must be satisfied or formally waived, and evidence
must exist, before an RFC can become `implemented`.

Quality gates are descriptors. Execution is available only through the
canonical Tool Execution Boundary; Project Governance contains no shell or
subprocess path. `EvalReference` is reference-only in this phase. Private eval
datasets are not implemented or exported to providers.
