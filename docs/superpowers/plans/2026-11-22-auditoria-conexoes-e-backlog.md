# Synapse — Auditoria das conexões e sequência de integração

Data de inspeção 2026-11-22. Base Git `1d615b2`, acrescida das alterações locais em desenvolvimento. Este documento registra a inspeção do código e transforma as oito prioridades em tarefas. As tabelas de inspeção preservam a situação inicial. Os 27 itens do checklist foram concluídos no aceite local Windows registrado em [22/11/2026](../../evidence/backend/2026-11-22-integracao-oito-prioridades.md).

## Escopo observado

O workspace atual contém `backend/core`, `backend/desktop` e `backend/desktop-slint`. O cliente Slint está em arquivos novos locais e compartilha componentes com o desktop eframe. O ADR 0004 mantém sua promoção condicionada à integração. Há alterações locais em conversa, registro de modelos e candidatos que também fazem parte desta inspeção.

A release publicada em novembro é evidência de uma revisão anterior. Seu aceite não cobre automaticamente os novos callbacks Slint ou um roteador unificado.

As fontes consultadas foram os contratos Rust v1, o charter 0.3, o ADR 0004 e o código atual. Nenhum arquivo com o nome da proposta V3 de orquestração foi localizado nos caminhos de referência pesquisados. Os comportamentos V3 mencionados na solicitação são requisitos a cruzar com esta implementação.

## 1. Entrada e roteamento

| Caminho atual | Arquivos e símbolos | Resultado da inspeção |
| --- | --- | --- |
| Mensagem escrita no Slint | `backend/desktop-slint/src/session.rs`, `attach_with_model`, callback `on_send_message`, `State::start_turn` | Cria ou reutiliza chat e envia `conversation_start` com modelo escolhido e texto. Não classifica a intenção. |
| Voz comum no Slint | Mesmo arquivo, `State::tick_voice`; `backend/core/src/voice.rs`, `turn` | Envia `voice_turn_start`. Fora de tradução, o Core reutiliza `conversation::start`. |
| Tarefa no Slint | `attach_with_model`, callbacks `on_plan_task`, `on_approve_task`, `on_execute_task` | Registra projeto e usa `mission_plan_start`, aprovação e execução em fluxo explícito distinto. |
| Cliente eframe | `backend/desktop/src/main.rs`, `send_message`, `plan_mission`, `approve_mission` | Mantém entradas distintas para conversa e missão. Oferece contexto, Skill e orçamento de modelo que ainda não aparecem no envio comum do Slint. |
| Entrada no Core | `backend/core/src/contracts.rs`, `Command`; `backend/core/src/core.rs`, `dispatch`, `dispatch_tx` | Contratos separados para conversa, voz, inferência, planejamento e execução. A entrada comum de decisão sobre o tipo de pedido ainda falta. |

O texto de identidade em `conversation::start` manda encaminhar trabalho com arquivos para o controle de tarefas. Uma resposta de conversa não dispara uma missão. A frase “agora deixe mais seguro” pode ter o histórico do chat, mas não recebe automaticamente um vínculo com a missão e seus artefatos.

## 2. MoM, Swarm e recursos

| Componente existente | Arquivos e símbolos | Limite atual |
| --- | --- | --- |
| Escolha por capacidade e orçamento | `backend/core/src/registry.rs`, `resolve_chat_model`, `model_route`, `select_model` | Seleciona o menor `memory_bytes` cadastrado compatível. Essa medida é declarada no manifesto e não equivale a uma medição da memória livre ou de pico. |
| Escolha explícita | `resolve_chat_model`; `Command::ConversationStart`, `Command::MissionPlanStart` | O Core aceita ID explícito ou orçamento automático. Receber os dois resulta em erro. A precedência manual precisa ser resolvida pelo novo fluxo antes do despacho. |
| Manifestos e capacidades | `registry::model_register`, `models_list`, `capabilities`; `conversation::registered_model` | Há catálogo e diagnóstico. Planejamento e conversa validam modelos locais com capacidade `chat`. A lista de capacidades do produto ainda não é um registro executável de especialistas. |
| Residência dos modelos | `backend/python/synapse_ai/providers.py`, `model_instance`, `_cli_model_instance`, `_release_model` | Instância existente é reutilizada. Instância criada pelo worker é liberada no encerramento. Outro modelo residente impede nova carga. O gerenciamento depende de `SYNAPSE_MANAGE_LOCAL_MODELS`. |
| Ocupação e cancelamento | `backend/core/src/core.rs`, `active`, `launch`, `drain`; `backend/core/src/worker.rs`, `Stop` | Uma inferência ativa por Core. Aprendizado tem tratamento de prioridade. Cancelamento gerenciado dá oportunidade de liberar o modelo. |
| Swarm | `planner::get`; `Command::MissionApprove`; `mission_run::swarm_consent`, `start`, `get`, `advance` | Recomendação e consentimento são vinculados à missão. Implementação e verificação são dois papéis temporários sequenciais sobre os modelos primário e revisor. |
| Publicação | `backend/core/src/integration.rs`, `advance`, `reserve_conflict`, `publish_one`, `postcheck`, `rollback_one` | Existem reservas de efeitos em arquivos e recibos de publicação. Seu escopo difere da reserva de memória e residência de modelos. |

