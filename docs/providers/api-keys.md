# Provider API Keys

Provider settings are available in **Configuracoes > Providers & API Keys** and through `/api/provider-settings`.

Non-secret settings are stored at `DATA_DIR/config/provider_settings.yaml`. In the Windows alpha, API keys are encrypted for the current OS user with Windows DPAPI and stored as protected blobs at `DATA_DIR/providers/credentials.yaml`. The API returns only a masked suffix; an empty key field preserves the existing key.

Supported IDs are `lmstudio_local`, `ollama_local`, `openai`, `anthropic`, `google_gemini`, `groq`, `openrouter`, and `openai_compatible`. Configuration support does not imply that a cloud chat adapter exists.

Connection tests issue a short read-only request to the configured model-list endpoint. They do not send prompts or start inference. Use dedicated, least-privilege credentials.

## Alpha limitations

- Secure persistence currently uses Windows DPAPI and is tied to the current Windows user.
- macOS Keychain and Linux Secret Service are not implemented.
- Credential export and recovery are intentionally unavailable.
- A cross-platform credential-vault interface remains the next security step.
