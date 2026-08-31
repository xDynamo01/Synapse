# LM Studio Provider

Synapse can call a local LM Studio server through its OpenAI-compatible API.

Default endpoint:

```text
http://127.0.0.1:1234/v1
```

## Enable

Start LM Studio manually and enable the local server in LM Studio.

Then edit:

```text
DATA_DIR/config/lmstudio_provider.yaml
```

Example:

```yaml
lmstudio:
  enabled: true
  base_url: "http://127.0.0.1:1234/v1"
  timeout_seconds: 30
  default_model: "your-loaded-model-id"
  metadata: {}
```

Synapse does not choose between multiple loaded models automatically. Set `default_model` explicitly or pass a model in API calls.

When the user saves a local LM Studio model from the Modelos screen, Synapse also
syncs:

- `DATA_DIR/config/local_chat_policy.yaml` -> `local_chat.enabled = true` and `provider_id = lmstudio_local`
- `DATA_DIR/config/lmstudio_provider.yaml` -> `lmstudio.enabled = true` and `default_model = <selected model>`

That keeps the Local Chat screen and the Modelos screen on the same source of
truth.

## Commands

```text
/lmstudio-status
/lmstudio-models
/lmstudio-chat "hello"
```

## API

```text
GET /providers/lmstudio/status
GET /providers/lmstudio/models
POST /providers/lmstudio/chat
```

## Manual Local Chat Test

1. Open LM Studio.
2. Load a local chat model.
3. Start the LM Studio local server.
4. Edit `DATA_DIR/config/lmstudio_provider.yaml` or save a local model from the
   Modelos screen:

```yaml
lmstudio:
  enabled: true
  base_url: "http://127.0.0.1:1234/v1"
  timeout_seconds: 30
  default_model: "your-loaded-model-id"
  metadata: {}
```

5. Edit `DATA_DIR/config/local_chat_policy.yaml` if you want to override the
   Local Chat gate manually:

```yaml
local_chat:
  enabled: true
  provider_id: lmstudio_local
  require_explicit_provider: true
  persist_conversations: true
  max_context_messages: 10
  include_conversation_summary: true
  include_multimodal_context: false
```

6. Run the backend.
7. Check provider status:

```text
/lmstudio-status
```

8. Test the real local chat path:

```text
/local-chat "Hello from Synapse"
```

The command returns the model response and a `conversation_id`. Synapse persists the chat session under `chats/sessions/` and mirrors local-chat messages into `conversations/` when `persist_conversations` is enabled.

The Desktop UI Shell also exposes this path under the Conversations module. The UI does not stream responses and does not persist its own history; it only renders the current browser-session messages and reuses the backend `conversation_id`.

## Limits

This provider does not implement streaming, embeddings, function calling, model downloads, process management, or OpenAI cloud access.

If LM Studio is disabled, Synapse reports it as disabled and continues booting normally. If it is enabled but offline, health/readiness report a warning.
