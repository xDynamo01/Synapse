# ADR 0079: LM Studio Provider Adapter

## Status

Accepted.

## Context

Synapse has provider contracts, plugin manifests, model routing, chat runtime, and mock model adapters. The next architectural risk is validating a real local model provider without coupling the core runtime to a specific LLM process.

LM Studio exposes a local OpenAI-compatible API when the user starts its server, normally at:

```text
http://127.0.0.1:1234/v1
```

## Decision

Add `LMStudioProviderRuntime` as an optional local model provider adapter.

Configuration lives in:

```text
DATA_DIR/config/lmstudio_provider.yaml
```

Default configuration is disabled:

```yaml
lmstudio:
  enabled: false
  base_url: "http://127.0.0.1:1234/v1"
  timeout_seconds: 30
  default_model: null
```

The runtime supports:

- `health()`
- `list_models()`
- `chat_completion()`
- `explain_status()`

The Provider Runtime registers:

```text
provider_id: lmstudio_local
provider_type: model
capabilities: local_llm, chat_completion
```

The Provider Plugin Runtime catalogs:

```text
plugin_id: lmstudio_plugin
plugin_type: model
providers: lmstudio_local
```

The Model Router can use the adapter when an agent/system model route uses `lmstudio` or `lmstudio_local`.

## Boundaries

This adapter does not:

- start LM Studio
- install LM Studio
- download models
- choose a model automatically when multiple are available
- implement streaming
- implement embeddings
- implement tool/function calling through LM Studio
- integrate OpenAI cloud or any other provider

Bootstrap must not fail if LM Studio is disabled or offline.

## Consequences

Synapse can validate a real local LLM path while keeping mocks and existing routes intact. Operational readiness treats LM Studio as optional unless the user enables it.
