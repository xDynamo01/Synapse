# Synapse V3 / Backend Freeze Audit

Data da auditoria: 2026-07-09

Escopo executado:

- Frontend Electron ADE removido por completo: `apps/electron-ade/` foi excluído.
- Resíduos visuais/operacionais do Electron ADE foram limpos.
- O backend permaneceu intacto.
- Esta auditoria é somente análise; não implementa correções de produto.

Observação de contexto:

- Ainda existem documentos históricos em `docs/` que mencionam o Electron ADE/V3. Isso foi preservado por decisão explícita de manter documentação histórica.
- Não restou nenhuma camada de apresentação ativa no diretório `apps/electron-ade/`; o repositório agora está backend-first.

## 1. Arquitetura

### Visão geral

O backend do Synapse é uma composição grande e explícita, montada em `backend/synapse/core/app.py` e exposta por um único roteador FastAPI em `backend/synapse/api/routes.py`.

Estrutura principal:

- `core/`
  - bootstrap, config, data dir, eventos, permissões, serialização, roteamento de modelos.
- `agents/`
  - identidade, registro, auditoria, admin, provisionamento e runtime.
- `conversations/` e `chat/`
  - persistência de conversas e orquestração de turnos com LLM / chat local.
- `models/`, `model_providers/`, `model_hub/`, `providers/`, `provider_plugins/`
  - roteamento, health, descoberta, defaults e catálogo de modelos/provedores.
- `tools/`, `tool_intents/`, `tool_discovery/`, `approvals/`, `execution_router/`, `mcp*`
  - execução de ferramentas, decisão de permissão, intents e bridge MCP.
- `audio/`, `voice/`, `speech_adapters/`, `speech_pipeline/`
  - áudio, STT/TTS, sessões, adaptação e pipeline multimodal/voz.
- `memory/`, `context/`, `context_fusion/`
  - memória persistente simples, carregamento de contexto, fusão multimodal.
- `avatar/`, `embodiment/`, `wardrobe/`
  - estado de avatar, perfil de embodiment e inventário visual/3D.
- `communication/`, `email/`
  - comunicação genérica, inbox/drafts e integração de email.
- `vision/`, `multimodal/`, `perception/`
  - sinais multimodais, visão, percepção e agregação de eventos.
- `health/`, `readiness/`, `system_insight/`
  - diagnóstico operacional, readiness e inteligência de hardware.
- `missions/`, `mission_control/`, `delegation*`, `dead_letter/`, `retention/`, `scheduler/`, `daemon/`
  - fluxo operacional, filas, retry, timeout, daemon e retenção.
- `ui_contracts/`, `app_shell/`
  - superfícies de contrato para UI, sem frontend acoplado.

### Dependências e acoplamento

Pontos de maior acoplamento:

- `backend/synapse/core/app.py`
  - funciona como composition root e instancia praticamente todos os runtimes.
  - o arquivo é estável, mas concentra muita responsabilidade.
- `backend/synapse/api/routes.py`
  - roteador monolítico; todas as rotas de produto convergem aqui.
  - isso é funcional, porém eleva custo de manutenção e aumenta risco de regressão por edição acidental.
- `backend/synapse/chat/runtime.py`
  - acopla conversa, memória, contexto, modelos, presença e persistência de sessão.
- `backend/synapse/voice/runtime.py`
  - acopla voz, embodiment, avatar, áudio e speech adapters.
- `backend/synapse/context_fusion/runtime.py`
  - agrega conversa, missão, percepção, multimodal, health e readiness.
- `backend/synapse/tools/runtime.py`
  - mistura infraestrutura genérica de tools com seeds de domínio (email, voice, missions, providers).

### Violações / tensões arquiteturais observadas

- Roteador FastAPI único para todo o domínio: operacionalmente simples, mas pouco modular.
- Presença simultânea de superfícies reais e mock/placeholder no mesmo nível de API.
- Camadas duplicadas de provider/adapters:
  - `providers/`
  - `speech_adapters/`
  - `model_providers/`
  - `provider_plugins/`
  - isso é flexível, mas hoje também é fonte de duplicação e confusão semântica.
- `commands/runtime.py` ainda funciona como “superfície de debug/admin” com muitos comandos mock.
- `app_shell` e `ui_contracts` descrevem UI, mas não há UI dentro deste repositório após a remoção do Electron ADE.

## 2. APIs

