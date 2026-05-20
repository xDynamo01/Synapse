# Security Policy

Synapse is a local-first personal assistant. Treat all prompts, files, logs, memory and provider settings as private user data.

## Secrets

- Never commit `.env`, API keys, tokens or local database files.
- Use `.env.example` as a template only.
- Prefer environment variables such as `OPENAI_API_KEY`, `GROQ_API_KEY` and `GEMINI_API_KEY`.
- Logs are masked with basic token patterns, but do not paste secrets into chat.

## Local Safety

- Synapse does not execute arbitrary shell commands.
- Tool execution must be allowlisted before future automation features are enabled.
- Uploaded files are loaded temporarily into the active prompt and are not stored as raw content unless the user explicitly asks for persistence.
- File paths are resolved and validated before reading.

## Limits

- Local rate limiting reduces accidental model loops.
- File size and context limits are configured in `data/synapse_config.json`.
- Long memory is summarized into SQLite instead of sending unbounded history.

## Reporting

If you find a vulnerability before this project has a public issue tracker, report it privately to the project owner. Include reproduction steps and avoid sharing secrets or private files.
