# ADR 0099: Model Hub Runtime v1

## Status

Accepted.

## Context

Model information was split between Model Router configuration, LM Studio,
provider manifests, provider plugins, and local model folders. The desktop
Models surface could not safely manage this state without reimplementing
backend discovery and availability rules.

## Decision

Add a local-first Model Hub that projects existing runtime state into a
normalized catalog. It owns only monitored-folder records, user defaults, and a
catalog snapshot under `DATA_DIR/model_hub/`. The snapshot provides a readable
fallback when a provider is unavailable; provider runtimes remain authoritative
for live state.

The Hub scans registered folders in place for GGUF, GGML, and Safetensors files.
It never copies, moves, downloads, loads, or executes models. Provider responses
exclude credentials. User defaults are deliberately not applied to Model Router
automatically in v1, avoiding an implicit execution-policy change.

Future clients consume only the Model Hub API for catalog, provider, folder,
refresh, connection-test, and default-selection operations. Desktop assets and
renderer metadata are outside this runtime.

## Consequences

- Clients have one stable operational model-management contract.
- Existing model/provider runtimes keep their current responsibilities.
- Folder removal removes only monitoring metadata, never model files.
- Catalog metadata is best effort where providers do not expose size, context,
  quantization, or hardware requirements.
- Applying Model Hub defaults to live chat routing remains an explicit future
  integration.