Não há campos de contrato `execution_regime` e `resource_policy`, nem as quatro opções NORMAL, SWARM, RESPONSIVE e ECONOMICAL implementadas como eixos de estado. Também não foi encontrado um livro de reservas de modelos compartilhado entre Cores. O bloqueio de ocupação e o ciclo atual de instâncias devem ser preservados ao acrescentar essa coordenação.

O cliente eframe expõe recomendação, aceite e papéis do Swarm. O Slint aprova a missão sem enviar o campo `swarm` e ainda não oferece a mesma transição.

## 3. Conversa, contexto e memória

`backend/core/src/conversation.rs`, `start`, monta mensagens com identidade, idioma, Skill, referências e histórico do chat. `context::select` lê referências explícitas `(scope, key)`, fixa revisão e digest e limita a seleção. `context::finalize` valida tamanho, quantidade e blocos de sistema. Há rejeição de contexto acima do limite, sem compactação automática de conversas longas.

`backend/core/src/learning.rs`, `start`, `complete`, `requeue`, já extrai e versiona memória com validação de origem e tratamento de conflitos. `memory::latest_active` oferece recuperação da revisão ativa. A existência desses mecanismos não comprova relevância semântica para qualquer novo pedido.

O Slint envia a conversa sem `context` e sem `skill`. Suas atribuições `assigned_models` e a seleção atual ficam no estado da sessão. O planejamento recebe um objetivo, mas o callback atual não envia histórico, referências ou o chat de origem. O Core deliberadamente exclui o histórico bruto do planejamento.

O contrato de memória já aprovado continua aplicável. A seleção automática de relevância deve ocorrer dentro das referências autorizadas pelo usuário. Mencionar um projeto pode resolver uma referência que precisa ter identidade verificável; similaridade textual, sozinha, não concede acesso a outros projetos.

## 4. Planejamento e execução

O fluxo encontrado é `planner::start` → `planner::complete` → proposta de missão selada → `missions::approve` → `mission_run::start` → geração → checks → revisão → `integration::advance` → publicação → pós-checks ou rollback.

`MissionPlan` contém `summary`, `artifacts` e `checks`. `MissionExecutionSpec` fixa modelos, limites, artefatos e verificações. Ainda não contém um grafo de tarefas com dependências, prioridades e aceites por tarefa. O avanço existente coordena etapas sequenciais de uma missão.

RFC aparece na documentação de engenharia, mas não foi localizado como entidade executável com ID, estado e vínculo à missão nos contratos atuais. Portanto, RFC → Plan → Mission ainda exige uma conexão explícita se essa governança precisar existir no produto.

Cancelamento, revogação, interrupção e recuperação de efeitos já existem em `missions`, `mission_run`, `mission_recovery` e `integration::resolve`. Não há comandos gerais `MissionPause` e `MissionResume`. Retomar uma publicação interrompida e continuar uma missão pausada precisam de semânticas próprias.

## 5. Validação, ferramentas e interface

`tools::authorize` e `tools::prepare` limitam ferramentas ao contrato aprovado. `candidate::validate_artifacts`, `parse_generation` e `parse_review` verificam candidatos e revisão. `mission_run::valid_check` confere recibos antes de avançar. `CheckKind` cobre receitas Rust, Python e formatos como JSON, TOML, CSV, SVG, Markdown e WebVTT. Imagens têm análise isolada própria no navegador, mas não há um aceite genérico de criação de imagens integrado a um grafo de tarefas.

Um check inválido encerra a execução correspondente como falha. Ainda falta a etapa governada que decide entre revisão, nova tentativa e replanejamento, preservando escopo, limites e os efeitos já confirmados.

O Slint já consulta catálogo, capacidades, chats, eventos e missão. Atribui modelos a conversa, tarefas e revisão. Atribuição de tradução aparece indisponível. `State::receive` deriva botões de aprovação e execução das respostas do Core, e `task_request` guarda o último comando para aguardar ocupação transitória. Preferências de roteamento e dos dois eixos não têm persistência encontrada no esquema atual.

Eventos e recibos já relacionam jobs a chats, contratos, checks e publicações. Falta uma correlação única de ponta a ponta que registre a decisão de rota e todos os handoffs derivados da mesma entrada.

## Backlog executável

