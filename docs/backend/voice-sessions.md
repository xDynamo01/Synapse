# Voice Sessions

Voice sessions persist state, previous state, revision, timestamps, settings
snapshot, active recording/utterance/synthesis IDs, conversation ID, and last
error. Valid states are idle, listening, recording, processing, thinking,
speaking, paused, cancelling, cancelled, closed, and error. Legacy queue states
remain readable for stored data.

Every canonical transition validates the current state and optional expected
revision. Pause cancels partial capture and never reopens a microphone. Resume
returns to listening rather than resuming partial recording. Cancel and close
release active recording/synthesis state idempotently.

On runtime restart, listening, recording, processing, thinking, and speaking
sessions recover as paused. Partial recordings and running syntheses are marked
cancelled with `runtime_restarted`; no device is opened automatically.

Conversation turns execute Voice Message STT/analysis, then call only
`ChatRuntime.submit_turn`, persist linkage and synthesis, and return to listening.
Streaming is not simulated. Barge-in cancels persisted synthesis state and
starts a new recording when enabled.
