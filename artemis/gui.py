#!/usr/bin/env python3
# ============================================================
#  ARTEMIS — Interface Gráfica Desktop (CustomTkinter)
# ============================================================
"""
Interface desktop nativa para o Artemis.
Execute: python gui.py

Requer: pip install customtkinter pypdf
"""

import sys
import os
import threading
import queue
import base64
import mimetypes
from pathlib import Path
from tkinter import filedialog

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import customtkinter as ctk
except ImportError:
    print("Instale o customtkinter: pip install customtkinter")
    sys.exit(1)

import tkinter as tk

from core.memory   import MemoryManager
from core.chat     import ChatEngine
from core.commands import CommandHandler
from config.settings import OLLAMA_MODEL


# ─────────────────────────────────────────────────────────────
#  Tipos de arquivo suportados
# ─────────────────────────────────────────────────────────────

TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".ts", ".jsx", ".tsx",
    ".html", ".css", ".json", ".csv", ".xml", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".sh", ".bat", ".c", ".cpp",
    ".h", ".java", ".rs", ".go", ".rb", ".php", ".sql",
    ".r", ".kt", ".swift", ".dart", ".lua", ".ps1", ".env",
    ".log", ".gitignore", ".dockerfile",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

MAX_TEXT_CHARS = 12_000   # limite para não explodir o contexto


# ─────────────────────────────────────────────────────────────
#  Paleta de cores
# ─────────────────────────────────────────────────────────────

COLORS = {
    "bg_dark":        "#0a0d14",
    "bg_panel":       "#0f1320",
    "bg_input":       "#141824",
    "accent":         "#00d4ff",
    "accent_dim":     "#005f7a",
    "accent2":        "#7c3aed",
    "accent2_dim":    "#3b1f6e",
    "text_primary":   "#e2e8f0",
    "text_secondary": "#64748b",
    "text_user":      "#93c5fd",
    "text_bot":       "#00d4ff",
    "text_success":   "#34d399",
    "text_error":     "#f87171",
    "text_warn":      "#fbbf24",
    "border":         "#1e2a3a",
    "scrollbar":      "#1e293b",
    "chip_bg":        "#1a1f35",
    "chip_border":    "#2d3a5a",
}

FONT_MONO  = ("Consolas", 11)
FONT_CHAT  = ("Consolas", 12)
FONT_TITLE = ("Consolas", 16, "bold")
FONT_LABEL = ("Consolas", 9)
FONT_BTN   = ("Consolas", 11, "bold")
FONT_INPUT = ("Consolas", 12)


# ─────────────────────────────────────────────────────────────
#  Leitura de arquivos
# ─────────────────────────────────────────────────────────────

def _read_text_file(path: Path) -> tuple:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return "", f"Erro ao ler arquivo: {e}"
    warn = ""
    if len(content) > MAX_TEXT_CHARS:
        content = content[:MAX_TEXT_CHARS]
        warn = f"[Arquivo truncado em {MAX_TEXT_CHARS} caracteres]"
    return content, warn


def _read_pdf(path: Path) -> tuple:
    try:
        import pypdf
    except ImportError:
        return "", "pypdf não instalado. Execute: pip install pypdf"
    try:
        reader = pypdf.PdfReader(str(path))
        pages  = [p.extract_text() or "" for p in reader.pages]
        text   = "\n\n".join(pages).strip()
        warn   = ""
        if len(text) > MAX_TEXT_CHARS:
            text = text[:MAX_TEXT_CHARS]
            warn = f"[PDF truncado em {MAX_TEXT_CHARS} caracteres]"
        if not text:
            warn = "Não foi possível extrair texto (PDF pode ser imagem/escaneado)."
        return text, warn
    except Exception as e:
        return "", f"Erro ao ler PDF: {e}"


def _read_image(path: Path) -> tuple:
    try:
        mime = mimetypes.guess_type(str(path))[0] or "image/png"
        data = base64.b64encode(path.read_bytes()).decode("utf-8")
        return data, mime
    except Exception as e:
        return "", str(e)


