# Synapse

Synapse is a local-first personal assistant prototype evolved from Artemis. It is designed to be light, modular and safe to publish: local memory, configurable LLM providers, a terminal-focused CLI, a desktop GUI and a multi-agent foundation.

The old `artemis/` prototype is preserved. New development lives in `synapse/`.

## Features

- LLM-agnostic providers: Ollama, LM Studio, vLLM/text-generation-webui, OpenAI-compatible endpoints, OpenAI, Groq and Gemini configuration.
- Provider fallback when the active provider fails.
- SQLite memory with session history, long memory and incremental summaries.
- Multi-agent manager with Artemis as the default agent.
- CLI for focus/coding mode.
- Tkinter desktop GUI with chat, agents, provider/model controls, memory panel, upload and basic logs.
- File analysis for `txt`, `md`, `json`, `csv`, `pdf`, `docx` and common code files.
- Security-first defaults: `.env.example`, `.gitignore`, masked logs, path validation, rate limits and no arbitrary command execution.
- STT driver scaffolding for future `faster-whisper` or Vosk support.

## Install

```powershell
cd E:\Projetos\AI-Companion
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

For local Ollama:

```powershell
ollama serve
ollama pull gemma4:e4b
```

## Run

```powershell
python run_cli.py
python run_gui.py
```

The CLI and GUI use the same Synapse core.

If Windows says `python` is not recognized, install Python 3.11+ from python.org or enable the Python launcher/path option, then reopen the terminal.

## Providers

On first run, Synapse creates `data/synapse_config.json`. Edit it to change providers without code changes.

Default local providers:

- `ollama`: `http://localhost:11434/v1`
- `lmstudio`: `http://localhost:1234/v1`

Cloud keys should live in `.env`, copied from `.env.example`, and never be committed.

Useful commands:

```text
/provider ollama
/provider lmstudio
/model llama3.1
/config
```

Any OpenAI-compatible endpoint can be added to `data/synapse_config.json` with:

```json
{
  "name": "my-endpoint",
  "type": "openai_compatible",
  "base_url": "http://localhost:8000/v1",
  "model": "my-model",
  "api_key_env": "MY_ENDPOINT_API_KEY",
  "enabled": true
}
```

## Agents

Artemis is the default agent. Agents can be created from CLI or GUI.

```text
/agent list
/agent new Reviewer "Revisa respostas e riscos"
/agent switch Reviewer
/agent delete Reviewer
```

Each agent has a name, description, system prompt, tool allowlist, optional provider/model and memory scope.

## Memory

Synapse stores memory in `data/synapse.db`:

- session history per run
- long memory summary
- profile/preferences placeholder
- automatic summary every configured number of turns

Commands:

```text
/memoria
/resumo
/esquecer
/reset
/history
```

## File Upload

Use the GUI upload button or CLI:

```text
/upload E:\Projetos\AI-Companion\README.md
Analise os riscos e sugira melhorias.
```

Supported formats include text, Markdown, JSON, CSV, PDF, DOCX and common source code files. File content is injected temporarily into the next prompt and constrained by size/context limits.

## Swarm Mode

The initial swarm foundation records a multi-agent plan and lets you switch agents for subtasks:

```text
/swarm Refatore o modulo de memoria e revise riscos
/agent switch Artemis
```

Future versions can expand this into autonomous subtask execution with stronger safety confirmations.

## Project Structure

```text
synapse/
  agents/
  cli/
  config/
  core/
  memory/
  providers/
  security/
  tools/
  ui/
  utils/
  voice/
run_cli.py
run_gui.py
SECURITY.md
requirements.txt
```

## Security Notes

- Do not commit `.env`, local DB files or logs.
- Avoid pasting secrets into chat.
- Synapse does not execute arbitrary shell commands.
- Tool execution should remain allowlisted and confirmation-based as automation grows.