Inventário por módulo. Os endpoints abaixo vêm de `backend/synapse/api/routes.py`.

### Admin / policy / approvals

- `GET /admin-policy`
- `POST /admin-check`
- `GET /approvals/pending`
- `POST /approvals/{approval_id}/approve`
- `POST /approvals/{approval_id}/reject`
- `GET /agent-admin/requests`
- `GET /agent-admin/requests/retention`
- `POST /agent-admin/requests/cleanup`
- `GET /agent-admin/requests/{request_id}`
- `POST /agent-admin/requests`
- `POST /agent-admin/requests/{request_id}/approve`
- `POST /agent-admin/requests/{request_id}/reject`
- `POST /agent-admin/requests/{request_id}/apply`

### Agents

- `GET /agents`
- `GET /agents/{agent_id}`
- `POST /agents`
- `PATCH /agents/{agent_id}`
- `POST /agents/{agent_id}/validate`
- `POST /agents/{agent_id}/activate`
- `POST /agents/{agent_id}/deactivate`
- `POST /agents/{agent_id}/archive`
- `POST /agents/{agent_id}/restore`
- `GET /agents/{agent_id}/capabilities`
- `GET /agents/{agent_id}/inbox`
- `POST /agents/{agent_id}/process-inbox`
- `GET /agents/{agent_id}/audit`
- `GET /agents/{agent_id}/audit/summary`
- `GET /agents/{agent_id}/tools`
- `POST /agents/{agent_id}/tool-call/preview`
- `POST /agents/{agent_id}/tool-call/create`
- `GET /agents/{agent_id}/context-preview/{conversation_id}`
- `POST /agents/{agent_id}/process-delegations`
- `POST /agents/{agent_id}/enqueue-delegations`
- `POST /agents/{to_agent_id}/messages`
- `POST /agents/{agent_id}/local-chat`
- `GET /agent-directory`

### App shell / UI contracts

- `GET /app-shell`
- `GET /app-shell/modules`
- `GET /app-shell/panels`
- `GET /app-shell/navigation`
- `GET /ui-contracts`
- `GET /ui-contracts/mission-control`
- `GET /ui-contracts/agents`
- `GET /ui-contracts/health`
- `GET /ui-contracts/readiness`
- `GET /ui-contracts/notifications`
- `GET /ui-contracts/conversations/{conversation_id}`
- `GET /ui-contracts/missions/{mission_id}`

### Audio / voice / speech

- `GET /voice/sessions`
- `POST /voice/sessions`
- `GET /voice/sessions/{session_id}`
- `GET /voice/sessions/{session_id}/utterances`
- `POST /voice/sessions/{session_id}/queue`
- `POST /voice/sessions/{session_id}/pause`
- `POST /voice/sessions/{session_id}/resume`
- `POST /voice/sessions/{session_id}/close`
- `GET /voice/settings`
- `PATCH /voice/settings`
- `GET /voice/devices`
- `POST /voice/devices/{device_id}/test`
- `GET /voice/providers`
- `GET /voice/recordings`
- `POST /voice/recordings`
- `GET /voice/recordings/{recording_id}`
- `POST /voice/recordings/{recording_id}/transcribe`
- `POST /voice/conversation/turn`

- `GET /audio/sessions`
- `POST /audio/sessions`
- `GET /audio/sessions/{session_id}`
- `POST /audio/sessions/{session_id}/pause`
- `POST /audio/sessions/{session_id}/resume`
- `POST /audio/sessions/{session_id}/close`
- `GET /audio/devices`
- `POST /audio/mock/transcribe`
- `POST /audio/mock/synthesize`
- `POST /audio/synthesize`
- `POST /audio/transcribe`

- `GET /speech/sessions`
- `POST /speech/sessions`
- `GET /speech/sessions/{session_id}`
- `POST /speech/sessions/{session_id}/pause`
- `POST /speech/sessions/{session_id}/resume`
- `POST /speech/sessions/{session_id}/close`
- `POST /speech/sessions/{session_id}/input/mock`
- `POST /speech/sessions/{session_id}/output/mock`
- `GET /speech/sessions/{session_id}/summary`
- `GET /speech-adapters`
- `GET /speech-adapters/health`
- `GET /speech-adapters/resolve/{capability_id}`
- `GET /speech-adapters/{adapter_id}`

### Avatar / embodiment / wardrobe

