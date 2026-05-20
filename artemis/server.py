#!/usr/bin/env python3
# ============================================================
#  ARTEMIS — Servidor Web Local (FastAPI)
# ============================================================
"""
Expõe a lógica do Artemis via HTTP para a interface web (ui/artemis.html).
Execute: python server.py
Depois abra: http://localhost:8000/ui
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import json
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from core.memory   import MemoryManager
from core.chat     import ChatEngine
from core.commands import CommandHandler

# ── Inicialização ──────────────────────────────────────────
memory  = MemoryManager()
chat    = ChatEngine(memory)
handler = CommandHandler(memory, chat)
memory.load_last_session()

app = FastAPI(title="Artemis AI Co-Pilot", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rotas ──────────────────────────────────────────────────

@app.get("/health")
def health():
    ok = ChatEngine.health_check()
    return {"status": "ok" if ok else "ollama_offline", "model": "gemma4:e4b"}


@app.post("/chat")
async def chat_endpoint(request: Request):
    body       = await request.json()
    user_input = body.get("message", "").strip()

    if not user_input:
        return JSONResponse({"error": "Mensagem vazia"}, status_code=400)

    # Verifica se é um comando
    handled, response = handler.handle(user_input)
    if handled:
        return {"reply": response, "type": "command"}

    # Resposta normal (não-streaming para simplicidade na API)
    reply = chat.send(user_input)
    return {"reply": reply, "type": "chat"}


@app.post("/chat/stream")
async def chat_stream(request: Request):
    """Endpoint de streaming para exibir tokens conforme chegam."""
    body       = await request.json()
    user_input = body.get("message", "").strip()

    if not user_input:
        return JSONResponse({"error": "Mensagem vazia"}, status_code=400)

    handled, response = handler.handle(user_input)
    if handled:
        async def command_stream():
            yield f"data: {json.dumps({'token': response, 'done': True})}\n\n"
        return StreamingResponse(command_stream(), media_type="text/event-stream")

    async def token_stream():
        for token in chat.send_stream(user_input):
            yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"
        yield f"data: {json.dumps({'token': '', 'done': True})}\n\n"

    return StreamingResponse(token_stream(), media_type="text/event-stream")


@app.get("/memory")
def get_memory():
    return {
        "summary":  memory.long_summary,
        "profile":  memory.user_profile,
        "name":     memory.user_name,
        "stats":    memory.stats(),
    }


@app.post("/save")
def save():
    path = memory.save_session()
    memory.save_long_memory()
    return {"saved": path}


@app.get("/ui", response_class=HTMLResponse)
def serve_ui():
    ui_path = Path(__file__).parent / "ui" / "artemis.html"
    if ui_path.exists():
        return HTMLResponse(ui_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>UI não encontrada. Coloque artemis.html em ui/</h1>")


# ── Entry point ────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    print("\n  🚀 Artemis Web Server iniciando...")
    print("  📡 API:  http://localhost:8000")
    print("  🌐 UI:   http://localhost:8000/ui\n")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
