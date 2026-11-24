# Prontidão operacional — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Follow the local AGENTS.md: work directly in the canonical checkout; no worktree is authorized.

**Goal:** Fechar os 34 critérios dos nove grupos com implementação, revisão e evidência; não reclassificar validações limitadas como aceite global.

**Architecture:** O Core permanece o único escritor e autoridade. Evoluções de contratos, manutenção offline protegida, governança de autoalteração e observabilidade integram o proprietário existente. A distribuição empacota os mesmos artefatos e declara compatibilidade; evals e runbooks verificam os caminhos públicos.

**Tech Stack:** Rust nativo/Slint, Python local, SQLite WAL, DPAPI e contenção Windows; sem inferência remota.

**Spec:** `docs/superpowers/plans/2026-11-22-auditoria-prontidao-operacional.md`; `docs/specs/2026-11-06-synapse-0.3-decision-charter.md`.

## Global Constraints

- Preservar alterações locais, dados, evidências e referências históricas; não tocar no disco E.
- Trabalhar em `F:\Projetos\Synapse`; não criar outro checkout.
- API v1 permanece compatível; novas capabilities e schemas são explícitos; worker novo negocia compatibilidade com v4.
- Inferência local: chamadas remotas e seu custo permanecem zero.
- Aprovações e revisão de autoalterações não podem ser emitidas por texto de modelo ou rótulos de agente.
- Não desligar nem reiniciar a máquina de trabalho para simular falha; usar estado/instalação descartáveis e distinguir o que exige ambiente virtual próprio.

## Review Focus

- Banco v15 já contendo extensões: migrar uma vez sem perder preferências, chats, missões ou recibos.
- Backup com WAL e processo em uso: snapshot consistente ou recusa explícita, nunca cópia parcial.
- Limites e métricas desconhecidas: não converter ausência de contador em zero ou estimativa em medição.
- Cliente/worker/pacote anterior: negociar ou recusar de modo explícito; impedir downgrade de banco incompatível.
- Aprovação de projeto apontando para o Synapse: negar efeitos genéricos e exigir fluxo dedicado com diff revisto.

## Tarefas e verificação

### 1. Contratos, migração e manutenção protegida (coordenador)

- [x] Introduzir schema16, manifesto de compatibilidade e registro de migração; testar fixtures v6/v15, idempotência e recusa de versão futura.
- [x] Criar manutenção offline Rust com backup consistente, criptografia DPAPI, restauração em destino novo e verificação de integridade, identidade e versão.
- [x] Proteger arquivos de estado e temporários; testar canários e corrupção/usuário incompatível sem alterar dados de uso.

### 2. Métricas, orçamento e diagnósticos (readiness_observability)

- [x] Negociar worker v5/v4; transportar uso de tokens real quando fornecido sem expor prompts.
- [x] Implementar métricas e orçamento agregado por missão; RAM medida, VRAM disponível ou explicitamente desconhecida, bloqueio de inferência remota.
- [x] Integrar hooks no Core, testar limite, falha, cancelamento, reuso e contadores indisponíveis.

### 3. Autogovernança e isolamento (readiness_governance)

- [x] Fluxo dedicado de proposta, revisão de diff, aprovação humana, publicação e reversão com journal e principal local.
- [x] Impedir missões genéricas de alterar o produto; testar rótulos forjados, contextos divergentes e interrupções.
- [x] Registrar fronteira de um usuário do SO; não presumir servidor autenticado multiusuário.

### 4. Distribuição atual (readiness_distribution)

- [x] Empacotar Slint/Core/workers/runtime Python completo e verificadores; manifesto reprodutível e compatibilidade de estado.
- [x] Validar instalação, atualização, downgrade recusado/rollback compatível e diagnóstico sem GPU/provedor/ferramentas.
- [x] Integrar backup/restauração à operação sem depender de variáveis do terminal de desenvolvimento.

### 5. Evals e campanha de falhas (coordenador após hooks)

- [x] Casos rotulados de roteamento, memória, ferramentas, QA e replanejamento; medir falsos positivos/negativos por classe e guardar baseline versionado.
- [x] Testar limites, concorrência, cancelamento, orfandade e recuperação por comandos reais; executar tarefas locais representativas.
- [ ] Executar ensaios de reinício em ambiente descartável adequado, quando disponível, sem substituir perda de energia por um encerramento limpo. **Não realizado; dispensado pelo usuário em 2026-11-24.**

### 6. Revisão final e entrega

- [x] Revisar alterações e corrigir achados; atualizar arquitetura, contratos, runbooks e gate executável de prontidão.
- [x] Verificar artefato instalado da revisão atual e preencher os 34 critérios somente com a evidência correspondente.


Recibo atual: [software Windows, 2026-11-24](../../evidence/backend/2026-11-24-operational-readiness.md). Os testes de software e o pacote foram validados; o ensaio de reinício foi dispensado pelo usuário por ausência de ambiente Windows descartável e está marcado como não realizado. Nenhuma falta de energia foi simulada no host.