- `GET /avatar/sessions`
- `POST /avatar/sessions`
- `GET /avatar/sessions/{session_id}`
- `GET /avatar/sessions/{session_id}/state`
- `POST /avatar/sessions/{session_id}/expression`
- `POST /avatar/sessions/{session_id}/pose`
- `POST /avatar/sessions/{session_id}/pause`
- `POST /avatar/sessions/{session_id}/resume`
- `POST /avatar/sessions/{session_id}/close`

- `GET /embodiments`
- `GET /embodiments/{agent_id}`
- `POST /embodiments/{agent_id}/activate`
- `POST /embodiments/{agent_id}/deactivate`

- `GET /wardrobe/assets`
- `GET /wardrobe/bindings`
- `POST /wardrobe/bindings`
- `DELETE /wardrobe/bindings/{agent_id}`
- `POST /wardrobe/assets/import`
- `PATCH /wardrobe/assets/{asset_id}`
- `DELETE /wardrobe/assets/{asset_id}`
- `GET /wardrobe/assets/{asset_id}/file`

### Chat / conversations / context

- `POST /chat`
- `POST /local-chat`
- `GET /conversations`
- `POST /conversations`
- `GET /conversations/{conversation_id}`
- `DELETE /conversations/{conversation_id}`
- `GET /conversations/{conversation_id}/messages`
- `GET /conversations/{conversation_id}/summary`
- `POST /conversations/{conversation_id}/summary`
- `GET /conversations/{conversation_id}/context`
- `POST /conversations/{conversation_id}/local-chat`
- `POST /messages/send`
- `POST /messages/{message_id}/ack`
- `GET /context/conversation/{conversation_id}`
- `GET /context/mission/{mission_id}`
- `GET /context/session/{session_id}`
- `GET /context/validate/{conversation_id}`

### Communication / email

- `GET /communication/messages`
- `GET /communication/messages/{message_id}`
- `GET /communication/drafts`
- `POST /communication/drafts`
- `GET /communication/drafts/{draft_id}`
- `POST /communication/drafts/{draft_id}/approve`
- `POST /communication/drafts/{draft_id}/reject`
- `POST /communication/drafts/{draft_id}/request-send`
- `GET /communication/outbound`
- `POST /communication/outbound/{request_id}/approve`
- `POST /communication/outbound/{request_id}/reject`
- `GET /communication/summary`

- `GET /email/accounts`
- `POST /email/accounts`
- `GET /email/accounts/{account_id}`
- `PATCH /email/accounts/{account_id}`
- `POST /email/accounts/{account_id}/disable`
- `GET /email/oauth/settings`
- `PATCH /email/oauth/settings`
- `GET /email/bridge/thunderbird/status`
- `POST /email/bridge/thunderbird/rotate-token`
- `POST /email/bridge/thunderbird/messages`
- `POST /email/providers/resolve`
- `POST /email/accounts/{account_id}/oauth/microsoft/start`
- `POST /email/accounts/{account_id}/oauth/microsoft/complete`
- `POST /email/accounts/{account_id}/oauth/disconnect`
- `POST /email/accounts/{account_id}/test`
- `GET /email/accounts/{account_id}/folders`
- `POST /email/accounts/{account_id}/sync`
- `GET /email/accounts/{account_id}/messages`
- `GET /email/accounts/{account_id}/messages/{message_id}`

### Capabilities / providers / model hub / models

- `GET /capabilities`
- `GET /capabilities/{capability_id}`

- `GET /providers`
- `GET /providers/health`
- `GET /providers/resolve/{capability_id}`
- `GET /providers/{provider_id}`
- `GET /providers/lmstudio/status`
- `GET /providers/lmstudio/models`
- `POST /providers/lmstudio/chat`
- `GET /provider-settings`
- `GET /provider-settings/{provider_id}`
- `PATCH /provider-settings/{provider_id}`
- `POST /provider-settings/{provider_id}/test`
- `POST /provider-settings/{provider_id}/clear-key`

- `GET /provider-plugins`
- `GET /provider-plugins/health`
- `GET /provider-plugins/summary`
- `GET /provider-plugins/{plugin_id}`
- `POST /provider-plugins/{plugin_id}/enable`
- `POST /provider-plugins/{plugin_id}/disable`

- `GET /models/catalog`
- `GET /models/available`
- `GET /models/discovered`
- `GET /models/providers`
- `GET /models/default`
- `POST /models/default`
- `GET /models/folders`
- `POST /models/folders`
- `DELETE /models/folders/{folder_id}`
- `POST /models/refresh`
- `POST /models/providers/{provider_id}/test`

