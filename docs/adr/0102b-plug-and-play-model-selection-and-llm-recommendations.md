# ADR 0102B: Plug-and-Play Model Selection and LLM Recommendations v1

Status: Accepted

## Context

Synapse already had a working local-chat path and a model catalog, but the UI and
runtime did not expose a clear, session-local way to choose a model for a
conversation. Users also had no actionable guidance about which local models fit
their machine, which models were too heavy, or which runtime should be used for a
given model.

## Decision

The Model Hub now acts as the local catalog and recommendation layer, not as an
executor.

`SystemInsightRuntime` collects hardware facts and feeds them to
`build_llm_recommendations(...)`, which produces heuristic suggestions for:

- general chat;
- programming;
- fast responses;
- higher quality;
- low-memory machines;
- CPU-only machines;
- GPU-recommended setups.

The backend surfaces these recommendations through `GET /system/insight` and
returns them to the frontend as part of `SystemInsightDTO`.

`ChatRuntime.local_chat()` now accepts optional `model_provider_id` and
`model_name` overrides. When the user chooses a model in the UI, the selected
provider/model is passed explicitly through the local-chat request and into the
agent runtime. This is session-local behavior; it does not rewrite the global
Model Hub defaults unless the user uses the Model Management screen to do so.

The Model Management UI shows:

- the current default model;
- recommended models for the detected machine;
- discovered local models;
- collapsed technical details for each model.

The Conversations UI shows the chosen model for the active session and forwards
the explicit provider/model selection to the backend before sending the turn.

## Compatibility

- Existing local chat remains usable when no explicit selection is made.
- LM Studio remains the default fallback for local chat when no better explicit
  selection exists.
- Model recommendations are advisory only; they do not auto-load or auto-run
  models.
- Existing provider configuration and existing catalog discovery remain intact.

## Consequences

Users can pick a model directly from chat without editing config files, and the
UI can explain why a model is recommended or discouraged for the current
machine. The selection is explicit in the request path instead of being inferred
from a hidden convention.

This does not add streaming, auto-download, automatic model switching, or any
new execution capability. It only makes model choice visible and explicit.
