# Voice durable foundation V1

Voice operational history is stored as append-only facts in
`voice/voice-journal-v1.sqlite3`. Static Voice configuration remains in
`voice/settings.yaml`; PCM/VAD buffers and raw audio are not journal payloads.
`store_raw_audio` remains disabled by default. When policy permits an external
media artifact, the journal contains only its reference, checksum, format,
duration, and retention metadata.

## Record and schema versions

- Canonical record format: `voice-record-v1`.
- SQLite schema and migration: version 1.
- The migration checksum and `PRAGMA user_version` are verified on open.
- Factual rows and migration history reject `UPDATE` and `DELETE`.
- Record identities are opaque UUIDs. Stream identities bind the durable domain
  identity; timestamps are occurrence metadata and do not participate in the
  semantic fingerprint.

The consumer-owned journal boundary supports append with optimistic revision,
exact record/fingerprint read, bounded causal range, replay with completeness
and lineage results, idempotency, and factual persistence health. It exposes no
`latest`, `current`, or implicit-most-recent API.

## Projection and restart

Session, utterance, recording, and synthesis objects are projections of their
ordered facts. They are not a second source of truth. Existing YAML records are
read once and imported only when real legacy files exist; new operational facts
are not written back to the legacy formats. Legacy Avatar/Embodiment fields are
discarded during import without importing those packages.

On runtime construction, an externally active session produces a new
`session.reconciliation_required` fact. The projection becomes
`reconciliation_required`, retains the prior state and pending references, and
marks external state `unknown`. Restart never means paused, resumed, cancelled,
failed, completed, or closed. Explicit evidence is required to reconcile input,
output, STT, TTS, pending transcription/synthesis, speaking, interruption,
cancellation, and artifact availability. Late results append facts and never
rewrite earlier history.

Persistence health distinguishes `available`, `schema_mismatch`,
`migration_mismatch`, `corrupt`, and `unavailable`; provider availability stays
separate. Runtime construction and replay do not execute STT/TTS, open a device,
or play audio.

## Slice 6 reservations

Provider execution supervision, streaming microphone/playback, Sandbox
execution, new providers, frontend events, bootstrap changes, and the existing
`voice -> agents -> tools -> voice` SCC remain outside this foundation.