### Health / readiness / insight

- `GET /health`
- `GET /system/insight`
- `GET /agent-multimodal-policy`
- `GET /readiness`
- `GET /readiness/issues`
- `GET /readiness/actions`

### Missions / delegation / mission control

- `GET /missions`
- `POST /missions`
- `GET /missions/{mission_id}`
- `POST /missions/{mission_id}/tasks`
- `GET /missions/{mission_id}/tasks`
- `GET /missions/{mission_id}/summary`
- `GET /missions/{mission_id}/context`
- `GET /missions/{mission_id}/health`
- `GET /missions/{mission_id}/recovery`
- `GET /missions/{mission_id}/status`

- `GET /mission-control/overview`
- `GET /mission-control/missions/{mission_id}`
- `GET /mission-control/attention`
- `GET /mission-control/work-queue`
- `GET /mission-control/agents/workload`

- `GET /delegations`
- `GET /delegations/{task_id}`
- `GET /delegations/{task_id}/executions`
- `POST /delegations/timeout-scan`
- `POST /delegations/{task_id}/timeout-check`
- `POST /delegations/{task_id}/timeout-apply`
- `POST /delegations/{task_id}/retry-check`
- `POST /delegations/{task_id}/retry`
- `POST /delegations/{task_id}/autonomy-check`
- `POST /delegations`
- `POST /delegations/{task_id}/accept`
- `POST /delegations/{task_id}/reject`
- `POST /delegations/{task_id}/start`
- `POST /delegations/{task_id}/complete`
- `GET /delegations/{task_id}/completion`
- `POST /delegations/{task_id}/completion`
- `POST /delegations/{task_id}/completion/apply`

- `GET /delegation-executions/{execution_id}`
- `GET /delegation-inbox/{agent_id}`
- `GET /delegation-inbox/{agent_id}/summary`
- `GET /delegation-inbox/{agent_id}/next`
- `GET /delegation-inbox/{agent_id}/order`
- `POST /delegation-inbox/{agent_id}/rebuild`
- `POST /delegation-inbox/rebuild-all`
- `GET /delegation-autonomy-policy`
- `GET /delegation-retry-policy`
- `GET /delegation-scheduling-policy`
- `GET /delegation-timeout-policy`

- `GET /recovery/summary`
- `GET /recovery/open`
- `GET /recovery/{task_id}`

### Notifications / presence / lifecycle / scheduler / daemon / workers

- `GET /notifications`
- `GET /notifications/unread`
- `POST /notifications/cleanup`
- `GET /notifications/{notification_id}`
- `POST /notifications/{notification_id}/read`
- `DELETE /notifications/{notification_id}`

- `GET /presence`
- `GET /presence/{agent_id}`
- `GET /lifecycle`
- `GET /lifecycle/{agent_id}`
- `POST /lifecycle/{agent_id}/wake`
- `POST /lifecycle/{agent_id}/sleep`

- `GET /daemon/status`
- `POST /daemon/run-once`
- `GET /daemon/runner`
- `POST /daemon/runner/heartbeat`
- `GET /jobs`
- `POST /jobs`
- `POST /jobs/run`
- `POST /jobs/{job_id}/cancel`
- `GET /scheduler/recurring`
- `POST /scheduler/recurring/run`
- `GET /scheduler/lock`

- `GET /workers/status`

### Misc / execution / decisions / tasks / trace / events

- `GET /execution/targets`
- `POST /execution/plan`
- `GET /execution/summary`
- `POST /decision-check`
- `GET /tasks`
- `POST /tasks`
- `GET /events`
- `GET /trace/{correlation_id}`
- `GET /migrations`
- `GET /dead-letter`
- `GET /dead-letter/{dlq_id}`
- `POST /dead-letter`
- `POST /dead-letter/{dlq_id}/review`
- `POST /dead-letter/{dlq_id}/restore`
- `POST /dead-letter/{dlq_id}/close`
- `GET /retention`
- `GET /retention/domains/{domain_id}`
- `POST /retention/domains/{domain_id}/cleanup`
- `POST /retention/cleanup-all`

- `GET /mcp/servers`
- `GET /mcp/servers/{server_id}`
- `GET /mcp/tools`
- `GET /mcp/summary`
- `GET /mcp/bridge`
- `POST /mcp/bridge/sync`
- `GET /mcp/bridge/tools/{bridge_tool_id}`

