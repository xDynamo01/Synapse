# Hierarchical memory validation — 2026-10-23

> Historical results from the memory implementation. The subsequent backend
> corrective validation passed 4623 tests with no failures on 2026-10-24; see
> [current backend validation](backend-readiness.md) for the latest evidence and
> the five platform-dependent skipped tests. Counts below retain the original run.


## Scope and audit

Profile: bounded-context-change, Memory / RAG / Agent Runtime / Workspace Context.
Only the active `F:/Projetos/Synapse` checkout was changed. Existing dirty voice,
frontend, MoM and swarm work was preserved; no version, stage, commit or push change.

The audit found a reusable canonical MemoryStore and schema-1 JSON persistence,
consumer-owned Context Fusion ports, explicit Project Knowledge RAG intent, and
existing agent/project identity contracts. Concrete problems addressed: full record
reads on retrieval, a lock covering save but not read/modify, missing selected
fusion evidence in the model payload, eager legacy memory injection, and
uncoordinated final prompt truncation.

## Implemented paths

- `backend/synapse/memory`: workspace/episodic/working scopes; typed kinds,
  verification/provenance, history-preserving replacement, invalidation, transaction
  lock, derived metadata/offset index, scope discovery and bounded consolidation.
- `backend/synapse/context`, `context_fusion`, `chat/runtime.py`: selected workspace,
  current summary priority, source failure reporting and legacy compatibility.
- `backend/synapse/models/budget.py`, adapters/router and model-provider adapters:
  selected-model context allocation, preserved core/current input, low-authority
  evidence, output reservation, no second truncation of budgeted requests, metrics.
- Composition, memory API and agent memory tools: canonical wiring, index discovery,
  scoped remember/recall, explicit cross-workspace comparisons, background consolidation.

## Executed evidence

| Check | Result |
| --- | --- |
| A-J and additional persistence/authority/tool tests plus new architecture boundaries | 19 passed in the specific run; see `artifacts/reports/memory-hierarchy-final-specific.txt` |
| Memory/context/chat/LM Studio regression | 66 passed, 4 failed, one warning; failures concern existing local-chat default/selection expectations |
| Active backend type checking | 826 source files passed after correcting the chat history list type |
| Dependency graph comparison | 313 runtime edges before/after; no added edges; same 11-context/31-edge pre-existing SCC |
| Live installed model | Gemma 2 2B returned `F:/Projetos/Synapse` from temporary workspace memory; provider result was real, not a canned response |
| Canonical storage scale | 3001 fixture records; discovery/retrieval prohibited `storage.load()` and still recovered the single old matching decision; final prompt stayed bounded |
| Global architecture | 252 passed, 19 failed on the broad baseline run; details below |
| Global backend regression | 4573 passed, 35 failed, 5 skipped, 4 subtests passed in 1923.99s; broad run preceded the final targeted fixes below |
| Final chat/tool/memory/boundary regression | 56 passed; `memory-hierarchy-chat-final.txt` |
| Final changed-file Ruff and diff check | Passed; no whitespace errors |
| RAG and primary-agent regression | 23 passed; `memory-hierarchy-rag-regression.txt` |
| MoM regression after prompt-contract update | 23 passed; `memory-hierarchy-mom-final.txt` |
| Global Ruff | 4 import-order errors in unrelated speech-adapter, LM Studio test, operational-projection test and theme-assets test files |

The live probe used isolated temporary runtime data and shut down its own local
model server. It did not populate production memory. The pure transport test
uses a capture adapter and is explicitly distinguished from the real model probe.

Architecture failures include stale 312-edge expectations (the pre-task graph
already has 313), earlier voice adapter/transport inventory additions, deployment
adapter edge expectations and route counts. This slice adds exactly one authorized
index endpoint; the frozen route assertion was advanced by exactly that one path
and operation, retaining the remaining baseline checks. No SCC expectation was
relaxed. Comparison evidence is `artifacts/reports/memory-hierarchy-graph.json`.

The initial Mypy command included generated `backend/dist` dependencies and reported
130 errors. That is not the active-source gate. The corrected global source command
checks `backend/synapse` with `--no-incremental` and passes all 826 active files.

## Final regression follow-up

The broad run exposed five failures related to the changed retrieval/prompt contract.
Three tests expected retrieved memories or preferences in the system message or
silent truncation of essential instructions; these now assert user-side evidence
and explicit budget overflow. The tool-receipt test now checks role separation
instead of an obsolete exact warning string. The legacy restart test previously
used an already-seeded English profile to answer a Portuguese name question without
actually saving the asserted name. It now explicitly saves `Nome: Arthur`, then
checks retrieval after restart. Legacy query tokenization also strips punctuation
so `nome?` matches `Nome:`. No automatic conversational fact learning is claimed.

All 56 tests in the final focused chat/tool/memory/boundary run passed, recorded in
`artifacts/reports/memory-hierarchy-chat-final.txt`. This is a targeted rerun, not
a second full-suite pass; the original global counts above remain unchanged.

The four local-chat provider failures were reproduced with task-modified clean
modules loaded from HEAD in memory (`memory-hierarchy-provider-baseline.txt`).
The observability correlation and desktop activity failures were similarly
reproduced (`memory-hierarchy-extra-baseline.txt`). Voice/provider-readiness failures
remain outside this task; their configuration expectations were not relaxed.
Not every global failure was independently baseline-replayed, so global readiness
is explicitly not claimed.

## Limits

- New per-workspace permissions are enforced by the existing permission manager;
  no production permission grants were silently widened. A caller lacking grants
  gets a denial/unavailable-retrieval warning, not access inferred from its role name.
- Memory-record search is lexical/structured; learned semantic document retrieval
  remains in the existing Project Knowledge component under explicit intent.
- Index bootstrap/recovery and writes still deserialize the canonical collection;
  steady-state retrieval only reads chosen bodies. No database-scale write claim.
- Background consolidation is selective and process-local. Pending is not saved;
  graceful close drains the queue. Only committed records survive abrupt restart.
- Budgeting uses explicit estimates, not an exact tokenizer for every provider.
- System-role separation is enforced; semantic injection resistance still depends
  on the model as well as tool authorization. No universal model-security claim.
- Global failures keep the backend NOT READY; passing this slice is not global readiness.
