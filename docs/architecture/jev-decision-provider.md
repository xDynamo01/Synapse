# Jev decision provider

Jev is an optional decision provider for Synapse. It receives a state string and
a closed set of candidate IDs, then returns one typed choice with confidence and
probabilities. It does not generate commands, URLs, tool arguments or response
text. Command and tool runtimes remain the owners of validation, policy,
approval and execution.

## Configuration

Set `JEV_API_KEY` in an ignored local environment file to enable the provider.
`JEV_ENDPOINT` defaults to `https://api.typesafe.ai/v1/systemone` and `JEV_MODEL`
defaults to `jev-latest`. No key means the provider stays disabled and Synapse
continues with its existing deterministic routing.

## Safe use

Call `JevDecisionClient.choose()` only after the caller has built a bounded list
of candidates. The returned `candidate_id` must be resolved against that same
list before any action is attempted. Treat low confidence or a provider error as
a review/fallback path. Never pass raw Jev output directly to a shell, browser,
URL, tool registry or command executor.

The client uses TypeSafe's `POST /v1/systemone` choice contract and sends the API
key only in the `Authorization` header. It does not log the key or persist the
user's state. Jev's model is hosted; this provider is intentionally optional and
does not add a model download or a Python dependency.

Source contract: [TypeSafe API](https://api.typesafe.ai/redoc).
