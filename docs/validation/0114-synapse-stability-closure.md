# 0114 — Synapse Stability Closure

Data da validação: 2026-07-07

## Objetivo

Fechar os fluxos que estavam implementados no código, mas ainda precisavam de validação e/ou estabilização antes de seguir para novas features.

## Escopo desta rodada

Prioridades tratadas nesta rodada:

1. Voice/STT no executável real
2. Avatar/3D/Wardrobe
3. Criação de agente sem fricção de aprovação
4. Insight detectando GPU real
5. Memória persistente entre sessões

## Resultado executivo

- O build do frontend, o rebuild do desktop e os testes direcionados passaram.
- Foi encontrado e corrigido um bug real na fundação de agentes/memória: o bootstrap do `DATA_DIR` não criava os seeds de `agents/orchestrator`, o que quebrava a base de runtime em testes.
- Nesta sessão eu não fiz a interação manual completa por clique no `synapse-desktop.exe` para as superfícies visuais mais sensíveis. Portanto, a validação final no executável continua pendente para os fluxos visuais.

## Validações executadas

Backend:

- `py -3 -m unittest tests.test_speech_adapters tests.test_voice_runtime tests.test_system_insight tests.test_wardrobe_runtime tests.test_agent_provisioning tests.test_runtime_foundation`
- `py -3 -m ruff check backend/synapse/core/data_dir.py tests/test_runtime_foundation.py tests/test_chat_runtime.py tests/test_system_insight.py tests/test_wardrobe_runtime.py tests/test_agent_provisioning.py`

Frontend:

- `npm test -- --run src/modules/ConversationsModule.test.tsx src/modules/WorkspaceModules.test.tsx src/components/avatar/AvatarSurface.test.tsx src/components/agent-directory/AgentFormDrawer.test.tsx src/modules/InsightModule.test.tsx`
- `npm run lint`
- `npm run build`

Desktop:

- `desktop/scripts/build-release-prototype.ps1 -PythonPath C:\Users\arthu\AppData\Roaming\uv\python\cpython-3.12.11-windows-x86_64-none\python.exe`

Artefatos gerados:

- `E:\Projetos\Synapse\frontend\dist\index.html` — `07/07/2026 18:09:02`
- `E:\Projetos\Synapse\backend\dist\synapse_backend\synapse_backend.exe` — `07/07/2026 18:08:48`
- `E:\Projetos\Synapse\desktop\release\synapse-desktop.exe` — `07/07/2026 18:10:04`

## Fase 1 — Voice/STT

Status: ⚠️ Parcial

### Evidência

- O pipeline de captura e transcrição está implementado em:
  - `frontend/src/audio/captureAudio.ts`
  - `frontend/src/components/chat/ChatComposer.tsx`
  - `frontend/src/audio/voiceSettings.ts`
  - `frontend/src/audio/conversationLoop.ts`
- Os testes relevantes de STT/voz passaram:
  - `tests.test_speech_adapters`
  - `tests.test_voice_runtime`
  - `src/modules/ConversationsModule.test.tsx`

### Bug encontrado

- Nenhum novo bug de STT foi encontrado nesta rodada de validação de código/build.
- O fluxo segue dependente de validação manual no executável empacotado para fechar a fase com confiança total.

### Correção aplicada

- Nenhuma correção adicional foi necessária nesta rodada para STT.

### Validação no `.exe`

- Pendência: confirmar manualmente no `E:\Projetos\Synapse\desktop\release\synapse-desktop.exe` o ciclo completo:
  - microfone inicia;
  - Faster-Whisper transcreve;
  - texto entra no input;
  - conversation mode escuta;
  - envia ao LLM;
  - resposta volta;
  - volta para listening.

---

## Fase 2 — Avatar / Wardrobe / GLB

Status: ⚠️ Parcial

### Evidência

- O fluxo Wardrobe → AvatarModelViewer → Chat/Agent Chat está implementado em:
  - `frontend/src/components/avatar/AvatarSurface.tsx`
  - `frontend/src/components/avatar/AvatarModelViewer.tsx`
  - `frontend/src/modules/WorkspaceModules.tsx`
  - `frontend/src/modules/ConversationsModule.tsx`
  - `backend/synapse/wardrobe/runtime.py`
  - `backend/synapse/wardrobe/models.py`
  - `backend/synapse/api/routes.py`
- Os testes relevantes passaram:
  - `tests.test_wardrobe_runtime`
  - `src/components/avatar/AvatarSurface.test.tsx`
  - `src/modules/WorkspaceModules.test.tsx`
  - `src/components/agent-directory/AgentFormDrawer.test.tsx`

