# Canonical memory to conversation — actual integrated journey

Date2026-11-10. Model journey source `0c7386a41b73f9715da290d8546154817ec3b641`.
Windows, Rust1.96/MSVC, Python3.14.3, default-feature actual Core binary.

## Observed journey

The client used only Core's stdin/stdout protocol. Core launched the supervised
Python worker against the actual local LM Studio model. There was no test HTTP
fixture, client `memory_put`, direct provider call or synthetic answer.

1. A source-project chat received the human statement
   `Meu projeto utiliza o identificador RIVA-4796D5.`
2. The real conversation completed. Automatic learning selected its whole source
   statement and wrote `meu-projeto`, kind `fact`, active revision1, with actual
   human message and source job provenance.
3. A different chat in a Presence project referenced exactly that project/key.
   The question asked for the identifier without containing it, and the chat had
   no source conversation history. The actual model replied `RIVA-4796D5`.
4. The reply's durable context metadata identified the correct scope/key,
   revision1, kindfact and raw-content SHA256. Restarting Core preserved the
   identical successful job, reply and selected revision metadata. The target
   chat contained only its own human question and assistant answer.

The initial automatic-memory test had shown source-backed storage and retrieval.
This journey additionally proves that a selected canonical record actually
reaches response generation across chat/project boundaries when referenced.

One existing Qwen3.5 4B alias ran CPU only, context1024, parallel1. Generation
was explicitly128 output tokens,60000ms, reasoning none. No model weights were
downloaded. The validation alias was unloaded afterward; the controller observed
`lms ps` with no loaded models.

## Evidence and review

Artifacts retained in ignored `.superpowers/sdd/2026-11-10-explicit-conversation-context/`:

- `live_context.py`: actual Core subprocess/RPC controller and assertions.
- `synapse-backend-context.exe` SHA256
  `552d8471d175c460ad51232b6efc44794123e070bc4acb4c91fe81bcfe2d0525`.
- `live-773493799aef4a568589a792a3002e90/receipt.json` SHA256
  `b2404776c9c82a9ca96bb7c8a39edba954a0408e2e78960fae482a2723e428d4`.

An independent scoped reviewer checked the helper, matching hashes and receipt,
including the automatic source, separate-chat reply, context digest and restart.
Source-build association and provider/model alias identity remain controller
observations, not reproducible-build proof or cryptographic attestation.

Before review,46 Rust all-feature tests passed (20 actual-binary AI and26 Core).
The independent review found that the health diagnostic still reported schema7
despite the real schema8 migration. Its correction/review is recorded separately
in the execution ledger; the model journey above ran on the stated source and
does not conceal this initial reporting defect.

Correction `3cf866d2689d0f9c2267a61994e28870d80cf72c` now reads actual
`PRAGMA user_version` through the existing transaction. The migration test
recorded RED7-versus8 then GREEN1/1; independent scoped re-review approved the
fix with no new findings. A default-feature rebuild and actual CLI health probe
matched the independently read database version8. Its ignored receipt is
`health-uh9duazp/receipt.json`; executable SHA256 is
`ca191f3ad5c4b4c994340bccab2fff221c3465e0ab7c3050c6c3f77d501492b4`.
Only diagnostic reporting/test expectation changed after the model journey;
the model was not run again for that correction.

## Supported contract and limits

`conversation_start.context` optionally selects at most16 unique `{scope,key}`
references. Only the newest active revision is read; missing or inactive latest
records fail atomically without falling back to stale history. The current chat
and automatic-learning destination keep their original scopes. Explicit external
project references do not copy/promote records or grant tools/mission authority.

Skill guidance, selected memory, chat history and the human message share the
existing64-message/48000-byte request budget and32768-byte per-message bound.
Unrelated keys, older revisions and foreign transcripts are not loaded. Injected
instructions remain untrusted quoted data with no worker-to-Core dispatch path.
The learner still sees only the latest human message, not injected context.

Natural-language project-name resolution, global memory search, general automatic
multilingual canonicalization, planner, Skill evolution, routing, temporary Swarm,
voice/browser adapters, packaging and native frontend remain subsequent work.
This is an integrated conversation milestone, not complete-backend acceptance.
