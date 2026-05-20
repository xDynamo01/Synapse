from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from synapse.core import SynapseApp


class SynapseGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.app = SynapseApp()
        self.stream_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.streaming = False
        self.title("Synapse")
        self.geometry("1180x720")
        self.minsize(920, 560)
        self.configure(bg="#080a0f")
        self._style()
        self._build()
        self._refresh_agents()
        self._refresh_memory()
        self.after(40, self._poll_stream)

    def _style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#080a0f")
        style.configure("Panel.TFrame", background="#10131a")
        style.configure("TLabel", background="#10131a", foreground="#d8dee9")
        style.configure("TButton", background="#151a24", foreground="#d8dee9", borderwidth=1)
        style.configure("TEntry", fieldbackground="#090c12", foreground="#d8dee9")
        style.configure("TCombobox", fieldbackground="#090c12", foreground="#d8dee9")

    def _build(self) -> None:
        root = ttk.Frame(self, style="TFrame")
        root.pack(fill="both", expand=True)

        left = ttk.Frame(root, style="Panel.TFrame", width=260)
        left.pack(side="left", fill="y", padx=(10, 6), pady=10)
        left.pack_propagate(False)
        ttk.Label(left, text="Synapse", font=("Consolas", 18, "bold")).pack(anchor="w", padx=12, pady=(12, 2))
        self.status = ttk.Label(left, text="local-first | modular | swarm")
        self.status.pack(anchor="w", padx=12, pady=(0, 14))

        ttk.Label(left, text="Agentes").pack(anchor="w", padx=12)
        self.agent_list = tk.Listbox(left, bg="#090c12", fg="#d8dee9", selectbackground="#263247", borderwidth=0, height=8)
        self.agent_list.pack(fill="x", padx=12, pady=6)
        self.agent_list.bind("<<ListboxSelect>>", self._switch_selected_agent)
        row = ttk.Frame(left, style="Panel.TFrame")
        row.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(row, text="Novo", command=self._new_agent).pack(side="left", expand=True, fill="x")
        ttk.Button(row, text="Remover", command=self._delete_agent).pack(side="left", expand=True, fill="x", padx=(6, 0))

        ttk.Label(left, text="Provider").pack(anchor="w", padx=12)
        self.provider_var = tk.StringVar(value=self.app.config.active_provider)
        self.provider_combo = ttk.Combobox(left, textvariable=self.provider_var, values=list(self.app.config.providers.keys()), state="readonly")
        self.provider_combo.pack(fill="x", padx=12, pady=4)
        self.provider_combo.bind("<<ComboboxSelected>>", self._set_provider)
        ttk.Label(left, text="Modelo").pack(anchor="w", padx=12, pady=(8, 0))
        self.model_var = tk.StringVar(value=self.app.config.active_model)
        self.model_entry = ttk.Entry(left, textvariable=self.model_var)
        self.model_entry.pack(fill="x", padx=12, pady=4)
        ttk.Button(left, text="Aplicar modelo", command=self._set_model).pack(fill="x", padx=12, pady=(2, 14))

        ttk.Label(left, text="Memoria").pack(anchor="w", padx=12)
        ttk.Button(left, text="Resumir", command=lambda: self._send_text("/resumo")).pack(fill="x", padx=12, pady=2)
        ttk.Button(left, text="Esquecer", command=self._forget_memory).pack(fill="x", padx=12, pady=2)
        ttk.Button(left, text="Upload/analise", command=self._upload_file).pack(fill="x", padx=12, pady=(12, 2))

        center = ttk.Frame(root, style="TFrame")
        center.pack(side="left", fill="both", expand=True, padx=6, pady=10)
        self.chat = tk.Text(center, bg="#05070b", fg="#d8dee9", insertbackground="#d8dee9", wrap="word", borderwidth=0, font=("Consolas", 11))
        self.chat.pack(fill="both", expand=True)
        self.chat.tag_config("user", foreground="#78a6ff")
        self.chat.tag_config("bot", foreground="#38d9a9")
        self.chat.tag_config("sys", foreground="#f87171")
        input_row = ttk.Frame(center, style="TFrame")
        input_row.pack(fill="x", pady=(8, 0))
        self.input = tk.Text(input_row, height=3, bg="#090c12", fg="#d8dee9", insertbackground="#d8dee9", borderwidth=0, font=("Consolas", 11))
        self.input.pack(side="left", fill="x", expand=True)
        self.input.bind("<Return>", self._enter_send)
        ttk.Button(input_row, text="Enviar", command=self._send_current).pack(side="left", fill="y", padx=(8, 0))

        right = ttk.Frame(root, style="Panel.TFrame", width=280)
        right.pack(side="left", fill="y", padx=(6, 10), pady=10)
        right.pack_propagate(False)
        ttk.Label(right, text="Memoria longa", font=("Consolas", 12, "bold")).pack(anchor="w", padx=12, pady=(12, 6))
        self.memory_text = tk.Text(right, bg="#090c12", fg="#d8dee9", wrap="word", borderwidth=0, height=16, font=("Consolas", 10))
        self.memory_text.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        ttk.Label(right, text="Logs basicos", font=("Consolas", 12, "bold")).pack(anchor="w", padx=12)
        self.logs = tk.Text(right, bg="#090c12", fg="#8fbcbb", wrap="word", borderwidth=0, height=9, font=("Consolas", 9))
        self.logs.pack(fill="x", padx=12, pady=(6, 12))

        self._append("Sistema", "Synapse pronto. Use /help para comandos.\n", "sys")

    def _append(self, speaker: str, text: str, tag: str) -> None:
        self.chat.insert("end", f"{speaker}> ", tag)
        self.chat.insert("end", text)
        self.chat.see("end")

    def _log(self, text: str) -> None:
        self.logs.insert("end", text + "\n")
        self.logs.see("end")

    def _enter_send(self, event):
        if not event.state & 0x0001:
            self._send_current()
            return "break"
        return None

    def _send_current(self) -> None:
        text = self.input.get("1.0", "end").strip()
        self.input.delete("1.0", "end")
        self._send_text(text)

    def _send_text(self, text: str) -> None:
        if not text or self.streaming:
            return
        self.streaming = True
        self._append("Voce", text + "\n", "user")
        self._append(self.app.agents.active().name, "", "bot")

        def worker():
            try:
                for token in self.app.stream(text):
                    self.stream_queue.put(("token", token))
            finally:
                self.stream_queue.put(("done", ""))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_stream(self) -> None:
        try:
            while True:
                kind, data = self.stream_queue.get_nowait()
                if kind == "token":
                    self.chat.insert("end", data)
                    self.chat.see("end")
                if kind == "done":
                    self.chat.insert("end", "\n\n")
                    self.streaming = False
                    self._refresh_memory()
                    self._log("resposta concluida")
        except queue.Empty:
            pass
        self.after(40, self._poll_stream)

    def _refresh_agents(self) -> None:
        self.agent_list.delete(0, "end")
        for agent in self.app.agents.list_agents():
            prefix = "* " if agent.name == self.app.agents.active_name else "  "
            self.agent_list.insert("end", prefix + agent.name)

    def _switch_selected_agent(self, _event=None) -> None:
        selection = self.agent_list.curselection()
        if not selection:
            return
        name = self.agent_list.get(selection[0]).replace("*", "").strip()
        self.app.agents.switch(name)
        self._refresh_agents()
        self._log(f"agente ativo: {name}")

    def _new_agent(self) -> None:
        name = simpledialog.askstring("Novo agente", "Nome do agente:")
        if name:
            desc = simpledialog.askstring("Novo agente", "Descricao curta:") or ""
            self.app.agents.create(name, desc)
            self._refresh_agents()

    def _delete_agent(self) -> None:
        selection = self.agent_list.curselection()
        if not selection:
            return
        name = self.agent_list.get(selection[0]).replace("*", "").strip()
        try:
            self.app.agents.delete(name)
            self._refresh_agents()
        except Exception as exc:
            messagebox.showerror("Synapse", str(exc))

    def _set_provider(self, _event=None) -> None:
        self._send_text(f"/provider {self.provider_var.get()}")

    def _set_model(self) -> None:
        self._send_text(f"/model {self.model_var.get()}")

    def _refresh_memory(self) -> None:
        mem = self.app.memory.get_long_memory().get("summary") or "Memoria vazia."
        self.memory_text.delete("1.0", "end")
        self.memory_text.insert("end", mem)

    def _forget_memory(self) -> None:
        if messagebox.askyesno("Synapse", "Apagar memoria longa?"):
            self._send_text("/esquecer")

    def _upload_file(self) -> None:
        path = filedialog.askopenfilename(title="Anexar arquivo")
        if path:
            self._send_text(f"/upload {path}")


def main() -> None:
    app = SynapseGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
