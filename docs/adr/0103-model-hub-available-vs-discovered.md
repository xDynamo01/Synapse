# 0103 — Model Hub: available vs discovered

Status: accepted

Context

The desktop app previously exposed one mixed catalog that combined:

- models confirmed as ready to use now;
- models found in local library scans but not currently usable in chat;
- defaults inherited from configuration snapshots.

This made the frontend responsible for interpreting availability, which led to contradictory UI states and chat flows that were blocked by stale policy/config.

Decision

The backend now exposes two distinct concepts:

- `GET /api/models/available` returns only models that are ready to use now. These are the models the chat picker should treat as directly selectable.
- `GET /api/models/discovered` returns library/discovery data separately for informational and management purposes.

The chat bootstrap writes the selected available model back into persisted defaults, and the backend synchronizes local chat policy from that selection so the user does not need to edit YAML manually.

Consequences

- The chat UI no longer needs to infer whether a model is usable.
- Discovery data can still be shown in management screens without being mixed into the quick-pick chat list.
- If a default model is unavailable, the UI can fall back to the first available model instead of surfacing a policy error.
