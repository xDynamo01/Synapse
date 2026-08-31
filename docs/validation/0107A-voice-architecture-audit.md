# 0107.A — Voice & Communication Architecture Audit

Data: 2026-07-02
Escopo: auditoria técnica בלבד. Nenhuma feature foi implementada nesta etapa.

## 1. Estado atual

### O que já existe

- Voice já é um runtime backend de primeira classe em `backend/synapse/voice/runtime.py`.
- Existe um runtime de áudio separado em `backend/synapse/audio/runtime.py`.
- O backend já possui camadas explícitas para:
  - `chat` (`backend/synapse/chat/runtime.py`)
  - `agents` (`backend/synapse/agents/*`)
  - `models/model hub` (`backend/synapse/model_hub/*`)
  - `providers` (`backend/synapse/providers/*`)
  - `tools` (`backend/synapse/tools/*`)
  - `permissions` (`backend/synapse/tools/permission_bridge.py`)
  - `embodiment` (`backend/synapse/embodiment/runtime.py`)
  - `perception` / sinais multimodais (`backend/synapse/perception/runtime.py`)
  - `multimodal` (`backend/synapse/multimodal/runtime.py`)
  - `context fusion` (`backend/synapse/context_fusion/runtime.py`)
  - memória persistente (`backend/synapse/memory/store.py`)
- A UI já expõe Voice dentro de Configurações, não como produto principal:
  - `frontend/src/modules/SettingsModule.tsx`
- A UI de chat já tem botão de microfone no composer:
  - `frontend/src/components/chat/ChatComposer.tsx`
- A navegação principal já não expõe Voice como item primário:
  - `frontend/src/app/productNavigation.ts`
  - `frontend/src/workspace/panelRegistry.tsx`

### O que está implementado

- `VoiceRuntime` persiste settings, recordings, sessions e utterances:
  - `voice/settings.yaml`
  - `voice/recordings/*.yaml`
  - `voice/sessions/*.yaml`
  - `voice/utterances/*.yaml`
- `VoiceRuntime` já oferece:
  - settings de voz
  - listagem de devices
  - listagem de providers
  - teste de microfone
  - transcrição de recordings
- `AudioRuntime` já oferece contrato separado para devices/sessions e mocks de STT/TTS.
- `ChatRuntime` já suporta:
  - rota direta de local chat com LM Studio
  - rota com agente
  - persistência de memória factual simples
  - integração com `ContextLoader`
- `ContextLoader` já injeta memória, identidade, histórico, contexto de conversa, delegação e multimodalidade antes da chamada ao LLM.
- `ModelHubRuntime` já separa claramente:
  - modelos configurados
  - modelos instalados em pasta
  - modelos da biblioteca do LM Studio
  - modelos realmente carregados/servíveis via `/v1/models`
- `ModelHubRuntime` já tem rotina de recomendações de LLM baseada em hardware:
  - `backend/synapse/model_hub/recommendations.py`
- `EmbodimentRuntime` já conecta perfil de agente com voz/avatar por capability.
- `ToolRuntime` e `PermissionBridge` já são o ponto de execução e controle de ferramentas.

### O que é placeholder / mock / contrato determinístico

- `AudioRuntime` e parte do fluxo de voz são contratuais/determinísticos; não são um pipeline de áudio contínuo em tempo real.
- `VoiceRuntime` funciona como runtime de coordenação/persistência, não como engine de streaming de áudio.
- Os providers built-in incluem mocks explícitos:
  - `mock_stt`
  - `mock_tts`
  - `mock_voice_analysis`
  - `mock_vision`
  - `mock_face_tracking`
  - `mock_body_tracking`
  - `mock_avatar_renderer`
- O botão de microfone no chat usa captura/transcrição manual no frontend, via APIs do browser quando disponíveis, e não um pipeline nativo contínuo.
- A inferência de sinais não verbais existe como dados e contexto (`perception`, `multimodal`, `context_fusion`), mas não como um “motor emocional” único.

### O que está conectado na UI

- Voice aparece dentro de Settings como seção colapsável.
- Chat possui entrada contextual de microfone no composer.
- O restante da navegação de workspace não trata Voice como workspace primário.

### O que está conectado no backend

- Voice expõe endpoints próprios em `backend/synapse/api/routes.py`:
  - `/voice/settings`
  - `/voice/devices`
  - `/voice/providers`
  - `/voice/recordings`
  - `/audio/mock/transcribe`
  - `/audio/mock/synthesize`
