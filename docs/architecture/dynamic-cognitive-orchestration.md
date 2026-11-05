# Dynamic Cognitive Orchestration — auditoria e implementação

## Escopo autorizado em 2026-10-25

Perfil: bounded-context-change, por incrementos, com integração transversal autorizada
pelo pedido de execução de todas as fases. Preservar alterações preexistentes e
backups. Sem commit, publicação ou alteração dos dados pessoais. Condição de
conclusão: contratos integrados e gates registrados; limitações não viram sucesso.

## Fase 0 — evidências atuais

| Responsabilidade | Evidência | Reuso e lacuna |
| --- | --- | --- |
| Composição | bootstrap/application.py, features/missions.py, bindings.py | Ports/adapters no composition root; subsistemas limitados não implicam backend pronto |
| MoM | mom/contracts.py, runtime.py, selection.py | conversation já existe; seleção por palavras, opcional, sem contexto recente |
| Chat | chat/runtime.py, routing.py | Caminhos diretos, histórico, memória, ferramentas; escolha MoM atualmente sobrepõe modelo manual |
| Swarm | swarm/runtime.py, strategies.py, interaction.py, request_policy.py | Ativação explícita, estratégias e confirmação persistida; não depende de MoM |
| Recursos | model_providers/synapse_local.py | Pool 1–2 modelos, leases ocupados; não há reserva por Swarm nem orçamento de bytes |
| Planejamento | missions/planner.py, dag.py | DAG, versões, ciclos e dependências; provider não conectado na composição |
| Scheduler | missions/dispatcher.py, workers/scheduler.py | Admissão, capacidades, tentativas; execução síncrona do lote |
| Validação | missions/verification.py, workers/runtime.py | Verificação antes de completed; flags de resultado não provam execução externa |
| Recuperação | missions/recovery.py, attempts.py | Tentativas persistentes, idempotência, backoff e dead letter |
| Governança | missions/runtime.py, project_governance/runtime.py | RFC e ImplementationPlan vinculados; não criar segundo Planner/governança |
| Contexto | workers/execution_adapter.py, bootstrap/features/integration.py | ContextFusion e memória; completar handoff com dependências e critérios |
| JEV | decision/, docs/architecture/jev-decision-provider.md | Não necessário para primeiro router determinístico; não presumir probabilidades calibradas |
| UI | MoMToggle.tsx, MoMSettings.tsx, main.tsx, WorkspacePanel.tsx | MoM e Swarm separados; reutilizar controle MoM para política |

### Dependências e contratos MoM–Swarm

Não há chamada direta Swarm → MoM. Ambos compartilham ModelRouter, providers,
pool local, eventos e infraestrutura de missões/agentes por composição. MoM é
restrito ao Primary; workers mantêm seus modelos. As novas conexões devem usar
ports, sem imports reversos. Controles independentes e confirmação explícita do
Swarm são invariantes. Concorrência NORMAL não autoriza SWARM.

Swarm.start/resume atualmente apenas persistem running; pause/cancel apenas
persistem estado. run utiliza as estratégias existentes e o dispatcher. Não há
garantia atual de múltiplos modelos residentes: isso é uma lacuna comprovada,
não uma funcionalidade a presumir. A proteção será adicionada ao pool e ligada
ao ciclo do Swarm sem substituir estratégias. Recursos desconhecidos deverão
produzir indisponibilidade explícita, nunca orçamento fictício.

### Plano incremental e riscos

1. Fases 1–3: contrato de política, MoM permanente no chat, conversation,
   precedência manual e intenção recente; migração compatível de rotas legadas.
2. Fases 6–7: políticas no pool, reservas por proprietário, transições seguras,
   readback da UI e persistência com revisão. Busy/reserved nunca são evictados.
3. Fases 4–5/8–10: estender Planner/dispatcher/verifier/handoff existentes;
   planos gerados são propostas, não autorização para efeitos externos.
4. Fases 11–12: projeção factual e regressão, incluindo falhas e recuperação.

Arquivos autorizados: os owners acima, adapters de bootstrap, testes específicos
e esta documentação. Snapshot dos fontes candidatos e inventário preexistente em
artifacts/restore-points/dynamic-orchestration. Riscos principais: alterações
preexistentes extensas, migração de configuração, dupla autoridade sobre Swarm,
corridas no pool e escrita concorrente de planos, providers sem unload/residency,
retomada de efeitos externos desconhecidos. Não repetir automaticamente esses
efeitos. O status global NOT READY não muda por conclusão local.

## Validação

Simulações não comprovam capacidade de RAM/VRAM, qualidade ou desempenho de modelos reais.

## Implementação por fase — 27/10/2026

