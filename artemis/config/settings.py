# ============================================================
#  ARTEMIS — Configurações Globais
# ============================================================

from pathlib import Path

# Diretório raiz do projeto (onde este arquivo está)
# Isso garante que os caminhos funcionem independente de onde
# o Python foi chamado — ESSE era o bug da memória.
_ROOT = Path(__file__).parent.resolve()

# Alterado de 127.0.0.1 para localhost para garantir compatibilidade IPv4/IPv6 estável no Windows
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL    = "gemma4:e4b"          # Modelo principal leve

# ---------- Limites de contexto (evitar travamentos) ----------
MAX_HISTORY_TURNS   = 12    # Máx de turnos no contexto ativo
MAX_TOKENS_RESPONSE = 2048   # Máx tokens por resposta
SUMMARY_EVERY_N     = 8     # Resumir após N turnos

# ---------- Caminhos de dados (agora ABSOLUTOS) --------------
DATA_DIR             = str(_ROOT / "data")
SESSIONS_DIR         = str(_ROOT / "data" / "sessions")
MEMORY_FILE          = str(_ROOT / "data" / "memory.json")
CURRENT_SESSION_FILE = str(_ROOT / "data" / "current_session.json")

# ---------- System prompt base --------------------------------
SYSTEM_PROMPT_TEMPLATE = """\
Você é Artemis, um assistente pessoal local inteligente, direto e eficiente.
Você roda 100% localmente no PC de {user_name} e prioriza respostas curtas e precisas.

=== PERFIL DO USUÁRIO ===
{user_profile}

=== MEMÓRIA LONGA (resumo de sessões anteriores) ===
{long_memory}

=== INSTRUÇÕES ===
- Seja conciso: prefira respostas curtas a longas divagações.
- Use português do Brasil naturalmente.
- Se não souber algo, diga claramente.
- Nunca invente fatos ou dados.
- Quando o usuário pedir código, entregue código limpo e funcional.
"""

# ---------- Comandos suportados --------------------------------
COMMANDS = {
    "/reset":     "Limpa o histórico da sessão atual.",
    "/memoria":   "Mostra a memória longa salva.",
    "/salvar":    "Força salvar a sessão atual.",
    "/esquecer":  "Apaga a memória longa.",
    "/resumo":    "Gera um resumo da conversa atual.",
    "/modo foco": "Ativa modo foco (respostas ultra-curtas).",
    "/ajuda":     "Lista todos os comandos disponíveis.",
}