- Chat usa:
  - `/local-chat`
  - `/agents/{agent_id}/local-chat`
  - `/conversations/{conversation_id}/local-chat`
- Model Hub fornece a base para descoberta, disponibilidade e recomendação de modelos.

## 2. Pontos de integração existentes

### Como Voice se conecta hoje

1. `backend/synapse/core/app.py` instancia:
   - `AudioRuntime`
   - `SpeechAdapterRuntime`
   - `VoiceRuntime`
   - `SpeechPipelineRuntime`
   - `EmbodimentRuntime`
   - `MultimodalCommunicationRuntime`
2. `VoiceRuntime` delega provider resolution ao `ProviderRuntime`.
3. `VoiceRuntime` consome dispositivos e providers e persiste seu estado próprio.
4. `frontend/src/modules/SettingsModule.tsx` consome `/voice/*`.
5. `frontend/src/components/chat/ChatComposer.tsx` usa `useVoiceSettings()` para habilitar captura manual de fala.

### Como Chat funciona hoje

- `backend/synapse/chat/runtime.py` é o ponto central do fluxo de chat.
- Para chat local direto, o runtime resolve:
  - policy de `config/local_chat_policy.yaml`
  - defaults do `ModelHubRuntime`
  - provider LM Studio
- Para chat com agente, o runtime usa:
  - `ContextLoader`
  - `AgentRuntime`
  - memória persistente
  - histórico de conversa
- A UI em `frontend/src/modules/ConversationsModule.tsx` mantém o composer contextual no painel da conversa.

### Como Tools funcionam hoje

- `ToolRuntime` executa tools com `PermissionBridge`.
- O catálogo e o log de execução de tools já existem.
- Voice já aparece no ecossistema de tools como operação de domínio, não como produto separado.

### Como Providers funcionam hoje

- `ProviderRuntime` é o registrador de capabilities e provedores.
- `SpeechAdapterRuntime` já é a ponte correta para adaptação de STT/TTS.
- O registry de providers já inclui mocks de voz e um provider local para LLM (`lmstudio_local`).
- Conclusão: Faster-Whisper não precisa virar uma camada totalmente nova; ele encaixa melhor como adapter/provider de speech dentro do ecossistema de `ProviderRuntime`/`SpeechAdapterRuntime`.

### Como Model Hub funciona hoje

- `ModelHubRuntime` já é o contrato de:
  - catálogo
  - modelos live/discovered
  - defaults
  - folders
  - refresh
  - provider testing
  - recomendações
- A distinção entre “library-only”, “installed”, “configured” e “loaded/server-ready” já existe.
- Para STT, o caminho arquitetural mais seguro é reaproveitar o padrão de provider/adapter, não duplicar um “model hub” paralelo para voz.

### Como Settings funciona hoje

- Settings já usa seções colapsáveis.
- Isso torna Voice um ajuste interno plausível dentro de Settings, em vez de uma tela própria.
- O padrão visual e estrutural de Settings já suporta módulos de configuração especializados.

## 3. Riscos de redundância

### O que não devemos criar de novo

- Novo runtime paralelo para voz se o objetivo for apenas STT/manual capture.
- Novo sistema de memória para contexto de voz.
- Novo catálogo de modelos para STT separado do padrão de provider/model hub sem justificativa forte.
- Novo “emotion engine” isolado, porque já existem `perception`, `multimodal` e `context_fusion`.
- Novo bridge de permissões independente de `PermissionBridge`.

### O que deve ser reaproveitado

- `VoiceRuntime` como camada de coordenação e persistência.
- `AudioRuntime` para contrato de device/session/audio.
- `SpeechAdapterRuntime` para adaptação de providers de fala.
- `ProviderRuntime` para registro e resolução de capabilities.
- `ModelHubRuntime` apenas quando a decisão envolver disponibilidade/recomendação de modelos.
- `ContextLoader` e `MemoryStore` para qualquer contexto persistente que precise entrar no prompt.
- `PerceptionRuntime` / `MultimodalCommunicationRuntime` para sinais não verbais.
- `ToolRuntime` + `PermissionBridge` se alguma operação de voz passar a ser uma tool explícita.

### O que já existe com outro nome

- “Embodiment” já cobre parte do conceito de presença/voz/avatar por agente.
- “Perception” já cobre sinais como emoção, engajamento, gestos, silêncio e voz.
- “Context fusion” já cobre a fusão de sinais e contexto read-only.
- “Speech adapter” já é o nome natural para integração de STT/TTS com providers.

