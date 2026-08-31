# Models And Routing

Model Hub receives the neutral provider catalog for discovery-only manifest views.
Generation, streaming, cancellation, model refresh, routing and fallback continue
through `ModelRouter`, model adapters and `ModelHubRegistry`; none is delegated to
the transversal catalog.

Status: **Implemented / Frozen**.

## Contracts

`ModelDescriptor`, `ProviderDescriptor`, `ModelSelection`, `ModelRequest`,
`ModelResponse`, `ModelUsage`, and `GenerationChunk` are provider-neutral.
Capabilities use stable IDs: text generation, streaming, tool calling,
structured output, embeddings, vision, audio input, and long context.

`ModelRouter` is the only product generation entry. Selection order is explicit
turn override, conversation override, agent preference, global default, then an
optional configured fallback. Missing providers/models raise structured errors.
Development/test mode never changes selection to mock; mock must be configured.

## Usage And Events

Providers return token usage only when supplied by the endpoint. Unknown values
remain null; no local monetary cost is invented. Router events contain provider,
model, latency, usage, finish reason, actor and correlation metadata, never prompt
content or credentials.

Cancellation is capability-dependent. Ollama, LM Studio and the generic
OpenAI-compatible protocol expose no portable cancellation endpoint and report
that limitation explicitly; closing the transport remains caller behavior.
