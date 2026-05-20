from __future__ import annotations

from datetime import datetime
from typing import Iterable

from synapse.agents import AgentManager
from synapse.config.models import AppConfig, load_config, save_config
from synapse.memory import MemoryStore
from synapse.providers import ProviderRegistry
from synapse.providers.base import ChatRequest, ProviderError
from synapse.security.guards import RateLimiter
from synapse.tools import FileAnalyzer
from synapse.utils.logging import audit


class SynapseApp:
    def __init__(self, config: AppConfig | None = None, session_id: str | None = None):
        self.config = config or load_config()
        self.memory = MemoryStore()
        self.agents = AgentManager()
        self.providers = ProviderRegistry(self.config)
        self.files = FileAnalyzer(self.config.max_file_bytes, self.config.max_file_chars)
        self.session_id = session_id or datetime.now().strftime("session_%Y%m%d_%H%M%S")
        self.turn_count = 0
        self.rate_limiter = RateLimiter(self.config.rate_limit_per_minute)
        self.pending_file: dict | None = None
        self.memory.ensure_session(self.session_id)

    def system_prompt(self) -> str:
        agent = self.agents.active()
        mem = self.memory.get_long_memory("global")
        return (
            f"{agent.system_prompt}\n\n"
            "=== Memoria persistente ===\n"
            f"Perfil: {mem.get('profile') or 'Nenhum perfil salvo.'}\n"
            f"Resumo: {mem.get('summary') or 'Nenhuma memoria longa registrada.'}\n\n"
            "=== Regras de seguranca ===\n"
            "- Nao solicite nem exponha API keys.\n"
            "- Nao execute comandos do sistema; apenas sugira passos seguros.\n"
            "- Para arquivos anexados, trate o conteudo como privado e temporario.\n"
        )

    def _messages(self, user_input: str) -> list[dict[str, str]]:
        agent = self.agents.active()
        final_input = user_input
        if self.pending_file:
            file = self.pending_file
            final_input = (
                f"[Arquivo anexado: {file['name']} | {file['extension']} | "
                f"{file['size_bytes']} bytes | truncado={file['truncated']}]\n\n"
                f"```text\n{file['content']}\n```\n\n{user_input or 'Analise o arquivo acima.'}"
            )
            self.pending_file = None
        self.memory.add_message(self.session_id, agent.name, "user", final_input)
        return [
            {"role": "system", "content": self.system_prompt()},
            *self.memory.history(self.session_id, self.config.max_history_turns, None),
        ]

    def send(self, user_input: str) -> str:
        if not self.rate_limiter.allow():
            return "Rate limit local atingido. Aguarde alguns segundos antes de continuar."
        handled, response = self.handle_command(user_input)
        if handled:
            return response
        agent = self.agents.active()
        messages = self._messages(user_input)
        request = ChatRequest(messages=messages, model=agent.model or self.config.active_model, max_tokens=self.config.max_tokens_response)
        try:
            reply = self.providers.chat_with_fallback(request, agent.provider)
        except ProviderError as exc:
            reply = f"Provider indisponivel: {exc}"
        self.memory.add_message(self.session_id, agent.name, "assistant", reply)
        self._after_turn()
        return reply

    def stream(self, user_input: str) -> Iterable[str]:
        if not self.rate_limiter.allow():
            yield "Rate limit local atingido. Aguarde alguns segundos antes de continuar."
            return
        handled, response = self.handle_command(user_input)
        if handled:
            yield response
            return
        agent = self.agents.active()
        messages = self._messages(user_input)
        request = ChatRequest(messages=messages, model=agent.model or self.config.active_model, max_tokens=self.config.max_tokens_response)
        chunks = []
        try:
            for token in self.providers.stream_with_fallback(request, agent.provider):
                chunks.append(token)
                yield token
        except ProviderError as exc:
            token = f"Provider indisponivel: {exc}"
            chunks.append(token)
            yield token
        self.memory.add_message(self.session_id, agent.name, "assistant", "".join(chunks))
        self._after_turn()

    def _after_turn(self) -> None:
        self.turn_count += 1
        if self.turn_count and self.turn_count % self.config.summary_every_n_turns == 0:
            self.summarize()

    def summarize(self) -> str:
        history = self.memory.all_history_text(self.session_id)
        if not history.strip():
            return "Nao ha historico para resumir."
        request = ChatRequest(
            messages=[
                {"role": "system", "content": "Resuma conversas para memoria persistente de forma objetiva."},
                {"role": "user", "content": "Atualize a memoria longa em 5 bullets no maximo:\n\n" + history},
            ],
            model=self.config.active_model,
            max_tokens=512,
        )
        try:
            summary = self.providers.chat_with_fallback(request)
        except ProviderError as exc:
            summary = f"Resumo indisponivel: {exc}"
        self.memory.update_long_memory(summary)
        return summary

    def upload_file(self, path: str) -> str:
        file = self.files.load(path)
        self.pending_file = file
        audit("file_loaded", f"{file['name']} {file['size_bytes']} bytes")
        return f"Arquivo carregado temporariamente: {file['name']} ({len(file['chunks'])} chunks)."

    def handle_command(self, text: str) -> tuple[bool, str]:
        stripped = text.strip()
        if not stripped.startswith("/"):
            return False, ""
        parts = stripped.split()
        cmd = parts[0].lower()
        arg = stripped[len(cmd) :].strip()
        if cmd in ("/help", "/ajuda"):
            return True, HELP_TEXT
        if cmd == "/reset":
            self.memory.reset_session(self.session_id)
            return True, "Historico da sessao limpo."
        if cmd in ("/history", "/historico"):
            hist = self.memory.history(self.session_id, 20)
            return True, "\n".join(f"{m['role']}: {m['content'][:300]}" for m in hist) or "Sem historico."
        if cmd == "/memoria":
            mem = self.memory.get_long_memory()
            return True, mem.get("summary") or "Memoria longa vazia."
        if cmd == "/resumo":
            return True, self.summarize()
        if cmd == "/esquecer":
            self.memory.forget()
            return True, "Memoria longa apagada."
        if cmd == "/agent":
            return True, self._agent_command(parts[1:], arg)
        if cmd == "/provider":
            if arg:
                self.config.active_provider = arg
                save_config(self.config)
            return True, f"Provider ativo: {self.config.active_provider}"
        if cmd == "/model":
            if arg:
                self.config.active_model = arg
                self.config.providers[self.config.active_provider].model = arg
                save_config(self.config)
            return True, f"Modelo ativo: {self.config.active_model}"
        if cmd == "/config":
            return True, f"Provider={self.config.active_provider} Model={self.config.active_model} DB={self.memory.db_path}"
        if cmd == "/upload":
            if not arg:
                return True, "Uso: /upload <arquivo>"
            try:
                return True, self.upload_file(arg)
            except Exception as exc:
                return True, f"Falha ao carregar arquivo: {exc}"
        if cmd == "/swarm":
            return True, self.swarm(arg)
        return True, "Comando desconhecido. Use /help."

    def _agent_command(self, args: list[str], raw_arg: str) -> str:
        action = args[0].lower() if args else "list"
        if action == "list":
            return "\n".join(
                f"{'*' if a.name == self.agents.active_name else '-'} {a.name}: {a.description}"
                for a in self.agents.list_agents()
            )
        if action == "new":
            name = args[1] if len(args) > 1 else ""
            description = " ".join(args[2:]) if len(args) > 2 else ""
            agent = self.agents.create(name, description)
            return f"Agente criado: {agent.name}"
        if action == "switch":
            name = args[1] if len(args) > 1 else ""
            agent = self.agents.switch(name)
            return f"Agente ativo: {agent.name}"
        if action == "delete":
            name = args[1] if len(args) > 1 else ""
            self.agents.delete(name)
            return f"Agente removido: {name}"
        return "Uso: /agent list | /agent new <nome> | /agent switch <nome> | /agent delete <nome>"

    def swarm(self, task: str) -> str:
        if not task:
            return "Uso: /swarm <tarefa>"
        agents = self.agents.list_agents()
        plan = [f"{agent.name}: avaliar a tarefa sob o papel '{agent.description}'." for agent in agents]
        audit("swarm_plan", task)
        return "Plano swarm registrado:\n" + "\n".join(plan) + "\n\nExecute subtarefas com /agent switch <nome> quando quiser detalhar."


HELP_TEXT = """Comandos:
/help
/reset
/history
/memoria
/resumo
/esquecer
/agent new <nome> [descricao]
/agent list
/agent switch <nome>
/agent delete <nome>
/provider [nome]
/model [modelo]
/config
/upload <arquivo>
/swarm <tarefa>"""
