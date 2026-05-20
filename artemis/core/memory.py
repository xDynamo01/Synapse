# ============================================================
#  ARTEMIS — Módulo de Memória Persistente
# ============================================================
"""
Gerencia dois níveis de memória:
  1. Sessão atual   → lista de turnos em RAM (salva em JSON)
  2. Memória longa  → resumo compactado de sessões passadas
"""

import json
import os
from datetime import datetime
from pathlib import Path

from config.settings import MEMORY_FILE, SESSIONS_DIR, MAX_HISTORY_TURNS


# ─────────────────────────────────────────────────────────────
#  Helpers de I/O
# ─────────────────────────────────────────────────────────────

def _load_json(path: str, default):
    """Carrega um arquivo JSON ou retorna o default."""
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return default


def _save_json(path: str, data) -> None:
    """Salva dados em JSON de forma segura (atomic write)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


# ─────────────────────────────────────────────────────────────
#  MemoryManager
# ─────────────────────────────────────────────────────────────

class MemoryManager:
    """
    Controla histórico de sessão + memória longa persistente.
    """

    def __init__(self):
        Path(SESSIONS_DIR).mkdir(parents=True, exist_ok=True)
        self._history: list[dict] = []      # Histórico ativo (RAM)
        self._long_memory: dict  = self._load_long_memory()
        self._focus_mode: bool   = False

    # ── Memória longa ──────────────────────────────────────

    def _load_long_memory(self) -> dict:
        default = {
            "user_name": "Usuário",
            "user_profile": "Nenhuma informação ainda.",
            "summary": "Nenhuma sessão anterior registrada.",
            "last_updated": None,
        }
        return _load_json(MEMORY_FILE, default)

    def save_long_memory(self) -> None:
        self._long_memory["last_updated"] = datetime.now().isoformat()
        _save_json(MEMORY_FILE, self._long_memory)

    def update_summary(self, new_summary: str) -> None:
        self._long_memory["summary"] = new_summary
        self.save_long_memory()

    def forget(self) -> None:
        self._long_memory["summary"] = "Memória apagada pelo usuário."
        self._long_memory["user_profile"] = "Nenhuma informação ainda."
        self.save_long_memory()

    @property
    def user_name(self) -> str:
        return self._long_memory.get("user_name", "Usuário")

    @property
    def user_profile(self) -> str:
        return self._long_memory.get("user_profile", "")

    @property
    def long_summary(self) -> str:
        return self._long_memory.get("summary", "")

    # ── Histórico de sessão ────────────────────────────────

    def add_turn(self, role: str, content: str) -> None:
        self._history.append({"role": role, "content": content})

    def get_history(self) -> list[dict]:
        """Retorna apenas os últimos N turnos para não explodir o contexto."""
        return self._history[-MAX_HISTORY_TURNS:]

    def reset_session(self) -> None:
        self._history = []

    # ── Persistência de sessão ─────────────────────────────

    def save_session(self) -> str:
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(SESSIONS_DIR, f"session_{ts}.json")
        _save_json(path, {
            "timestamp": ts,
            "history":   self._history,
            "summary":   self._long_memory.get("summary", ""),
        })
        return path

    def load_last_session(self) -> bool:
        sessions = sorted(Path(SESSIONS_DIR).glob("session_*.json"), reverse=True)
        if not sessions:
            return False
        data = _load_json(str(sessions[0]), {})
        self._history = data.get("history", [])
        return True

    # ── Modo Foco ──────────────────────────────────────────

    def toggle_focus_mode(self) -> bool:
        self._focus_mode = not self._focus_mode
        return self._focus_mode

    @property
    def focus_mode(self) -> bool:
        return self._focus_mode

    # ── Estatísticas ───────────────────────────────────────

    def stats(self) -> dict:
        return {
            "turns_in_session": len(self._history),
            "sessions_stored":  len(list(Path(SESSIONS_DIR).glob("session_*.json"))),
            "memory_file":      MEMORY_FILE,
            "focus_mode":       self._focus_mode,
        }