### Route-level assessment

- Complete and currently useful:
  - core health / readiness / provider registry / model hub / agents / conversations / tools / permissions / scheduler / retention / notifications / mission control / app shell contracts.
- Partial or still mixed with placeholders:
  - voice / audio / speech / avatar / wardrobe / email / vision / multimodal / perception / communication / commands.
- Placeholder-only or mostly diagnostic:
  - mock speech, mock audio, mock vision, mock communication, mock model routing, mock summary helpers, placeholder TTS fields, OpenAI-compatible adapter.

## 3. Estado dos módulos

| Módulo | Objetivo | Estado atual | Problemas encontrados | Prioridade |
|---|---|---|---|---|
| `core` | Bootstrap, config, data, events, permissions, serialization | Completo | `core/app.py` concentra demasiada composição | Alta |
| `api` | Expor a superfície do backend | Completo, mas monolítico | `routes.py` é muito grande e mistura produção com mocks | Alta |
| `agents` | CRUD, identidade, provisionamento, audit, admin | Majoritariamente completo | Seed de `orchestrator` e provisionamento ainda geram complexidade | Alta |
| `conversations` / `chat` | Conversas, mensagens, local chat, histórico | Majoritariamente completo | `generate_mock_summary` e ramificações de local chat ainda são heurísticas | Alta |
| `tools` / `tool_intents` / `approvals` | Execução segura de ferramentas | Completo | `tools/runtime.py` virou catálogo de domínio + permissões + helpers de email/voz | Alta |
| `models` / `model_hub` / `providers` / `model_providers` | Descoberta e roteamento de modelos | Parcial-real | `OpenAICompatibleAdapter` ainda não implementado; fallback mock existe | Alta |
| `memory` | Memória persistente | Mínimo funcional | Só markdown file-based; sem memória semântica/estrutural avançada | Média |
| `context` / `context_fusion` | Compor contexto para LLM e multimodal | Parcial-real | Fusão ampla, mas ainda baseada em memória local + sinais e não em camadas semânticas ricas | Alta |
| `voice` / `audio` / `speech_adapters` / `speech_pipeline` | STT/TTS e loop de voz | Parcial-real | Mocks convivem com STT/TTS reais; sem separação limpa entre STT e TTS no contrato | Alta |
| `avatar` / `embodiment` / `wardrobe` | Estado do avatar e assets visuais | Parcial-real | Backend guarda estado/config, mas renderer real é externo ao backend | Média |
| `communication` / `email` | Email e comunicação geral | Parcial-real | Gmail provider ainda é stub; Thunderbird bridge e OAuth coexistem; muitos diagnósticos/fluxos | Alta |
| `vision` / `multimodal` / `perception` | Sinais multimodais e visão | Parcial/mock | `vision` é mock no caminho principal; percepção é armazenamento/ponte de sinais | Média |
| `missions` / `mission_control` / `delegation*` | Orquestração operacional | Completo | Complexidade alta, muita política de timeout/retry/recuperação | Média |
| `health` / `readiness` / `system_insight` | Diagnóstico e recomendação | Parcial-real | Boa base, mas regras e mensagens ainda são heurísticas | Alta |
| `notifications` / `presence` / `lifecycle` / `scheduler` / `daemon` / `retention` / `dead_letter` | Infraestrutura operacional | Completo | Denso, mas estável; dívida é mais de volume que de falha | Média |
| `app_shell` / `ui_contracts` | Contratos de UI | Completo como contrato | Não há frontend ativo neste repositório após a remoção do Electron ADE | Baixa |
| `commands` | CLI/command surface | Completo, porém inchado | Muitos comandos mock/debug e rotas de diagnóstico misturadas com produto | Alta |

## 4. Backend Health

### Código morto / duplicações / workarounds

- `OpenAICompatibleAdapter.generate()` ainda levanta `NotImplementedError`.
- Há múltiplas superfícies mock:
  - `audio/mock/*`
  - `speech/*/mock`
  - `vision/mock/*`
  - `communication/mock_provider.py`
  - `MockModelAdapter`
  - `mock_stt`, `mock_tts`, `mock_voice_analysis`, `mock_vision`, `mock_avatar_renderer`, etc.
