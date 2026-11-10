# Automatic canonical memory — actual Core and local model

Date: 2026-11-10. Source commit: `85427358ff585450891699e6796725d1ffc8e23c`.
Windows, Rust1.96/MSVC, Python3.14.3, actual `synapse-backend` binary with
default features. Independent code review accepted initial implementation plus
the source-meaning correction; live artifacts were retained for scoped review.

## Actual execution

The CLI controller used stdin/stdout to the real Core, which supervised the
Python worker against LM Studio at numeric loopback. No test HTTP fixture,
manual `memory_put`, extraction command or synthetic response was used.

One existing local Qwen3.5 4B model was loaded under the validation alias,
CPU only, context1024, parallel1. Generation was explicitly configured to
256 output tokens,60000ms, reasoning none. No weights were downloaded.

Human source: `Meu projeto utiliza Rust no núcleo e Python nos componentes de IA.`
The conversation succeeded. Automatic learning produced one active canonical
record, key `projeto`, kind `decision`, revision1. Its content exactly matched
the source and its provenance named the real human message and source job.
The model selected `decision` for a descriptive statement; this demonstrates
fallible semantic typing rather than proof of correct fact classification.
The client retrieved it with the explicit matching project context, restarted
Core, and retrieved the identical record with no extra revision.

A second successful turn queued learning. After it entered running status,
a foreground inference preempted that worker; starting the request took0.416s,
and the actual model replied `OK`. Server logs independently show task535
processing, client disconnection, server cancellation of535, slot release at
1794310509640, then foreground task539 beginning at1794310510128. This confirms
slot release before foreground generation in this observed run. It does not
establish cancellation guarantees for all provider versions, endpoints or
prompt-processing states. No universal server-side acknowledgement protocol is
claimed by the current compatible HTTP adapter.

The owned validation alias was unloaded afterward; `lms ps` showed no loaded
models. The background job was not required to finish again after this
preemption check; interrupted/requeued behavior is covered by binary fixtures.

## Artifact identity

Ignored controller artifacts are retained under the parent program's
`.superpowers/sdd/2026-11-09-integrated-backend/live-model/`:

- `synapse-backend-learning.exe` SHA256
  `9cff3c27785f3f7f4d3df7513220a9d09a208e99a7b37d863a4e6f2bd24736dc`.
- `learning-a525c72627824216bdedb483596b53ce/receipt.json` SHA256
  `ac6c7301cf5ded71c7dfc37458f20998e0fc4cc913fbbcd2be55eaaea8cd2702`.
- `core_learning_validation.py`: actual subprocess controller and assertions.
- `learning-server.log`: retained JSON server events; lines24–38 correlate
  background cancellation with the next foreground task.

The controller built/copied the executable from the stated source. Model identity
is the observed local server alias; neither constitutes cryptographic attestation
of the model or a reproducible independent binary rebuild.
An independent scoped reviewer checked the helper, hashes, receipt and server
log and accepted the observed extraction, restart and provider preemption evidence.

## Verification and limits

Implementation tests:14 actual-binary AI tests,22 Core tests,7 Python tests.
The fix recorded a failing negation-clipping test before its passing regression.
Earlier feature-fault tests passed on the initial implementation; the correction
changed memory admission and its AI tests, not artifact-recovery code.

Automatic admission is deliberately narrow: one complete short source statement,
recognized English/Portuguese first-person prefixes, conservative quotation,
attribution, command and credential exclusions. Many legitimate statements,
long/multiple sentences and other languages will not be accepted by this first
implementation. The model still classifies durability, type and subject key;
these are fallible. No general semantic accuracy, comprehensive secret detector,
automatic multilingual canonicalization or complete memory UX is claimed.
Reply text quality was not evaluated by this smoke.

Memory is one versioned canonical store with project scopes; chat history and
learning job state are separate. Skill guidance/evolution, planner, routing,
temporary Swarm, voice/browser adapters and complete packaging remain subsequent
backend work. This evidence is not acceptance of the entire Synapse backend.
