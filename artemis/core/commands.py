# ============================================================
#  ARTEMIS — Módulo de Comandos
# ============================================================
"""
Processa comandos especiais que começam com '/'.
Retorna (handled: bool, response: str).
"""

from config.settings import COMMANDS
from core.memory import MemoryManager


class CommandHandler:
    def __init__(self, memory: MemoryManager, chat_engine):
        self.memory = memory
        self.chat   = chat_engine  # referência ao ChatEngine

    def handle(self, text: str) -> tuple[bool, str]:
        """
        Tenta processar o texto como um comando.
        Retorna (True, resposta) se for um comando, (False, '') caso contrário.
        """
        cmd = text.strip().lower()

        if cmd == "/reset":
            self.memory.reset_session()
            return True, "🔄 Histórico da sessão limpo. Contexto zerado!"

        elif cmd == "/memoria":
            mem = self.memory.long_summary
            return True, f"🧠 **Memória longa:**\n{mem}"

        elif cmd == "/salvar":
            path = self.memory.save_session()
            self.memory.save_long_memory()
            return True, f"💾 Sessão salva em: `{path}`"

        elif cmd == "/esquecer":
            self.memory.forget()
            return True, "🗑️ Memória longa apagada. Começando do zero."

        elif cmd == "/resumo":
            summary = self.chat.manual_summarize()
            return True, f"📝 **Resumo gerado e salvo:**\n{summary}"

        elif cmd == "/modo foco":
            active = self.memory.toggle_focus_mode()
            status = "✅ ATIVADO" if active else "⛔ DESATIVADO"
            return True, f"🎯 Modo Foco {status} — respostas serão {'ultra-curtas' if active else 'normais'}."

        elif cmd == "/ajuda":
            lines = ["📋 **Comandos disponíveis:**\n"]
            for c, desc in COMMANDS.items():
                lines.append(f"  `{c}` — {desc}")
            return True, "\n".join(lines)

        elif cmd.startswith("/perfil "):
            profile_text = text[len("/perfil "):].strip()
            self.memory._long_memory["user_profile"] = profile_text
            self.memory.save_long_memory()
            return True, f"👤 Perfil atualizado: {profile_text}"

        elif cmd.startswith("/nome "):
            name = text[len("/nome "):].strip()
            self.memory._long_memory["user_name"] = name
            self.memory.save_long_memory()
            return True, f"✅ Nome definido como: **{name}**"

        elif cmd == "/stats":
            s = self.memory.stats()
            lines = ["📊 **Estatísticas:**"]
            for k, v in s.items():
                lines.append(f"  {k}: {v}")
            return True, "\n".join(lines)

        elif cmd.startswith("/"):
            return True, f"❓ Comando desconhecido: `{cmd}`. Use `/ajuda` para ver os disponíveis."

        return False, ""