- Existe sobreposição funcional entre:
  - `providers`
  - `speech_adapters`
  - `model_providers`
  - `provider_plugins`
  - o que é bom para extensibilidade, mas hoje ainda não está semanticamente consolidado.
- `commands/runtime.py` expõe uma quantidade muito grande de comandos que já são efetivamente uma shell administrativa paralela.
- `conversation.generate_mock_summary()` e o modo `mock` em `speech_pipeline` ainda carregam comportamento de suporte, não de produto final.

### TODOs / FIXMEs / placeholders observados por inspeção

- `NotImplementedError` em `models/adapters.py` para OpenAI-compatible.
- Mocks explícitos em voz, áudio, visão, comunicação e métricas de health.
- `email` ainda mantém vários caminhos de diagnóstico/“bridge”/OAuth ao mesmo tempo.
- `speech_pipeline` e `voice` têm transição incompleta entre provider, adapter e policy.

### Dependências desnecessárias ou frágeis

- Dependência excessiva de `127.0.0.1` em defaults de LM Studio/Ollama.
- Caminho de modelos `voice/models/faster-whisper` e diretórios de cache estão assumidos como layout local do DATA_DIR.
- O backend ainda assume contexto operacional local (Windows alpha) em vários pontos:
  - DPAPI para credenciais do provider settings.
  - `powershell`/`pwsh` como fallback em alguns diagnósticos de sistema.

### Arquivos órfãos / superfícies residuais

- Não há frontend ativo do Electron ADE.
- Há documentação histórica do Electron ADE em `docs/`, que foi preservada.
- A superfície de UI restante no backend é somente contrato (`app_shell`, `ui_contracts`) e não apresentação real.

## 5. Voice

### Fluxo atual

1. `voice/settings.yaml` armazena:
   - `provider_id`
   - `stt_provider_id`
   - `tts_provider_id`
   - `device_id`
   - `language`
   - `model`
2. `VoiceRuntime` normaliza legado:
   - se `provider_id == "piper"`, STT é corrigido para `faster_whisper`.
3. `speech_adapters` registra:
   - `mock_stt_adapter`
   - `faster_whisper_adapter`
   - `mock_tts_adapter`
   - `piper_tts_adapter`
   - `mock_voice_analysis_adapter`
4. `AudioRuntime` delega:
   - transcrição para `SpeechAdapterRuntime`
   - síntese para `SpeechAdapterRuntime`
5. `SpeechAdapterRuntime` escolhe o adapter por capability (`speech_to_text` / `text_to_speech`) e aplica policy.
6. `PerceptionRuntime` converte STT/TTS e outros sinais para eventos multimodais.
7. `SpeechPipelineRuntime` mantém o loop multimodal e ainda expõe caminhos mock.
8. `AvatarRuntime` e `VoiceRuntime` sincronizam estado de fala com avatar/embodiment quando há sessão ativa.

### Estado atual

- STT real:
  - existe `faster_whisper_adapter`.
  - o fluxo de áudio já se apoia em `AudioRuntime` + `SpeechAdapterRuntime`.
- TTS real:
  - existe `piper_tts_adapter`.
  - o backend sabe resolver provider TTS via embodiment/policy.
- Diagnóstico:
  - `voice/runtime.py` persiste sessões, gravações e settings.
  - `audio/runtime.py` e `speech_adapters/runtime.py` emitem eventos de health/transcrição/síntese.
- Conversação por voz:
  - existe infraestrutura de sessão, fila, pause/resume/close, e sincronização com avatar.

### Problemas e dívida

- O ecossistema de voz ainda tem três camadas de abstração ao mesmo tempo:
  - provider registry
  - speech adapter registry
  - voice runtime settings
- Ainda há muitas superfícies mock na API e em comandos.
- O contrato entre STT e TTS já foi separado no runtime, mas a semântica ainda é fácil de confundir na ponta da aplicação.
- O backend já está funcional como pipeline, porém ainda é pesado e fácil de quebrar por configuração mal persistida.

### O que precisa ser refeito no futuro

- Consolidar o contrato de voz:
  - STT de um lado
  - TTS de outro
  - voice analysis separado
- Eliminar qualquer ambiguidade entre:
  - `provider_id`
  - `stt_provider_id`
  - `tts_provider_id`
- Reduzir os caminhos mock de voz/áudio para teste explícito, não para rotas de produto.

## 6. Memory

### Estado

