# Models And Providers

Models + Providers is the provider-neutral generation infrastructure for Synapse.
It discovers configured providers and models, resolves explicit selection policy,
executes generation/streaming, records truthful usage, and reports structured
health and errors.

The system is local-first. LM Studio and Ollama are first-class local providers;
OpenAI-compatible endpoints may be local or explicitly configured remote services.
No cloud dependency or silent provider fallback exists.

See [Models And Routing](backend/models.md) and
[Model Providers](backend/providers.md) for normative details.
