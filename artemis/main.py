#!/usr/bin/env python3
# ============================================================
#  ARTEMIS — Ponto de Entrada Principal (CLI)
# ============================================================
"""
Assistente pessoal local com Ollama + Gemma4.
Execute: python main.py

Comandos disponíveis: /ajuda
"""

import sys
import os

# Garante que os imports relativos funcionem
sys.path.insert(0, os.path.dirname(__file__))

from core.memory   import MemoryManager
from core.chat     import ChatEngine
from core.commands import CommandHandler
from config.settings import OLLAMA_MODEL, OLLAMA_BASE_URL


# ─────────────────────────────────────────────────────────────
#  Banner
# ─────────────────────────────────────────────────────────────

BANNER = """
╔══════════════════════════════════════════════════════╗
║          ARTEMIS  —  AI Co-Pilot Local               ║
║          Modelo: {model:<38}║
║          Servidor: {url:<36}║
╚══════════════════════════════════════════════════════╝
  Digite /ajuda para ver os comandos disponíveis.
  Digite 'sair' ou Ctrl+C para encerrar.
"""


def print_banner():
    print(BANNER.format(model=OLLAMA_MODEL, url=OLLAMA_BASE_URL))


# ─────────────────────────────────────────────────────────────
#  Setup inicial
# ─────────────────────────────────────────────────────────────

def setup() -> tuple[MemoryManager, ChatEngine, CommandHandler]:
    memory  = MemoryManager()
    chat    = ChatEngine(memory)
    handler = CommandHandler(memory, chat)

    # Carrega última sessão automaticamente
    if memory.load_last_session():
        print(f"  ✅ Sessão anterior carregada ({memory.stats()['turns_in_session']} turnos).\n")
    else:
        print("  ℹ️  Nenhuma sessão anterior. Começando do zero.\n")

    return memory, chat, handler


# ─────────────────────────────────────────────────────────────
#  Loop principal
# ─────────────────────────────────────────────────────────────

def main():
    print_banner()

    # Verifica conexão com Ollama
    if not ChatEngine.health_check():
        print("  ❌ ERRO: Ollama não está respondendo em", OLLAMA_BASE_URL)
        print("  Execute: ollama serve\n")
        sys.exit(1)

    print(f"  ✅ Ollama conectado. Modelo: {OLLAMA_MODEL}\n")

    memory, chat, handler = setup()

    try:
        while True:
            # Prompt colorido no terminal
            try:
                user_input = input("\033[96mVocê:\033[0m ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not user_input:
                continue

            if user_input.lower() in ("sair", "exit", "quit"):
                break

            # Tenta processar como comando
            handled, response = handler.handle(user_input)
            if handled:
                print(f"\033[93mArtemis:\033[0m {response}\n")
                continue

            # Envia ao modelo com streaming
            print("\033[93mArtemis:\033[0m ", end="", flush=True)
            
            try:
                for token in chat.send_stream(user_input):
                    # Se o token indicar um erro conhecido do chat.py, quebra a linha antes de exibir
                    if token.startswith("❌") or token.startswith("⏱️"):
                        print(f"\n{token}", end="", flush=True)
                    else:
                        print(token, end="", flush=True)
                print("\n")
            except Exception as stream_err:
                print(f"\n❌ Erro crítico no fluxo de resposta: {stream_err}\n")

    except KeyboardInterrupt:
        pass
    finally:
        # Salva sessão de forma segura se o setup inicial foi concluído
        try:
            path = memory.save_session()
            memory.save_long_memory()
            print(f"\n\033[90m  💾 Sessão salva em {path}. Até logo!\033[0m\n")
        except NameError:
            # Captura o erro caso o script feche antes de instanciar a classe de memória
            print(f"\n\033[90m  Saindo do Artemis. Até logo!\033[0m\n")


if __name__ == "__main__":
    main()