- O backend tem `MemoryStore` simples, baseado em markdown:
  - `memory/USER.md`
  - `memory/SYSTEM.md`
  - `memory/MEMORY.md`
  - `agents/<id>/MEMORY.md`
- `ContextLoader` inclui memória, identidade, tarefas e histórico no prompt.
- `ChatRuntime` persiste fatos simples do usuário por regex.

### Limitações

- Não existe memória vetorial.
- Não existe memória semântica indexada.
- Não existe working memory separada de forma formal.
- A persistência é útil, mas ainda bastante literal.

### Conclusão

O módulo de memória existe e funciona como base persistente local, mas ainda está em estágio mínimo. Ele é suficiente para o backend freeze, porém não fecha o problema de longo prazo de contexto e recuperação.

## 7. Agentes

### Representação atual

- `AgentRegistry` lê `agents/<agent_id>/CONFIG.yaml`.
- `AgentIdentityRuntime` agrega `CONFIG.yaml`, `SOUL.md` e `SKILLS.md`.
- `AgentProvisioningRuntime` cria/valida/atualiza agentes.
- `AgentRuntime` chama `ModelRouter` e `ToolRouter`, aplica policy e tool-calls.
- `ConversationRuntime` valida participantes e registra mensagens.

### Comunicação e escalabilidade

- O modelo é orientado a arquivos locais e políticas explícitas.
- A escalabilidade funcional já é boa para single-node local-first.
- O custo está em:
  - provisionamento,
  - policy,
  - tool calling,
  - e a grande superfície de roteadores e runtimes auxiliares.

### Problemas encontrados

- Seed de agente `orchestrator` em bootstrap.
- A fronteira entre “agente como identidade” e “agente como runtime” ainda é larga.

### Conclusão

Os agentes estão operacionais e bem modelados para o estado atual, mas o módulo continua acoplado a muitos subsistemas de infraestrutura. A dívida principal é orquestração/crescimento da superfície, não falta de capacidade básica.

## 8. Modelos

### Estado

- `ModelRouter` resolve o roteamento do modelo padrão e do modelo preferido do agente.
- `ModelHubRuntime` descobre, deduplica, persiste snapshot e expõe catálogo/provedores.
- `providers` e `provider_plugins` complementam a descoberta.
- `model_providers/lmstudio.py` integra LM Studio.
- `models/adapters.py` implementa `MockModelAdapter`, `OllamaModelAdapter` e um placeholder para OpenAI-compatible.

### O que está completo

- Descoberta local de modelos.
- Default model/provider.
- Integração com LM Studio e Ollama.
- Health e snapshots.

### O que está parcial

- OpenAI-compatible ainda não implementado.
- O comportamento de mock em dev/test é intencional, mas ainda é uma bifurcação relevante.

### Conclusão

O módulo de modelos é utilizável para o backend atual, mas precisa de consolidação de provider contracts antes de crescer.

## 9. Insight

### Estado atual

- `SystemInsightRuntime` coleta:
  - SO
  - CPU
  - memória
  - disco
  - Python
  - git
  - GPU
  - LM Studio
- GPU:
  - usa `nvidia-smi` como fast path.
  - usa fallback Windows via `Get-CimInstance Win32_VideoController`.
  - tenta inferir fabricante por nome/compatibilidade.
- Recomendações:
  - `build_llm_recommendations()` usa RAM + VRAM + catálogo/modelos instalados + providers.

### Conclusão

O insight deixou de ser NVIDIA-only e já possui fallback vendor-neutral para Windows. O principal risco agora é semântica de recomendação, não apenas detecção.

## 10. Configuração

### Hardcodes relevantes

Não foi encontrado path absoluto de desenvolvedor em código backend (`E:\\Projetos\\...` ou `C:\\Users\\arthu\\...`) nas rotinas do backend. Os hardcodes restantes são de infraestrutura local e defaults de runtime:

- `127.0.0.1:11434` e `127.0.0.1:1234/v1`:
  - LM Studio / Ollama defaults.
- `SYNAPSE_HOST` default: `127.0.0.1`.
- `SYNAPSE_PORT` default: `8717`.
- `SYNAPSE_DATA_DIR` default: `./data`.
- `voice/models/faster-whisper`.
- `email/oauth/*`, `wardrobe/assets/*`, `memory/*`.
- `config/local_chat_policy.yaml`.
- `config/voice_settings.yaml`.
- `config/email_oauth.yaml`.
- `config/provider_policy.yaml`.
- `config/speech_adapter_policy.yaml`.

