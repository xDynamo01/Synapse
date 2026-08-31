# Voice–Perception–Conversation Integration V1

## Authority map

Voice owns microphone, session, utterance, transcription, turn-taking,
interruption, synthesis, and playback lifecycle. Perception owns observations,
derived features, model inferences, correlation, provenance, and retention.
Conversation/Agents own interpretation, intent, reasoning, responses, and tool
decisions. Correlation never transfers any of these authorities.

## Reference-only flow

The bounded flow is:

`Voice utterance -> STT fact -> transient Perception request -> perceptual bundle reference -> Conversation request -> response reference -> Voice acceptance`

The Perception request carries the Voice session, utterance, transcription,
checksum reference, occurrence range, actor, correlation, and provenance. PCM is
passed only to the local in-process adapter for immediate computation and is not
written into the request, bundle, journal, or Conversation boundary.

A perceptual bundle contains immutable artifact references with taxonomy,
provider/algorithm/model version, confidence when supplied, occurrence,
lineage, sensitivity, and retention. It contains no raw media and no generic
emotion, engagement, intent, or meaning field. Context Fusion is not needed for
this point-to-point envelope and remains a read-only correlator elsewhere.

The Conversation-owned request keeps transcript reference/content separate from
the optional perception bundle. Transcript content is omitted unless explicitly
allowed by `persist_transcript_content`. Perception can be `available`, `partial`,
`unavailable`, `not_requested`, or `pending`; unavailable Perception never creates
fake feature values and does not block a valid transcript request.

## Response correspondence and races

Response acceptance validates response, request, conversation turn, Voice
session, utterance, transcription, and correlation identities plus an explicit
deadline. A repeated identical response is a factual duplicate. Reuse of a
response identity with different content is contradictory and rejected.

Receiving a response does not synthesize or play it. `synthesize_response` is a
separate explicit Voice operation. A newer utterance supersedes the active
Conversation request without deleting history; a response for the superseded
request is stale. Late Perception is recorded against its original request and
does not rewrite the current turn. Barge-in remains a Voice lifecycle event.

## Persistence and restart

When a Voice journal is supplied, integration facts and reference-only requests
are appended to the existing Voice SQLite journal. Restart replay restores
pending Perception/Conversation status or accepted response references as
`reconciliation_required`. It does not reopen the microphone, recompute
Perception, resubmit Conversation reasoning, synthesize, or start playback.

## Controlled E2E and limitations

The controlled test journey uses a fake microphone/VAD/STT and Conversation
producer with the real local acoustic Perception adapter. It verifies bundle
taxonomy/lineage, response correspondence, and the absence of raw PCM from
durable boundaries. Piper is not required and no Agent or tool is selected or
executed automatically.

Slice 11 may add composition decisions or additional explicitly authorized
consumers. This slice does not activate global bootstrap, frontend events,
providers, models, camera capabilities, Search, Deployment, or Sandbox drivers.