Os nomes de comandos e tipos novos abaixo são propostas de implementação. Os símbolos descritos nas seções anteriores já existem no checkout inspecionado.

### A. Entrada única com conversa simples como primeiro aceite

Arquivos envolvidos — `contracts.rs`, `core.rs`, `conversation.rs`, `voice.rs`, `desktop-slint/src/session.rs`, `desktop/src/main.rs`.

- [x] Introduzir `InputSubmit` e um registro de entrada persistido, com texto, origem, chat, referência de continuidade e escolha de modelo explícita ou automática. Reutilizar a idempotência do Core.
- [x] Definir `RouteDecision` com destino conversa, capacidade especializada ou proposta de missão, justificativa e vínculos. Validar a decisão antes de iniciar trabalho ou pedir aprovação.
- [x] Encaminhar texto e voz comum ao mesmo despacho. Preservar a semântica do modo tradutor ativo, inclusive sua parada, antes da classificação de tarefas.
- [x] Reutilizar `conversation::start` para o caminho de diálogo, sem planejamento, Swarm ou inferência adicional de classificação obrigatória para toda saudação.
- [x] Validar “oi”, pergunta comum, tradução ativa e reenvio da mesma entrada. Conferir no provedor e nos eventos a ausência de planejamento e duplicação de efeito.

### B. Capacidade especializada e continuidade

Dependência — A.

Arquivos envolvidos — `registry.rs`, `context.rs`, `planner.rs`, `conversation.rs`, callbacks e modelos do Slint.

- [x] Definir o descritor executável de capacidade, seus modelos compatíveis, ferramentas necessárias e condições de disponibilidade. Reutilizar os manifestos e o catálogo existentes.
- [x] Fixar a seleção manual quando compatível. Diante de incompatibilidade ou indisponibilidade, devolver estado explícito antes de qualquer troca. A seleção automática opera apenas quando esse modo estiver escolhido.
- [x] Resolver o assunto recente a partir do chat e do vínculo de missão ou artefato. “Agora deixe mais seguro” deve apontar ao resultado anterior verificável ou pedir a identificação que falta.
- [x] Criar uma projeção de handoff com objetivo, restrições, referências autorizadas, resultados e recibos. Fixar revisão e digest. Preservar o histórico e a memória nos respectivos registros.
- [x] Ligar seleção de Skill e contexto no Slint aos campos que o Core já aceita. Selecionar relevância dentro do escopo autorizado e mostrar as referências efetivamente usadas.
- [x] Testar troca de modelo no mesmo chat, continuação após uma missão, referência ambígua, projeto homônimo e memória de outro projeto. Reaproveitar os testes de contexto explícito e limites.

### C. Dois eixos e ciclo de vida dos modelos

Dependências — A e mapeamento desta auditoria. B é necessário para o aceite de especialista.

Arquivos envolvidos — `contracts.rs`, `store.rs`, `registry.rs`, `core.rs`, `worker.rs`, `providers.py`, `missions.rs`, `mission_run.rs`, cliente Slint.

- [x] Acrescentar estado persistido distinto para regime NORMAL/SWARM e política RESPONSIVE/ECONOMICAL. Migração deve atribuir um estado compatível aos registros antigos e exigir confirmação para novo Swarm.
- [x] Reutilizar consentimento de Swarm vinculado ao contrato, os papéis, seus recibos e encerramento. O agendador de recursos atende ambos os regimes.
- [x] Registrar reservas de modelos por proprietário e trabalho, com solicitação, aquisição, liberação e reconciliação. A capacidade de máquina e o pico estimado devem ser distintos do tamanho do modelo em disco.
- [x] Consultar a disponibilidade real do provedor e impedir descarga de instância em uso ou reservada. Preservar instâncias alheias. Definir recuperação de carga e descarga com resultado incerto.
- [x] Modelar transições solicitada, em preparação, ativa, falhou e encerrada. A interface confirma o Swarm e só indica ativação após a resposta autoritativa.
- [x] Testar as quatro combinações, duas solicitações concorrentes, instância já carregada pelo usuário, falha parcial de carga, cancelamento e morte do Core. Verificar reservas e residência depois do encerramento.

### D. Missão com tarefas e aceites

Dependências — B e C.

Arquivos envolvidos — `planner.rs`, `contracts.rs`, `missions.rs`, `mission_run.rs`, `checks.rs`, `candidate.rs`, `integration.rs`, `mission_recovery.rs`.