| Fase | Entrega e contrato |
| --- | --- |
| 0 | Auditoria acima, snapshot e preservação das alterações preexistentes |
| 1–2 | MoM permanente no chat do Primary, rota conversation e fallback generalista; seleção manual tem precedência. Texto, streaming e voz convergem no chat existente |
| 3 | Classificação determinística com intenção recente em continuações; saudação inicia conversa. Sem classificador externo obrigatório |
| 4 | Proposta JSON limitada a 32 tarefas, validada pelo DAG e persistida pelo Planner existente. Modelos devem ter rotas configuradas |
| 5 | Admissão serializada, execução concorrente limitada no regime NORMAL, prioridades e dependências; workers ocupados não são readmitidos. Swarm só usa seus membros |
| 6 | Pool existente estendido com reutilização, reservas por proprietário, limites físicos e journal de recuperação. Modelos busy/reserved protegidos |
| 7 | Controle MoM reaproveitado para Responsivo/Econômico, preferência versionada, leitura após salvar; controle Swarm preservado |
| 8 | Validação precede completed; tarefas de código geradas exigem evidência real de ferramenta para tests_passed. Verificação de imagem usa decodificação e integridade |
| 9 | Revisões são propostas versionadas; invalidação transitiva dos resultados afetados. Aceitação rejeita revisão obsoleta, tentativas ativas, missões terminais e reservas Swarm |
| 10 | Handoff inclui objetivo, critérios, dependências, falhas e ferramentas autorizadas; usa ContextFusion existente |
| 11 | Endpoint de recursos e painel mostram política, regime, modelos, reservas e missões; eventos existentes registram decisões e transições |
| 12 | Regressão global, testes de concorrência e falhas, testes de UI e compilação. Evidências em artifacts/reports/dynamic-orchestration-* |

### Migração e operação

`Configuration.enabled` continua desserializável para clientes antigos. O chat
não usa essa flag como interruptor do MoM; a API explícita de operações mantém
seu contrato legado. `resource_policy` ausente assume RESPONSIVE. Os enums
ExecutionRegime e ResourcePolicy são independentes. Trocar a política durante
Swarm afeta apenas recursos livres; não cancela missões nem remove reservas.

Planos gerados e revisões não autorizam efeitos externos. O endpoint
`POST /api/missions/{mission_id}/review-plan` recebe `plan_id` e `expected_revision`,
exige contexto de usuário com permissão de escrita e mantém a governança RFC
na execução. A revisão usa a mesma exclusão mútua da admissão de tarefas.
O objetivo original permanece na missão. As tentativas, backoff, limites e
recuperação pertencem ao mecanismo existente; não há repetição automática de
efeitos cuja execução após interrupção seja desconhecida.

Swarm local exige perfis medidos em `models.resource_profiles`, indexados pelo
nome do modelo, com `ram_bytes` positivo e `vram_bytes` não negativo. Não foram
inventados perfis nem alterados os modelos/configurações reais do usuário.
O limite existente do pool (um ou dois modelos, conforme configuração) continua
valendo: excesso de modelos ou memória falha explicitamente antes da admissão.
Providers sem contrato de residência controlável não recebem uma garantia falsa:
a ativação retorna erro explícito. O provider mock é usado somente nas simulações.

O journal armazena proprietário, modelos, orçamento e identidade dos processos.
Após interrupção, novas cargas ficam bloqueadas até reconciliação. Um registro
incompleto não permite assumir que processos desapareceram. Pausa mantém reservas;
cancelamento espera tentativas ativas e libera apenas seu proprietário. Após
liberação confirmada, o coordenador terminal não bloqueia execução NORMAL futura.

### Evidências e limites

- Baseline inicial: 69 testes aprovados.
- Regressão global antes dos últimos ajustes de integração: 4.638 aprovados,
  5 ignorados, 4 subtests aprovados; uma advertência de depreciação Starlette/httpx.
- Mypy global dessa revisão: 833 arquivos sem erros.
- Frontend: 142 testes aprovados; compilação TypeScript/Vite concluída.
- Electron: cinco seletores, troca/persistência da política, proteção contra
  falha ao salvar, controle Swarm preservado e painel de recursos verificados.
- Rodada final de integração, voz e fronteira do frontend: 110 testes aprovados.
- Regressão final de chat/local chat e orquestração: 71 testes aprovados.
- Arquitetura após os ajustes finais: 274 testes aprovados.
- Mypy final: 833 arquivos sem erros, mais rechecagens dos 10 arquivos de
  integração e do runtime de chat; Ruff do escopo sem erros após ordenar imports.
- Planejamento pelo chat e persistência no caminho local: teste integrado aprovado.
- Sidecar reconstruído: iniciou com diretório temporário e confirmou os 513
  caminhos públicos, incluindo os dois novos contratos. O log desse ambiente vazio
  registra indisponibilidade opcional de repository-runtime por canonical root
  mismatch; o smoke comprova inicialização/API, não prontidão global do repositório.

Não foi executado um Swarm com modelos pesados reais; a prova de residência,
concorrência, falhas e orçamento usa processos/modelos simulados. O hardware real
deve ter perfis medidos antes dessa ativação. A preferência é por workspace, mas
o pool físico é compartilhado: o painel distingue a seleção da política aplicada.
Não há nova tela de aprovação de planos; a revisão está disponível pela API de
missões. O status global do backend continua NOT READY.
