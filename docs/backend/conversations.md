# Conversations

## Status

Conversation is the durable communication aggregate. `ChatRuntime` is an
interface over it; it is not a second source of conversation state.

## Contracts

A conversation stores its ID, type, title, status, participants, typed
participant records, active agent/model metadata, timestamps, metadata, and
revision. Supported statuses are `active`, `paused`, `closed`, and `archived`.

Messages preserve sender/receiver identity, sender type, role, content parts,
attachments, model metadata, tool results, correlation/causation, parent,
idempotency key, status, timestamps, and structured error. Statuses include
`pending`, `streaming`, `completed`, `delivered`, `acknowledged`, `failed`, and
`cancelled`.

Content parts support text, code, file/image/audio references, tool result, and
structured data. Binary data is never embedded in the message record.

## Persistence

Each conversation is stored below `DATA_DIR/conversations/{id}`. Conversation
and summary YAML use structured atomic writes. Message JSONL is rewritten via a
temporary file and atomic rename for status changes and append operations.
Ordering is file order and IDs remain stable after restart.

Messages support bounded pagination (`offset`, `limit`) and idempotency within a
conversation. Revision-checked updates return a structured conflict instead of
silently overwriting concurrent changes.

## Participants

Agents are validated through `AgentRegistry`. `local_chat` represents the
authenticated user-facing participant boundary and does not invent an agent
identity. Add/remove operations persist joined/left timestamps. An agent cannot
send as another participant because sender and target are explicit at the
canonical turn boundary.

## Attachments

Attachments contain filename, MIME type, size, storage reference, checksum,
owner, conversation, status, timestamps, and metadata. Registration rejects
traversal, missing files, invalid size, missing MIME/checksum, and references
outside `DATA_DIR`. The current size ceiling is 25 MiB. Format interpretation is
deferred to dedicated processors.

## Summary

Production exposes no heuristic or fake summary. `ChatRuntime` generates a
summary through the configured agent/model contract. Missing agent/provider,
empty conversation, provider failure, and empty response are explicit errors.
The persisted summary records source message IDs, conversation revision,
version, status, timestamps, and generation metadata.

## Lifecycle

Archive is reversible through restore/resume. Delete removes the conversation
according to the current local policy and emits an event. Cancellation changes
the persisted message state and emits `generation.cancelled`; interruption of
an already-running provider is capability-dependent and not falsely advertised.

## Events

The domain emits conversation creation/update/lifecycle, participant changes,
turn and generation lifecycle, message status, attachment registration,
context preparation, summary, failure, and cancellation events with correlation
metadata where available.