- [x] Ligar o pedido e a conversa à proposta. Se RFC for entidade do produto, definir seu contrato e a revisão que o plano referencia antes de selar a missão.
- [x] Estender o plano com IDs de tarefas, dependências, entradas, entregas, aceites e custos. Converter planos antigos no fluxo sequencial que já executam.
- [x] Executar apenas tarefas prontas cujas dependências passaram, respeitando recursos e prioridade. Publicação e rollback continuam usando o broker e o journal existentes.
- [x] Definir pausa, retomada e recuperação de tarefa em andamento. Preservar o estado e reconciliar efeitos antes de qualquer repetição após interrupção.
- [x] Usar checks por tipo de resultado e revisão apoiada em recibos. Resultado reprovado bloqueia dependentes. Replanejamento que altera efeitos ou limites exige atualização do contrato aprovado.
- [x] Testar uma missão com dependências, check falso ou obsoleto, falha de tarefa, publicação parcial e retomada. Verificar o resultado no Workspace real e nos recibos.

### E. Interface, preferências e observabilidade

Depende de A para o primeiro incremento. Acompanhar B, C e D conforme cada contrato for introduzido.

Arquivos envolvidos — `store.rs`, `contracts.rs`, `core.rs`, `desktop-slint/src/session.rs`, `desktop-slint/ui/app.slint`, transporte e testes dos clientes.

- [x] Persistir modo automático/manual e atribuições de modelo, além dos dois eixos. Preferência persistida deve ser revalidada contra o catálogo ao reconectar.
- [x] Mostrar rota, capacidade, modelo atendente, missão e tarefa vinculadas, pedidos de confirmação e falhas. Derivar os estados ativos das respostas do Core.
- [x] Registrar entrada, decisão, handoff e transições com correlação a chat, missão, tarefa e job. Proteger segredos e conteúdo que não seja necessário aos eventos.
- [x] Automatizar o fluxo pelos callbacks reais do Slint, Core e worker. Conferir concordância entre interface, banco, provedor e arquivos. Testar também os comandos antigos usados pelo eframe e pela ponte.

## Cobertura encontrada e evidência necessária

| Área | Testes existentes a preservar | Complemento para o novo aceite |
| --- | --- | --- |
| Conversa e recuperação | `ai_cli.rs`, `conversation_fixture_persists_once_and_replays_across_restart`, `restart_interrupts_running_job_without_duplicating_user_message` | Entrada única sem planejamento indevido e decisão persistida. |
| Contexto | `ai_cli.rs`, `explicit_context_reaches_provider_pins_latest_and_keeps_learning_source_only`, `context_finalization_preserves_later_history_system_roles_and_order` | Continuação ligada à missão e projeção entre modelos. |
| Planejamento | `mission_cli.rs`, `structured_plan_proposes_without_effects_and_survives_restart`, `foreground_planning_preempts_learning_and_excludes_chat_history` | Tarefas dependentes e continuidade sem ampliar autoridade. |
| Modelo e ocupação | `test_worker.py`, `test_capacity_busy_preserves_existing_model`, `test_reuses_operator_instance_without_unloading_it`, `test_releases_owned_instance_after_failure` | Reservas persistidas, dois eixos e concorrência entre proprietários. |
| Execução e publicação | `project_check_cli.rs`, `mission_run_integrates_only_verified_owned_candidate`, `mission_recovery_resolves_only_verified_effects` | Falha entre tarefas, retomada e replanejamento autorizado. |
| Slint | `src/main.rs`, `core_pipe_workspace_library_and_conversation`; `src/session.rs`, `core_slots_drive_cards_and_task_model_choices` | Envio único, handoff especializado, confirmação de Swarm e restauração de preferências. |

Esta auditoria é estática, acrescida de 17 testes Python de protocolo e ciclo de vida aprovados com `py -3.14 -m unittest discover -s backend/python/tests -p test_worker.py` em 2026-11-22. Os nomes de testes encontrados comprovam a existência da cobertura; sua listagem não certifica a execução completa das integrações propostas. Esse era o estado da auditoria inicial; o aceite posterior implementou e observou os cenários A a E nos caminhos reais de entrada.

## Ordem de entrega

1. A com conversa simples funcionando pelo novo caminho e clientes antigos preservados.
2. B com uma capacidade especializada e continuidade verificável.
3. C com NORMAL/SWARM independente de RESPONSIVE/ECONOMICAL e falhas de ciclo de vida verificadas.
4. D com missão de várias tarefas, QA, publicação e recuperação.
5. E acompanha os incrementos e fecha o aceite ponta a ponta.

O primeiro incremento de implementação é A. Seus critérios permitem verificar uma mensagem do usuário desde o callback até a resposta e o registro da decisão antes de ampliar o comportamento para especialistas e missões.

## Fechamento do checklist

A–E concluídos: 27/27 itens. [Evidência Windows, matriz das oito prioridades e hashes dos executáveis](../../evidence/backend/2026-11-22-integracao-oito-prioridades.md). O aceite identifica a base Git e as fontes da árvore de trabalho, incluindo a ligação dos callbacks Slint ao Core e os gates com modelo local.