def _process_file(path_str: str) -> dict:
    path = Path(path_str)
    ext  = path.suffix.lower()
    result = {
        "name":      path.name,
        "kind":      "unknown",
        "content":   "",
        "image_b64": "",
        "mime":      "",
        "warning":   "",
        "ext":       ext,
        "size_kb":   round(path.stat().st_size / 1024, 1),
    }
    if ext in TEXT_EXTENSIONS:
        content, warn = _read_text_file(path)
        result["kind"]    = "text"
        result["content"] = content
        result["warning"] = warn
    elif ext == ".pdf":
        content, warn = _read_pdf(path)
        result["kind"]    = "pdf"
        result["content"] = content
        result["warning"] = warn
    elif ext in IMAGE_EXTENSIONS:
        b64, mime = _read_image(path)
        if b64:
            result["kind"]      = "image"
            result["image_b64"] = b64
            result["mime"]      = mime
        else:
            result["warning"] = mime
    else:
        result["warning"] = f"Tipo '{ext}' não suportado. Use texto, PDF ou imagem."
    return result


# ─────────────────────────────────────────────────────────────
#  Janela principal
# ─────────────────────────────────────────────────────────────

class ArtemisGUI(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("ARTEMIS — AI Co-Pilot Local")
        self.geometry("920x700")
        self.minsize(700, 500)
        self.configure(fg_color=COLORS["bg_dark"])

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.memory  = MemoryManager()
        self.chat    = ChatEngine(self.memory)
        self.handler = CommandHandler(self.memory, self.chat)
        self.memory.load_last_session()

        self._stream_queue: queue.Queue = queue.Queue()
        self._streaming = False
        self._attached  = None   # dict do arquivo atual ou None

        self._build_ui()
        self._check_ollama()
        self._poll_stream_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ─────────────────────────────────────────────────────────
    #  Layout
    # ─────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_chat_area()

    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(
            self, width=200, corner_radius=0,
            fg_color=COLORS["bg_panel"],
            border_width=1, border_color=COLORS["border"]
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(8, weight=1)
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)

        logo = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo.grid(row=0, column=0, padx=16, pady=(20, 8), sticky="ew")
        ctk.CTkLabel(logo, text="◈ ARTEMIS", font=FONT_TITLE,
                     text_color=COLORS["accent"]).pack(anchor="w")
        ctk.CTkLabel(logo, text="AI Co-Pilot Local", font=FONT_LABEL,
                     text_color=COLORS["text_secondary"]).pack(anchor="w")

        ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["border"]).grid(
            row=1, column=0, sticky="ew", padx=12, pady=8)

        self._status_dot = ctk.CTkLabel(
            sidebar, text="● VERIFICANDO",
            font=FONT_LABEL, text_color=COLORS["text_secondary"])
        self._status_dot.grid(row=2, column=0, padx=16, pady=(0, 4), sticky="w")
        ctk.CTkLabel(sidebar, text=f"Modelo: {OLLAMA_MODEL}",
                     font=FONT_LABEL, text_color=COLORS["text_secondary"]
                     ).grid(row=3, column=0, padx=16, pady=(0, 12), sticky="w")

        ctk.CTkFrame(sidebar, height=1, fg_color=COLORS["border"]).grid(
            row=4, column=0, sticky="ew", padx=12, pady=4)
        ctk.CTkLabel(sidebar, text="COMANDOS RÁPIDOS",
                     font=FONT_LABEL, text_color=COLORS["text_secondary"]
                     ).grid(row=5, column=0, padx=16, pady=(8, 4), sticky="w")

        btn_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        btn_frame.grid(row=6, column=0, padx=12, pady=4, sticky="ew")
        btn_frame.grid_columnconfigure(0, weight=1)
        for i, (label, cmd) in enumerate([
            ("⟳  /reset",     "/reset"),
            ("◎  /memoria",   "/memoria"),
            ("◈  /resumo",    "/resumo"),
            ("◉  /modo foco", "/modo foco"),
            ("✦  /esquecer",  "/esquecer"),
            ("◇  /stats",     "/stats"),
            ("?  /ajuda",     "/ajuda"),
        ]):
            ctk.CTkButton(
                btn_frame, text=label, anchor="w", font=FONT_MONO,
                fg_color="transparent", text_color=COLORS["text_primary"],
                hover_color=COLORS["bg_input"],
                border_width=1, border_color=COLORS["border"],
                corner_radius=4, height=30,
                command=lambda c=cmd: self._send_message(c)
            ).grid(row=i, column=0, sticky="ew", pady=2)

        sidebar.grid_rowconfigure(7, weight=1)
        ctk.CTkButton(
            sidebar, text="💾  Salvar Sessão", font=FONT_BTN,
            fg_color=COLORS["accent_dim"], hover_color=COLORS["accent2"],
            text_color=COLORS["accent"], corner_radius=6, height=36,
            command=lambda: self._send_message("/salvar")
        ).grid(row=8, column=0, padx=12, pady=(0, 16), sticky="sew")

    def _build_chat_area(self):
        chat_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=COLORS["bg_dark"])
        chat_frame.grid(row=0, column=1, sticky="nsew")
        chat_frame.grid_rowconfigure(0, weight=1)
        chat_frame.grid_columnconfigure(0, weight=1)

        # Caixa de mensagens
        txt_frame = ctk.CTkFrame(
            chat_frame, corner_radius=8,
            fg_color=COLORS["bg_panel"],
            border_width=1, border_color=COLORS["border"]
        )
        txt_frame.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="nsew")
        txt_frame.grid_rowconfigure(0, weight=1)
        txt_frame.grid_columnconfigure(0, weight=1)

        self._chat_text = tk.Text(
            txt_frame,
            bg=COLORS["bg_panel"], fg=COLORS["text_primary"],
            font=FONT_CHAT, wrap="word", state="disabled", relief="flat",
            padx=16, pady=12, cursor="arrow",
            selectbackground=COLORS["accent_dim"],
            selectforeground=COLORS["text_primary"],
            spacing3=4,
        )
        self._chat_text.grid(row=0, column=0, sticky="nsew")
        sb = ctk.CTkScrollbar(txt_frame, command=self._chat_text.yview,
                               fg_color=COLORS["bg_panel"],
                               button_color=COLORS["scrollbar"],
                               button_hover_color=COLORS["accent_dim"])
        sb.grid(row=0, column=1, sticky="ns")
        self._chat_text.configure(yscrollcommand=sb.set)

        # Tags
        self._chat_text.tag_configure("user_name",  foreground=COLORS["text_user"],     font=("Consolas", 11, "bold"))
        self._chat_text.tag_configure("user_msg",   foreground=COLORS["text_primary"],  font=FONT_CHAT)
        self._chat_text.tag_configure("bot_name",   foreground=COLORS["text_bot"],      font=("Consolas", 11, "bold"))
        self._chat_text.tag_configure("bot_msg",    foreground=COLORS["text_primary"],  font=FONT_CHAT)
        self._chat_text.tag_configure("cmd_name",   foreground=COLORS["accent2"],       font=("Consolas", 11, "bold"))
        self._chat_text.tag_configure("cmd_msg",    foreground="#c4b5fd",               font=FONT_CHAT)
        self._chat_text.tag_configure("success",    foreground=COLORS["text_success"],  font=FONT_CHAT)
        self._chat_text.tag_configure("error",      foreground=COLORS["text_error"],    font=FONT_CHAT)
        self._chat_text.tag_configure("warn",       foreground=COLORS["text_warn"],     font=FONT_CHAT)
        self._chat_text.tag_configure("dim",        foreground=COLORS["text_secondary"],font=FONT_LABEL)
        self._chat_text.tag_configure("file_chip",  foreground=COLORS["accent2"],       font=("Consolas", 10, "bold"))
        self._chat_text.tag_configure("img_chip",   foreground=COLORS["text_success"],  font=("Consolas", 10, "bold"))

        # Área de input
        input_outer = ctk.CTkFrame(
            chat_frame, corner_radius=8,
            fg_color=COLORS["bg_input"],
            border_width=1, border_color=COLORS["border"]
        )
        input_outer.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="ew")
        input_outer.grid_columnconfigure(1, weight=1)

        # Chip do arquivo (linha 0, oculto por padrão)
        self._chip_frame = ctk.CTkFrame(
            input_outer, fg_color=COLORS["chip_bg"],
            corner_radius=6, border_width=1, border_color=COLORS["chip_border"]
        )
        self._chip_label = ctk.CTkLabel(
            self._chip_frame, text="",
            font=("Consolas", 10), text_color=COLORS["accent2"], anchor="w"
        )
        self._chip_label.grid(row=0, column=0, padx=8, pady=4, sticky="ew")
        self._chip_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            self._chip_frame, text="✕", width=24, height=20,
            font=("Consolas", 10, "bold"),
            fg_color="transparent", hover_color=COLORS["bg_input"],
            text_color=COLORS["text_error"], corner_radius=4,
            command=self._clear_attachment
        ).grid(row=0, column=1, padx=(0, 4), pady=4)
        self._chip_frame.grid_remove()   # oculto até ter arquivo

        # Botão de anexo
        ctk.CTkButton(
            input_outer, text="📎",
            font=("Consolas", 16), width=44, height=44,
            corner_radius=8, fg_color="transparent",
            hover_color=COLORS["accent2_dim"],
            text_color=COLORS["text_secondary"],
            command=self._open_file_dialog
        ).grid(row=1, column=0, padx=(8, 2), pady=8)

        # Campo de texto
        self._input = ctk.CTkTextbox(
            input_outer, height=52, font=FONT_INPUT,
            fg_color="transparent", text_color=COLORS["text_primary"],
            border_width=0, wrap="word",
            scrollbar_button_color=COLORS["bg_input"],
        )
        self._input.grid(row=1, column=1, padx=4, pady=8, sticky="ew")
        self._input.bind("<Return>",       self._on_enter)
        self._input.bind("<Shift-Return>", lambda e: None)
        self._input.focus()

        # Botão enviar
        ctk.CTkButton(
            input_outer, text="▶",
            font=("Consolas", 16, "bold"),
            width=52, height=52, corner_radius=8,
            fg_color=COLORS["accent_dim"], hover_color=COLORS["accent2"],
            text_color=COLORS["accent"],
            command=self._on_send_click
        ).grid(row=1, column=2, padx=(2, 10), pady=8)

        ctk.CTkLabel(
            input_outer,
            text="Enter enviar  •  Shift+Enter nova linha  •  📎 para anexar arquivo",
            font=FONT_LABEL, text_color=COLORS["text_secondary"]
        ).grid(row=2, column=0, columnspan=3, pady=(0, 6))

        self._print_welcome()

    # ─────────────────────────────────────────────────────────
    #  Gerenciamento de anexo
    # ─────────────────────────────────────────────────────────

    def _open_file_dialog(self):
        path = filedialog.askopenfilename(
            title="Selecionar arquivo para análise",
            filetypes=[
                ("Todos suportados",
                 "*.txt *.md *.py *.js *.ts *.html *.css *.json *.csv "
                 "*.xml *.yaml *.yml *.toml *.ini *.sh *.c *.cpp *.h "
                 "*.java *.rs *.go *.rb *.php *.sql "
                 "*.pdf *.png *.jpg *.jpeg *.gif *.webp"),
                ("Texto / Código",
                 "*.txt *.md *.py *.js *.ts *.html *.css *.json *.csv "
                 "*.xml *.yaml *.yml *.toml *.ini *.sh *.c *.cpp *.h "
                 "*.java *.rs *.go *.rb *.php *.sql"),
                ("PDF",    "*.pdf"),
                ("Imagens","*.png *.jpg *.jpeg *.gif *.webp *.bmp"),
                ("Todos",  "*.*"),
            ]
        )
        if path:
            self._attach_file(path)

    def _attach_file(self, path: str):
        file = _process_file(path)
        if file["warning"] and not file["content"] and not file["image_b64"]:
            self._chat_append(f"  ⚠️ {file['warning']}", "warn")
            return
        self._attached = file
        icon = {"text": "◈ texto", "pdf": "⬡ pdf", "image": "◉ imagem"}.get(
            file["kind"], "◇")
        extra = f"  ⚠️ {file['warning']}" if file["warning"] else ""
        self._chip_label.configure(
            text=f"{icon}: {file['name']}  ({file['size_kb']} KB){extra}")
        self._chip_frame.grid(row=0, column=0, columnspan=3,
                              padx=10, pady=(8, 0), sticky="ew")

    def _clear_attachment(self):
        self._attached = None
        self._chip_frame.grid_remove()

    # ─────────────────────────────────────────────────────────
    #  Impressão no chat
    # ─────────────────────────────────────────────────────────

    def _chat_append(self, text: str, tag: str = "bot_msg", newline: bool = True):
        self._chat_text.configure(state="normal")
        self._chat_text.insert("end", text + ("\n" if newline else ""), tag)
        self._chat_text.configure(state="disabled")
        self._chat_text.see("end")

    def _print_welcome(self):
        turns = self.memory.stats()["turns_in_session"]
        self._chat_append("╔══════════════════════════════════════════╗", "dim")
        self._chat_append("║        ARTEMIS  —  AI Co-Pilot Local     ║", "dim")
        self._chat_append("╚══════════════════════════════════════════╝", "dim")
        self._chat_append("")
        if turns > 0:
            self._chat_append(
                f"  ✅ Sessão anterior carregada ({turns} turnos).", "success")
        else:
            self._chat_append("  ℹ  Nova sessão iniciada.", "dim")
        self._chat_append("")

    def _print_user(self, text: str, file=None):
        self._chat_append("┌─ Você ", "user_name", newline=False)
        self._chat_append("─" * 37, "dim")
        if file:
            icon = {"text": "◈ texto", "pdf": "⬡ pdf",
                    "image": "◉ imagem"}.get(file["kind"], "◇")
            tag  = "img_chip" if file["kind"] == "image" else "file_chip"
            self._chat_append(f"  [{icon}: {file['name']}]", tag)
        self._chat_append(f"  {text}\n", "user_msg")

    def _print_bot_header(self):
        self._chat_append("┌─ Artemis ", "bot_name", newline=False)
        self._chat_append("─" * 35, "dim")
        self._chat_append("  ", "bot_msg", newline=False)

    def _print_bot_token(self, token: str):
        self._chat_text.configure(state="normal")
        self._chat_text.insert("end", token, "bot_msg")
        self._chat_text.configure(state="disabled")
        self._chat_text.see("end")

    def _print_bot_end(self):
        self._chat_append("\n", "bot_msg")

    def _print_command_response(self, text: str):
        self._chat_append("┌─ Sistema ", "cmd_name", newline=False)
        self._chat_append("─" * 35, "dim")
        self._chat_append(f"  {text}\n", "cmd_msg")

    # ─────────────────────────────────────────────────────────
    #  Envio de mensagem
    # ─────────────────────────────────────────────────────────

    def _on_enter(self, event):
        self._on_send_click()
        return "break"

    def _on_send_click(self):
        if self._streaming:
            return
        text = self._input.get("1.0", "end").strip()
        if not text and not self._attached:
            return
        self._input.delete("1.0", "end")
        self._send_message(text)

    def _send_message(self, text: str):
        if self._streaming:
            return

        handled, response = self.handler.handle(text)
        if handled:
            self._print_user(text)
            self._print_command_response(response)
            return

        file = self._attached
        self._clear_attachment()

        if not text and file:
            text = "Analise este arquivo e me dê um resumo detalhado."

        self._streaming = True
        self._print_user(text, file)
        self._print_bot_header()

        def _worker():
            try:
                for token in self.chat.send_stream_with_file(text, file):
                    self._stream_queue.put(("token", token))
            except Exception as e:
                self._stream_queue.put(("token", f"\n❌ Erro: {e}"))
            finally:
                self._stream_queue.put(("done", None))

        threading.Thread(target=_worker, daemon=True).start()

    # ─────────────────────────────────────────────────────────
    #  Polling de streaming
    # ─────────────────────────────────────────────────────────

    def _poll_stream_queue(self):
        try:
            while True:
                kind, data = self._stream_queue.get_nowait()
                if kind == "token":
                    self._print_bot_token(data)
                elif kind == "done":
                    self._print_bot_end()
                    self._streaming = False
        except queue.Empty:
            pass
        self.after(30, self._poll_stream_queue)

    # ─────────────────────────────────────────────────────────
    #  Status Ollama
    # ─────────────────────────────────────────────────────────

    def _check_ollama(self):
        def _check():
            ok = ChatEngine.health_check()
            self.after(0, lambda: self._set_status(ok))
        threading.Thread(target=_check, daemon=True).start()

    def _set_status(self, ok: bool):
        if ok:
            self._status_dot.configure(text="● ONLINE",
                                       text_color=COLORS["text_success"])
        else:
            self._status_dot.configure(text="● OFFLINE",
                                       text_color=COLORS["text_error"])
            self._chat_append(
                "  ❌ Ollama offline. Execute: ollama serve\n", "error")

    # ─────────────────────────────────────────────────────────
    #  Fechar
    # ─────────────────────────────────────────────────────────

    def _on_close(self):
        try:
            path = self.memory.save_session()
            self.memory.save_long_memory()
            print(f"  💾 Sessão salva em {path}.")
        except Exception as e:
            print(f"  ⚠️ Erro ao salvar: {e}")
        self.destroy()


# ─────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = ArtemisGUI()
    app.mainloop()
