# Model Providers

## Transversal projection

Model provider settings project to the canonical discovery IDs `lmstudio_local`,
`ollama_local`, `openai`, `anthropic`, `google_gemini`, `groq`, `openrouter` and
`openai_compatible`. Existing Model Router/Model Hub execution IDs remain unchanged
and are documented as compatibility aliases. The catalog neither applies settings
nor loads models.

Status: **Implemented / Frozen**.

`BaseModelAdapter` is the canonical provider port: model listing, health through
the provider surfaces, model validation through Model Hub, generation, streaming,
cancellation and capabilities. Product runtimes depend on ModelRouter, not HTTP.

## Supported Providers

- **LM Studio**: configurable local OpenAI-compatible endpoint, model listing,
  health, generation, SSE streaming, timeout, usage and structured errors.
- **Ollama**: configurable endpoint, tags listing, generation, JSONL streaming,
  usage and truthful capability reporting. Models are never pulled automatically.
- **OpenAI-compatible**: optional API key, allowed custom headers, models endpoint,
  chat completions, SSE, tools, structured output, timeout and normalized errors.
- **Mock**: deterministic explicit test/dev configuration only; never fallback by
  environment or runtime mode.

Retries are not duplicated: adapters issue one transport request. LM Studio retains
one bounded context-reduction retry for timeout compatibility; no validation,
authentication or malformed-response error is retried.

Provider keys and headers are accepted only from settings, omitted from responses
and events, and never copied into model metadata. Existing secret storage and
clear-key behavior remain owned by ProviderSettings.

Model Hub keys entries by `(provider_id, model_id)`, persists catalog snapshots,
keeps providers with the same model name distinct, uses configured endpoints, and
scans only explicit model folders and known extensions.