### Seed/configuração inicial

O bootstrap do DATA_DIR ainda injeta:

- `agents/orchestrator/*`
- `memory/USER.md`
- `memory/MEMORY.md`
- `memory/SYSTEM.md`
- vários `config/*.yaml`
- `provider_plugins/manifests/*.yaml`

Isso é aceitável para um backend local-first, mas deve ser considerado “estado seedado”, não estado vazio.

## 11. Qualidade

| Módulo | Estado | Dívida técnica | Prioridade |
|---|---|---|---|
| Core / bootstrap | Completo | Alto acoplamento em `core/app.py` | Alta |
| API router | Completo | Monólito muito grande | Alta |
| Agents | Quase completo | Seed/orchestrator e muitas responsabilidades | Alta |
| Conversations / Chat | Completo o suficiente | Mock summary e local chat com bifurcações | Alta |
| Tools / Intents / Approvals | Completo | Superfície muito ampla, mistura de domínios | Alta |
| Model Hub / Providers | Parcial-real | OpenAI-compatible não implementado | Alta |
| Memory | Mínimo funcional | Sem memória semântica / indexada | Média |
| Context / Context Fusion | Parcial-real | Agregação ampla, mas sem refinamento semântico | Alta |
| Voice / Audio / Speech | Parcial-real | Dupla semântica STT/TTS + mocks | Alta |
| Avatar / Embodiment / Wardrobe | Parcial-real | Configuração existe; renderer real fora do backend | Média |
| Communication / Email | Parcial-real | Gmail provider stub; muitos caminhos de diagnóstico/bridge | Alta |
| Vision / Multimodal / Perception | Parcial/mock | Caminho de produto ainda não consolidado | Média |
| Insight | Parcial-real | Recomendações heurísticas, mas útil | Alta |
| Missions / Delegation | Completo | Complexidade operacional alta | Média |
| Health / Readiness | Completo | Reflete a complexidade do sistema | Média |
| Scheduler / Daemon / Retention / Presence / Lifecycle | Completo | Forte dependência de estado local | Média |
| Commands | Completo | Inchaço e comandos debug/mock demais | Alta |
| App shell / UI contracts | Completo como contrato | Sem frontend ativo no repositório atual | Baixa |

## 12. Roadmap Backend

Ordem recomendada para finalizar o backend sem voltar a tocar em frontend agora:

1. Consolidar contratos centrais:
   - `providers`
   - `speech_adapters`
   - `model_providers`
   - `embodiment`
   - `app_shell` / `ui_contracts`
2. Reduzir ambiguidade de voz:
   - separar formalmente STT, TTS e voice analysis nas policies e DTOs;
   - diminuir a superfície mock de produto.
3. Fechar o modelo de contexto:
   - memória,
   - history,
   - mission context,
   - multimodal/perception,
   - context fusion.
4. Endurecer agentes e ferramentas:
   - menos comandos globais,
   - mais contratos por capability,
   - menos lógica duplicada em commands/tool runtime.
5. Reforçar email e communication:
   - clarificar provider real vs bridge vs mock;
   - reduzir ruído de diagnóstico e fluxos paralelos.
6. Simplificar vision/avatar/wardrobe:
   - backend deve manter estado e contratos, não tentar adivinhar renderer.
7. Depois disso:
   - revisar `api/routes.py` e quebrá-lo por roteadores de domínio se a manutenção começar a piorar.

## Conclusão executiva

O backend está intacto e amplo, mas ainda mistura superfícies reais com placeholders em quase todos os domínios multimodais e operacionais. O que mais pesa hoje não é falta de arquitetura, e sim excesso de superfícies paralelas:

- múltiplos providers/adapters,
- múltiplos caminhos mock,
- roteador monolítico,
- e contratos de UI residuais sem frontend ativo.

O próximo foco correto é congelar a superfície de apresentação e terminar o backend por módulos, começando por contratos centrais, voz, contexto/memória e simplificação das camadas de provider.
### Administrative DataDir maintenance audit — 2026-07-14

The prior Foundation adapter and generic Retention cleanup transports are no
longer accepted architecture. Administrative delivery has zero direct DataDir
access and zero filesystem mutation calls. Registered scopes, owner
contributors and durable plans are the only canonical route. Backup, restore
and migration remain unavailable rather than simulated.
