from __future__ import annotations

from synapse.core import SynapseApp


def main() -> None:
    app = SynapseApp()
    print("Synapse CLI - local-first assistant")
    print("Digite /help para comandos, /upload <arquivo> para anexar, sair para encerrar.")
    print(f"Agente ativo: {app.agents.active().name} | Provider: {app.config.active_provider} | Modelo: {app.config.active_model}\n")
    while True:
        try:
            user_input = input("voce> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input.lower() in {"sair", "exit", "quit"}:
            break
        print(f"{app.agents.active().name}> ", end="", flush=True)
        for token in app.stream(user_input):
            print(token, end="", flush=True)
        print("\n")


if __name__ == "__main__":
    main()
