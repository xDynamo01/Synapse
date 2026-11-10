# Real local inference diagnostic — 2026-11-10

Status: real model provider verified for a tiny request; existing backend
conversation path failed its live timeout. This is not whole-model or Core
operational acceptance and does not replace fixture regression results.

## Environment and ownership

Read-only inventory found no loaded models. LM Studio CLI commit43d4b26,
CPython3.14.3, Windows/MSVC Core. Installed local Qwen3.5 4B Q4_K_M was loaded
in CPU mode with1024-token context, one prediction slot,120-second TTL and the
isolated identifier `synapse-backend-validation`. No model files downloaded.
Estimated total memory3.52GiB; initial free memory about5.3GiB; after loading,
about2.8GiB remained. One model only. The model was explicitly unloaded after
the tests; final inventory showed no loaded models.

The copied Core binary snapshot SHA256 was
`3faf75aea490557eb041b989b096585a7c115026f1d5a4eccbaa384799b81788`.
The experiment ran while an unrelated tool-contract change was uncommitted;
this hash identifies the observed artifact, not a clean release acceptance.
Owned test state, exact receipts and scripts remain under ignored
`.superpowers/sdd/2026-11-09-integrated-backend/live-model/`.

## Observed results

| Path | Request/settings | Observed result |
|---|---|---|
| Actual Core CLI → supervised Python → local OpenAI-compatible endpoint | registered `lm_studio` model, saved-chat start and polling; default generation settings | `provider_timeout` after10.943s. Job failed, no assistant message accepted. |
| Direct local native `/api/v1/chat` diagnostic | reasoning off,16 output tokens,store false,no integrations | Real model returned `OK` in0.752s. This bypasses Core and is only provider diagnosis. |
| Direct local `/v1/chat/completions` diagnostic |16 tokens, `chat_template_kwargs.enable_thinking:false` | Setting did not disable reasoning in this local endpoint; content empty,16 generated tokens, finish reason length. |
| Direct local `/v1/chat/completions` diagnostic |16 tokens, `reasoning_effort:none` | Real model returned `OK`, finish reason stop,2 output tokens in0.335s. |

An initial helper request used the catalog-only provider label `loopback` and
was correctly refused before inference; it was corrected to the documented
product provider `lm_studio`. It is not counted as a model timeout.

## Required product correction

Expose bounded, validated model-specific generation settings instead of a
hardcoded1024-token output request and fixed10/15-second provider/supervisor
deadlines. Preserve endpoint/proxy/redirect isolation, digest-bound worker
contracts, responsive cancellation and no late success. A model's reasoning
configuration is not a global Responsive/Economical product mode. Add fixture
regression, then repeat real Core conversation and restart/history/cancel paths.
Do not silently inject a provider-specific workaround into every model.

The official [Qwen3.5 model card](https://huggingface.co/Qwen/Qwen3.5-4B)
describes API-controlled non-thinking behavior and does not support relying on
the old prompt soft switches. The [LM Studio chat endpoint documentation](https://lmstudio.ai/docs/developer/openai-compat/chat-completions)
defines the compatible chat API; the exact acceptance of `reasoning_effort:none`
above is locally observed behavior, not inferred compatibility for every model
or server version. The [native endpoint documentation](https://lmstudio.ai/docs/developer/rest/chat)
documents reasoning and store controls used in the isolated diagnostic.

Charter: SE-001, MM-001/002, PL-001/006 and QA-001–003. All prompts were synthetic
and local. No account, tool integration, external inference or personal project
data was supplied to the model. Automatic memory learning remains unimplemented.
