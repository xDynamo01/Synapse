# ============================================================
#  ARTEMIS — Módulo de Chat (Ollama API)
# ============================================================
"""
Comunicação com Ollama via endpoint OpenAI-compatible.
Suporta streaming, arquivos de texto/PDF e imagens (via visão do modelo).
"""

import os
import json
import requests
from typing import Generator

os.environ["no_proxy"] = "localhost,127.0.0.1"
os.environ["NO_PROXY"] = "localhost,127.0.0.1"

from config.settings import (
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    MAX_TOKENS_RESPONSE,
    SYSTEM_PROMPT_TEMPLATE,
    SUMMARY_EVERY_N,
)
from core.memory import MemoryManager


# ─────────────────────────────────────────────────────────────
#  ChatEngine
# ─────────────────────────────────────────────────────────────

class ChatEngine:

    def __init__(self, memory: MemoryManager):
        self.memory     = memory
        self.turn_count = 0

    # ── System prompt ─────────────────────────────────────

    def _build_system_prompt(self) -> str:
        focus_note = "\n⚠️ MODO FOCO ATIVO: responda em no máximo 2 frases." \
                     if self.memory.focus_mode else ""
        return SYSTEM_PROMPT_TEMPLATE.format(
            user_name    = self.memory.user_name,
            user_profile = self.memory.user_profile,
            long_memory  = self.memory.long_summary,
        ) + focus_note

    # ── Chamadas à API Ollama ─────────────────────────────

    def _call_ollama(self, messages: list) -> str:
        """Chamada simples (sem streaming)."""
        url  = f"{OLLAMA_BASE_URL}/v1/chat/completions"
        body = {
            "model":      OLLAMA_MODEL,
            "messages":   messages,
            "max_tokens": MAX_TOKENS_RESPONSE,
            "stream":     False,
            "options": {
                "num_predict": MAX_TOKENS_RESPONSE,
                "temperature": 0.7,
                "top_p":       0.9,
            },
        }
        try:
            resp = requests.post(url, json=body, timeout=None)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except requests.exceptions.ConnectionError:
            return "❌ Ollama não está rodando. Execute: `ollama serve`"
        except requests.exceptions.Timeout:
            return "⏱️ Timeout! Tente /reset para limpar o contexto."
        except Exception as e:
            return f"❌ Erro inesperado: {e}"

    def _call_ollama_stream(self, messages: list,
                             image_b64: str = "",
                             mime: str = "") -> Generator[str, None, None]:
        """
        Chamada com streaming via /api/chat.
        Se image_b64 for fornecido, injeta no último turno do usuário
        para uso com modelos de visão (ex: gemma4, llava, moondream).
        """
        url  = f"{OLLAMA_BASE_URL}/api/chat"

        # Copia as mensagens para não modificar o histórico original
        msgs = [dict(m) for m in messages]

        # Injeta imagem na última mensagem do usuário, se houver
        if image_b64 and msgs:
            for i in range(len(msgs) - 1, -1, -1):
                if msgs[i]["role"] == "user":
                    msgs[i]["images"] = [image_b64]
                    break

        body = {
            "model":    OLLAMA_MODEL,
            "messages": msgs,
            "stream":   True,
            "options": {
                "num_predict": MAX_TOKENS_RESPONSE,
                "temperature": 0.7,
            },
        }
        try:
            with requests.post(url, json=body, stream=True, timeout=None) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if line:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if chunk.get("done"):
                            break
        except requests.exceptions.ConnectionError:
            yield "❌ Ollama não está rodando. Execute: `ollama serve`"
        except Exception as e:
            yield f"❌ Erro: {e}"

    # ── Helpers de contexto de arquivo ───────────────────

    @staticmethod
    def _inject_file_into_message(user_message: str, file: dict) -> str:
        """
        Para arquivos de texto/PDF: envolve o conteúdo em bloco formatado
        e prepende à mensagem do usuário. O modelo vê arquivo + pergunta juntos.
        """
        if not file or not file.get("content"):
            return user_message

        ext     = file.get("ext", "")
        name    = file.get("name", "arquivo")
        content = file["content"]
        warn    = file.get("warning", "")

        # Tenta usar syntax highlight pelo tipo de arquivo
        lang_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".html": "html", ".css": "css", ".json": "json",
            ".sql": "sql", ".sh": "bash", ".bat": "batch",
            ".c": "c", ".cpp": "cpp", ".h": "c", ".java": "java",
            ".rs": "rust", ".go": "go", ".rb": "ruby", ".php": "php",
            ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
            ".xml": "xml", ".csv": "csv", ".md": "markdown",
        }
        lang = lang_map.get(ext, "")
        fence = f"```{lang}" if lang else "```"

        header = f"[Arquivo: {name}]"
        if warn:
            header += f"\n[Aviso: {warn}]"

        file_block = f"{header}\n{fence}\n{content}\n```"

        if user_message:
            return f"{file_block}\n\n{user_message}"
        else:
            return f"{file_block}\n\nAnalise o arquivo acima e forneça um resumo detalhado."

    # ── Envio padrão (sem arquivo) ────────────────────────

    def send(self, user_input: str) -> str:
        self.memory.add_turn("user", user_input)
        messages = [
            {"role": "system", "content": self._build_system_prompt()},
            *self.memory.get_history(),
        ]
        reply = self._call_ollama(messages)
        self.memory.add_turn("assistant", reply)
        self.turn_count += 1
        if self.turn_count % SUMMARY_EVERY_N == 0:
            self._auto_summarize()
        return reply

    def send_stream(self, user_input: str) -> Generator[str, None, None]:
        """Streaming sem arquivo (compatibilidade com main.py e server.py)."""
        yield from self.send_stream_with_file(user_input, None)

    # ── Envio com arquivo ─────────────────────────────────

    def send_stream_with_file(self, user_input: str,
                               file: dict = None) -> Generator[str, None, None]:
        """
        Versão principal com suporte a arquivos.

        Lógica por tipo:
          - text/pdf  → conteúdo injetado no texto da mensagem
          - image     → base64 enviado no campo 'images' do Ollama
          - None      → comportamento normal
        """
        image_b64 = ""
        mime      = ""

        if file and file.get("kind") == "image":
            # Imagem: monta mensagem normal, imagem vai separada via API
            image_b64 = file.get("image_b64", "")
            mime      = file.get("mime", "image/png")
            final_msg = user_input or "Descreva esta imagem detalhadamente."
        elif file and file.get("kind") in ("text", "pdf") and file.get("content"):
            # Texto/PDF: injeta conteúdo na mensagem
            final_msg = self._inject_file_into_message(user_input, file)
        else:
            final_msg = user_input

        self.memory.add_turn("user", final_msg)

        messages = [
            {"role": "system", "content": self._build_system_prompt()},
            *self.memory.get_history(),
        ]

        full_reply = []
        for token in self._call_ollama_stream(messages, image_b64=image_b64, mime=mime):
            full_reply.append(token)
            yield token

        reply = "".join(full_reply)
        self.memory.add_turn("assistant", reply)
        self.turn_count += 1
        if self.turn_count % SUMMARY_EVERY_N == 0:
            self._auto_summarize()

    # ── Resumo automático ─────────────────────────────────

    def _auto_summarize(self) -> None:
        history_text = "\n".join(
            f"{t['role'].upper()}: {t['content']}"
            for t in self.memory.get_history()
        )
        prompt = [{
            "role": "user",
            "content": (
                "Resuma em 3-5 frases os pontos mais importantes desta conversa "
                "para uso futuro como memória do assistente. Seja objetivo:\n\n"
                + history_text
            ),
        }]
        summary = self._call_ollama(prompt)
        self.memory.update_summary(summary)

    def manual_summarize(self) -> str:
        self._auto_summarize()
        return self.memory.long_summary

    # ── Health check ──────────────────────────────────────

    @staticmethod
    def health_check() -> bool:
        try:
            r = requests.get(f"{OLLAMA_BASE_URL}/", timeout=3)
            return r.status_code == 200
        except Exception:
            return False