### Bug encontrado

- Nenhum bug novo foi encontrado na validação por testes/build.
- A fase ainda precisa de confirmação visual manual no `.exe` para encerrar com segurança:
  - importar GLB;
  - preview inteiro;
  - texturas;
  - vínculo ao agente;
  - avatar no chat;
  - modos compact/fullscreen/off.

### Correção aplicada

- Nenhuma correção adicional foi necessária nesta rodada para o pipeline avatar/Wardrobe.

### Validação no `.exe`

- Pendência: confirmar visualmente no `synapse-desktop.exe`:
  - importação do GLB;
  - viewport inteiro;
  - preview e controles;
  - associação a agente;
  - avatar no chat;
  - modos compacto/tela cheia/desligado.

---

## Fase 3 — Criação de agente sem fricção de aprovação

Status: ⚠️ Parcial

### Evidência

- O fluxo de provisionamento/agendamento/aprovação está no backend e no frontend:
  - `backend/synapse/agents/provisioning.py`
  - `backend/synapse/agents/admin.py`
  - `backend/synapse/approvals/manager.py`
  - `frontend/src/components/agent-directory/AgentFormDrawer.tsx`
  - `frontend/src/modules/AgentDirectoryModule.tsx`
- Os testes de provisioning passaram.

### Bug encontrado

- Foi encontrado um problema de bootstrap que afetava a fundação de agentes em runtime de teste:
  - o `DATA_DIR` não estava se preparando corretamente para `agents/orchestrator`.
- Isso quebrava a base de runtime necessária para validar criação/memória/agente.

### Correção aplicada

- Corrigi `backend/synapse/core/data_dir.py` para semear os arquivos básicos de `agents/orchestrator`:
  - `CONFIG.yaml`
  - `SOUL.md`
  - `MEMORY.md`
  - `SKILLS.md`
  - `INBOX.md`

### Validação no `.exe`

- Pendência: confirmar manualmente no executável:
  - criar agente sem ficar preso em aprovação;
  - conversar com agente;
  - agente responde texto normal, não JSON/tool_summary.

---

## Fase 4 — Insight / GPU real

Status: ⚠️ Parcial

### Evidência

- A detecção de hardware está implementada em:
  - `backend/synapse/system_insight/runtime.py`
  - `backend/synapse/model_hub/recommendations.py`
- Há fallback Windows vendor-neutral via `Win32_VideoController` quando `nvidia-smi` não cobre a máquina.
- Os testes de `tests.test_system_insight` passaram.

### Bug encontrado

- Nenhum bug novo foi encontrado nesta rodada de validação de código/build.
- A fase ainda exige confirmação manual no `.exe` com a GPU real da máquina alvo.

### Correção aplicada

- Nenhuma correção adicional foi necessária nesta rodada para o Insight.

### Validação no `.exe`

- Pendência: confirmar no executável:
  - GPU AMD aparece;
  - VRAM aparece ou fallback amigável;
  - recomendações usam hardware real.

---

## Fase 5 — Memória persistente entre sessões

Status: ⚠️ Parcial

### Evidência

- Há suporte de memória em:
  - `backend/synapse/memory/store.py`
  - `backend/synapse/context/loader.py`
  - `backend/synapse/chat/runtime.py`
- Os testes de `tests.test_chat_runtime` e `tests.test_runtime_foundation` passaram após a correção do bootstrap.

### Bug encontrado

- O bootstrap do `DATA_DIR` não criava o esqueleto de `agents/orchestrator`, o que impedia a fundação de runtime/memória em testes.

### Correção aplicada

- A mesma correção aplicada para agentes também estabilizou a base de memória:
  - `backend/synapse/core/data_dir.py` passou a semear os arquivos do `orchestrator`.

### Validação no `.exe`

- Pendência: confirmar manualmente no executável:
  - conversar com agente;
  - fechar app;
  - reabrir app;
  - agente lembrar informação anterior.

---

## Ordem de prioridade para seguir fechando

1. Voice/STT no `.exe`
2. Avatar/Wardrobe no `.exe`
3. Criação de agente sem fricção de aprovação
4. Insight com GPU real na máquina alvo
5. Memória persistente entre sessões no `.exe`

## Conclusão

O estado atual ficou melhor do que o ponto de partida desta rodada:

- a base de runtime de agentes/memória foi corrigida;
- os testes backend relevantes passaram;
- os testes frontend relevantes passaram;
- o desktop release foi rebuildado com sucesso.

O que ainda falta para encerrar esta etapa com rigor é a validação manual no executável empacotado das superfícies visuais e interativas apontadas acima.