## 4. Recomendação de arquitetura

### Onde encaixar Faster-Whisper

Recomendação: encaixar como provider/adapter de fala dentro do ecossistema existente, não como runtime novo de alto nível.

Estrutura sugerida:
- backend:
  - `VoiceRuntime` continua sendo o runtime de domínio/persistência
  - `AudioRuntime` continua sendo o contrato de áudio/dispositivos
  - `SpeechAdapterRuntime` passa a orquestrar STT providers
  - Faster-Whisper entra como implementação de STT provider/adapter
- Se precisar aparecer no catálogo de capacidade, o lugar certo é o `ProviderRuntime`, não o `ModelHubRuntime` primário.

### Onde encaixar metadados de tom/ritmo/pausa/energia da voz

Recomendação: tratar isso como sinais de percepção e contexto multimodal, não como dados do chat puro.

Camada sugerida:
- captura/normalização: `VoiceRuntime` + `AudioRuntime`
- enriquecimento/sinais: `PerceptionRuntime`
- fusão de contexto: `ContextFusionRuntime`
- consumo em agente/chat: `ContextLoader` / `AgentWorker`

### Nome correto sugerido

Se a intenção for STT manual + metadados contextuais:
- usar “Voice Runtime” para domínio/persistência
- usar “Speech Adapter” para engine/provider de STT/TTS
- usar “Perception Signal Runtime” para sinais derivados

Evitar:
- criar um “Voice Hub” paralelo
- criar um “Emotion Hub”
- criar um “Multimodal v2” duplicado

### Onde isso deve ficar na pilha

- `VoiceRuntime`: coordenação de domínio, settings, sessions, recordings, utterances
- `AudioRuntime`: devices e sessão de áudio
- `ProviderRuntime` / `SpeechAdapterRuntime`: escolha e binding de provider
- `ModelHubRuntime`: apenas se houver decisão de LLM/modelo para transcrição/recomendação
- `ToolRuntime`: apenas se a transcrição virar tool explícita
- `PermissionBridge`: gate de execução
- `PerceptionRuntime` / `ContextFusionRuntime`: sinais não verbais

## 5. Plano recomendado

### Próxima etapa mínima

Antes de implementar Faster-Whisper:
1. Definir se o objetivo é só STT manual ou também sinais multimodais derivados.
2. Confirmar se o provider de speech deve ser local-only ou pluggable.
3. Reaproveitar `SpeechAdapterRuntime` como ponto de extensão principal.
4. Reaproveitar `VoiceRuntime` para settings/persistência/coordenação.

### Arquivos prováveis para a próxima etapa

- `backend/synapse/voice/runtime.py`
- `backend/synapse/audio/runtime.py`
- `backend/synapse/providers/runtime.py`
- `backend/synapse/speech_pipeline/runtime.py`
- `backend/synapse/perception/runtime.py`
- `backend/synapse/context_fusion/runtime.py`
- `backend/synapse/chat/runtime.py`
- `frontend/src/components/chat/ChatComposer.tsx`
- `frontend/src/modules/SettingsModule.tsx`
- `backend/synapse/api/routes.py`
- `backend/synapse/core/app.py`

### O que alterar

- Adicionar o provider/adaptador de STT em uma camada já existente.
- Conectar qualquer metadado de voz aos fluxos de percepção/contexto.
- Se necessário, expor apenas o mínimo de UI contextual no chat e em Settings.

### O que evitar

- Não criar um runtime duplicado para voz.
- Não colocar STT dentro de Model Hub sem necessidade real de catálogo/recomendação.
- Não mover lógica de negócio para frontend.
- Não acoplar voz diretamente ao Agent Runtime sem passar por contexto/percepção quando houver metadados derivados.

## Conclusão

O Synapse já possui a fundação correta para voz/comunicação não verbal:

- domínio/persistência: `VoiceRuntime`
- áudio: `AudioRuntime`
- provider/adapters: `ProviderRuntime` + `SpeechAdapterRuntime`
- contexto/memória: `ContextLoader` + `MemoryStore`
- sinais não verbais: `PerceptionRuntime` + `ContextFusionRuntime`
- presença/avatar: `EmbodimentRuntime`
- execução protegida: `ToolRuntime` + `PermissionBridge`

A recomendação é encaixar Faster-Whisper nessa fundação existente, sem criar um subsistema novo.
