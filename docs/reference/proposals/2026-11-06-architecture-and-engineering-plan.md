Synapse 0.3 — Projeto Arquitetural e Plano de Engenharia

Estado: proposta de arquitetura e execução; não representa auditoria do código.
Data: 2026-11-06
Workspace canônico informado: F:\Projetos\Synapse
Objetivo: transformar componentes existentes em um sistema integrado, observável, reproduzível e comprovadamente funcional.

1. Princípios e limites

Preservar antes de alterar. Registrar no GitHub privado um marco pre-v0.3, validar a recuperação e continuar na branch develop/0.3. Não excluir cópias locais nesta fase.

Evidência antes de refatoração. O inventário e a auditoria precedem a escolha da arquitetura-alvo definitiva. A proposta deste documento é uma hipótese de trabalho.

Um responsável por decisão. Evitar que Router, Planner, Scheduler, agentes e Swarm disputem autoridade sobre a mesma transição.

Contratos explícitos. Comunicação entre bounded contexts por ports/contratos e adaptadores no bootstrap, preservando as convenções comprovadas do projeto.

Skills como procedimentos, não como autorização. Ferramentas executam ações; gates avaliam evidências; as permissões permanecem no runtime ou na infraestrutura responsável.

Local-first com controle de recursos. Modelos residentes, concorrência, memória e VRAM precisam de orçamento e observabilidade.

Status por capacidade. IMPLEMENTED, INTEGRATED, TESTED, VALIDATED e OPERATIONAL são estados diferentes. READY global não substitui a matriz granular.

Documentação viva. Toda mudança deve manter sincronizados código, contratos, diagramas, testes, procedimentos e evidências.

Autoevolução futura, não escopo de ativação 0.3. Nenhuma modificação do próprio runtime sem autorização explícita, execução isolada e aprovação posterior de aplicação.

2. Arquitetura-alvo conceitual

flowchart TD
    UI["Electron / React UI"] --> IPC["Canal autenticado / IPC"]
    IPC --> CONV["Conversation Runtime"]
    CONV --> CTX["Context Resolver"]
    CTX --> ROUTER["Router"]
    ROUTER -->|"simples"| AGENT["Agent Runtime"]
    ROUTER -->|"complexa"| PLANNER["Planner"]
    PLANNER --> SCHED["Scheduler"]
    SCHED --> AGENT
    SCHED --> SWARM["Swarm Execution State"]
    SWARM --> AGENT
    AGENT --> MODELS["Model Runtime Manager"]
    AGENT --> SKILLS["Skill Registry / Loader"]
    AGENT --> BROKER["Tool Broker / Authorization"]
    BROKER --> ADAPTERS["System / MCP Adapters"]
    AGENT --> MEMORY["Memory / RAG Ports"]

Fluxos transversais: segurança aplica decisões no broker e nos boundaries; telemetria registra eventos e correlações; Private Evals consome evidências e mede regressões. A posição exata desses serviços será decidida após a análise dos contratos reais.

Responsabilidades e fronteiras propostas

Componente

Responsabilidade única

Não deve assumir

Conversation Runtime

Estado de conversa, streaming, reconexão, falhas

Decidir ferramenta ou provider diretamente

Context Resolver

Selecionar memória e contexto relevantes por tópico

Armazenar indiscriminadamente todo o histórico no prompt

Router

Selecionar caminho de execução e modelo/política

Planejar passos complexos ou executar tarefas

Planner

Definir plano, dependências e critérios de aceitação

Agendar recursos concretos

Scheduler

Enfileirar e coordenar a execução, limites e cancelamento

Escolher semanticamente objetivos do usuário

Model Runtime Manager

Gerenciar providers, sessões e recursos RAM/VRAM

Determinar permissões de ferramentas

Swarm

Estado de execução com múltiplos modelos carregados simultaneamente

Ser sinônimo genérico de colaboração entre agentes

Agent Runtime

Ciclo de decisão, chamadas e síntese de resultados

Contornar o Tool Broker

Tool Broker

Registro, descoberta, autorização, execução e retorno

Delegar enforcement de segurança apenas ao prompt

Skill Registry

Disponibilizar skills contextualizadas, versionadas

Conceder novas permissões automaticamente

Memory / RAG

Persistir, recuperar, consolidar e projetar fatos canônicos

Reenviar todos os contextos em toda conversa

Evals / Observability

Evidência, métricas, traces e regressão

Declarar aprovação sem execução representativa

Decisões de produto preservadas como requisitos a validar

MoM como caminho habitual de conversa, se confirmado no código e nas decisões atuais.

Alternância econômico / responsivo como política de carregamento/latência; não confundir com ativar/desativar Swarm.

Swarm é um estado distinto de múltiplos modelos residentes, sujeito a recursos e política de concorrência.

Skills herdadas da arquitetura inspirada no Hermes Agent precisam de compatibilidade, evolução supervisionada e contratos verificáveis.

Contextos como #001 pessoal, #002 smart home, #003 projeto, #004 jogo são exemplos de roteamento contextual; taxonomia definitiva depende da auditoria.

Voice lida com STT/TTS, turn-taking, interrupções e eventos; Perception trata entradas perceptivas; a presença visual é um visualizador de frontend, não um bounded context Avatar.

3. Arquitetura de qualidade e rastreabilidade

Cada capacidade deve ter um ID estável e um registro ligando:

Requisito → contrato → implementação → integração → teste → evidência → documentação → status

Estados

Estado

Critério mínimo

IMPLEMENTED

Código da capacidade encontrado e identificado

INTEGRATED

Chamadores, registro, bootstrap e dependências comprovados

TESTED

Testes relevantes executados e resultados anexados

VALIDATED

Comportamento esperado observado em ambiente apropriado

OPERATIONAL

Fluxo ponta a ponta aprovado, incluindo falhas importantes e regressão

Resultados permitidos: PASS, FAIL, BLOCKED, NOT RUN. Mocks e testes unitários não comprovam comportamento real. Um resultado que não foi executado nunca é PASS.

Dois gates complementares

Engineering Gate: contratos, análise estática, testes unitários e integração relevante, segurança e revisão do código.

Operational Gate: execução real pelo caminho de usuário, ambiente representativo, evidências, recuperação de falhas e regressões.

Cada teste deve registrar ID, finalidade, ambiente, pré-requisitos, fixture, versão/commit, comando, resultado esperado, resultado observado, logs/traces/screenshot quando aplicável, duração, classificação e limitações. O revisor confere que a evidência prova especificamente a alegação.

4. Catálogo de skills candidatas

Status: candidatas para auditoria, não aprovadas nem instaladas. Ler SKILL.md, referências e scripts; verificar licença, commit, dependências, permissões, compatibilidade com Codex Windows, conflitos com AGENTS.md e execução piloto antes de aprovar.

Skill

Fonte

Uso previsto

codebase-context

dtsong/agentic-council

Inventário e contexto arquitetural read-only

sift-codebase-audit

2389-research/sift

Auditoria complementar de estados, concorrência e boundaries

systematic-debugging

obra/superpowers

Reprodução e rastreamento de causa raiz

writing-plans

obra/superpowers

Decomposição após RFC aprovada; adaptar ao RFC→Plan→Mission existente

fastapi-python

mindrally/skills

Backend Python/FastAPI, se adequado à arquitetura real

electron-dev

jamditis/claude-skills-journalism

Electron/React/TypeScript; conferir compatibilidade

mcp-builder

anthropics/skills

Contratos e teste de ferramentas MCP; não assumir que todo adapter é MCP

multi-agent-orchestration

composio-community/opencode-skills

Padrões de decomposição; não equivale ao Swarm do runtime

agent-memory

quegenx/agent-skills

Referência de memória; não substituir política canônica sem benchmark

rag-eval

nvidia/skills

Avaliação de retrieval/generation, condicionado às dependências

agent-evaluation

mlflow/skills

Benchmarks de comportamento de agentes, condicionado a MLflow

test-driven-development

obra/superpowers

Testes negativos antes de correções

webapp-testing

anthropics/skills

QA de interface web

playwright-interactive

openai/skills (legado)

E2E de Electron com ambiente e permissões apropriados

verification-before-completion

obra/superpowers

Evidência antes de declaração de sucesso

security-threat-model

openai/skills (legado)

Modelagem de ameaças enraizada no código; buscar versão atual

python-observability

wshobson/agents

Logs, métricas, tracing e correlação

technical-writing

mindrally/skills

Procedimentos reproduzíveis, documentação técnica

Não instalar todas indiscriminadamente. O AGENTS.md atua como índice curto de regras e roteamento; o corpo das skills continua em arquivos próprios. Nenhuma skill de terceiros modifica seus próprios gates na missão em que é avaliada.

5. Fases e skills por fase

0.3.0 — Preservation & Engineering Tooling

Objetivo: preservar a versão anterior no GitHub privado, configurar skills e governança documental.

Skills: codebase-context para reconhecimento, verification-before-completion como padrão de evidência após aprovação, technical-writing para procedimentos, security-threat-model somente quando efetivamente conduzida uma análise AppSec.

Ações: tag anotada pre-v0.3, branch develop/0.3, comparação do clone remoto, inventário de dados ignorados, auditoria das skills e revisão pontual de AGENTS.md/.agent.

Entregáveis: baseline recuperável, matriz de skills, catálogo versionado, plano de documentação, roteiro de inventário.

Gate: push confirmado, integridade verificável, skills aprovadas por revisão e piloto; nenhuma exclusão local.

0.3.1 — Full System Inventory (AS-IS)

Objetivo: listar todas as funcionalidades reais, serviços, ferramentas, contratos e consumidores do repositório.

Skills: codebase-context, opcional sift-codebase-audit, technical-writing.

Ações: varredura do código, manifesto de módulos, entrypoints, bootstraps, events, tool registry, UI→runtime, testes e documentação; rastreabilidade por arquivos e símbolos.

Entregáveis: catálogo global, diagramas AS-IS, matriz de dependências, lista de TODO/stubs, cobertura documental.

Gate: todos os pacotes analisados; sem lacunas ocultas, UNKNOWN explícito onde não comprovado.

0.3.2 — Integration Audit & Failure Baseline

Objetivo: reproduzir falhas de Tools, Swarm, Memory, Models, Skills e fluxo de conversa.

Skills: systematic-debugging, mcp-builder para ferramentas aplicáveis, playwright-interactive/webapp-testing para UI, agent-evaluation, python-observability, verification-before-completion.

Ações: construir testes de baseline; capturar traces/correlation IDs; distinguir falha do provider, gateway, wiring, estado e autorização.

Entregáveis: matriz de integração e falhas, reproduções mínimas, causas comprovadas ou hipóteses, ranking por impacto.

Gate: defeitos prioritários reproduzidos, ou classificados BLOCKED com justificativa; nenhuma correção oportunista nesta fase.

0.3.3 — Target Architecture & Migration RFCs

Objetivo: confirmar/refinar a arquitetura-alvo com base no AS-IS e falhas.

Skills: writing-plans adaptada, codebase-context, security-threat-model, technical-writing.

Ações: ADRs, contratos de Router/Planner/Scheduler/Swarm, política de modelos e skills, migrações incrementais, testes de aceitação definidos antes do código.

Entregáveis: RFCs, arquitetura TO-BE, contratos, diagrama de eventos/estados, plano por slices e rollback.

Gate: decisões críticas aprovadas pelo usuário; nenhuma reescrita total sem prova de necessidade.

0.3.4 — Foundation, Bootstrap, Security & Tool Execution

Objetivo: restaurar um fluxo mínimo e seguro de solicitação → agente → ferramenta → resposta.

Skills: fastapi-python, mcp-builder, systematic-debugging, test-driven-development, verification-before-completion.

Ações: corrigir composition roots, tool discovery, autorização, protocolos e resultado; instrumentar correlação ponta a ponta. Distinguir ferramentas nativas de servidores MCP.

Entregáveis: fluxo real de consulta local, eventos e erros reproduzíveis, documentação de cada ferramenta.

Gate: teste com ferramenta real, saída independente de controle, permissão negada, falha e timeout; nenhum retorno inventado pela LLM.

0.3.5 — Model Runtime, Router, Planner & Scheduler

Objetivo: separar decisões semânticas, planos, filas e recursos de inferência.

Skills: systematic-debugging, agent-evaluation, test-driven-development, python-observability, writing-plans quando houver mudança de escopo.

Ações: contrato de carregamento de modelos, policy econômico/responsivo, rotas simples/complexas, cancelamento, retry, budgets e falhas de provider.

Entregáveis: matriz de políticas, estados, benchmark de latência/custo/recursos, testes de regressão.

Gate: execução real no hardware de destino; fallback, cancelamento e escassez de recursos comprovados.

0.3.6 — Agents, Skills, Memory & RAG

Objetivo: garantir que agentes recebam as ferramentas/skills/contextos certos e persistam fatos corretamente.

Skills: mcp-builder onde aplicável, agent-memory como referência, rag-eval, agent-evaluation, systematic-debugging, test-driven-development.

Ações: unificar contratos de descoberta, permissionamento e skill lifecycle sem quebrar evolução herdada; memória canônica por tópico, retrieval seletivo, testes de contaminação entre contextos.

Entregáveis: catálogos, contratos, políticas de memória, benchmarks RAG, documentação completa.

Gate: gravar/recuperar/esquecer/atualizar fatos no cenário correto, com isolamento, evidência de chamadas e ausência de vazamento entre contextos.

0.3.7 — Swarm & Multi-Model Coordination

Objetivo: restabelecer Swarm como estado operacional distinto com múltiplos modelos residentes.

Skills: systematic-debugging, agent-evaluation, python-observability, test-driven-development; multi-agent-orchestration apenas como fonte comparativa.

Ações: máquina de estados, ownership, recursos RAM/VRAM, pool residente, fan-out controlado, sincronização, validação entre etapas, cancelamento, degradação e encerramento.

Entregáveis: contrato do Swarm, casos de teste multi-modelo, medições de recursos, logs por execução, documentação.

Gate: dois ou mais modelos realmente carregados simultaneamente quando o hardware permitir; comprovar concorrência/coordenação. Se indisponível, BLOCKED, nunca PASS por mocks.

0.3.8 — Frontend, Conversation & Perception Integration

Objetivo: integrar estados e capacidades reais à interface Electron/React, incluindo handshake, streaming, reconexão, erros e percepção/voz existentes.

Skills: electron-dev, playwright-interactive, webapp-testing, systematic-debugging, verification-before-completion.

Ações: contratos IPC, bootstrap, estado de conversa, controles econômico/responsivo, Swarm, log/transcrição, visualizador de voz, segurança de transporte.

Entregáveis: mapas de tela→runtime, casos de interação, screenshots e traces; documentação de operação.

Gate: executar o app real em Windows; inspeção visual e funcional, incluindo falhas e estados transitórios. Voice/Perception requer teste real específico, não apenas UI.

0.3.9 — System E2E, Regression, Packaging & Documentation

Objetivo: validar integração total e reconstrução a partir do zero.

Skills: verification-before-completion, playwright-interactive, webapp-testing, agent-evaluation, rag-eval, security-threat-model, technical-writing.

Ações: testes ponta a ponta, regressão, falhas de recursos, segurança, build Windows, clean clone, configuração, execução e SYNAPSE_FROM_ZERO.md reproduzido.

Entregáveis: evidências assinadas por versão/ambiente, matriz de funcionalidades, manual integral, release candidate.

Gate: fluxos críticos OPERATIONAL; riscos residuals explicitados; sem declarar READY global com blockers críticos.

0.3.10 — Release Acceptance & Handoff

Objetivo: obter aprovação final do usuário para promover a versão.

Skills: verification-before-completion, technical-writing, revisão de segurança apropriada.

Ações: comparar requisitos com evidências, consolidar ADRs e changelog, validar rollback, demonstrar fluxos, preparar release.

Entregáveis: acceptance report, documentação final, release notes e matriz residual.

Gate: aprovação explícita do usuário, critérios cumpridos e restauração disponível.

6. Matriz de testes prioritários

ID

Fluxo real

Evidência mínima

TOOL-E2E-001

Usuário solicita processos do Windows

Tool call autorizado, resultado OS e comparação independente

TOOL-SEC-002

Usuário nega permissão

Não execução, erro observável, nenhuma escalada

MODEL-001

Carregar e utilizar provider/modelo

Identidade, tempo, sessão e resultado reais

ROUTER-001

Chat simples via MoM

Rota e provider usados, tokens e latência

PLAN-001

Tarefa composta

Plano, ordem de execução, validadores e resultado

SWARM-001

Dois modelos residentes

Prova de dois processos/sessões residentes, RAM/VRAM e coordenação

SWARM-002

Falha/cancelamento de modelo

Encerramento correto, liberação de recursos, resultado consistente

MEM-001

Persistir e recuperar fato canônico

Consulta de armazenamento e uso contextual correto

MEM-002

Isolamento de tópicos

Dados de contexto não pertinente não injetados

SKILL-001

Descobrir e usar skill

Registro, carregamento, execução e retorno observados

UI-001

Electron → backend → agente → UI

Eventos correlacionados e resposta visível

UI-002

Falha/reconexão

Máquina de estados e recuperação reais

BUILD-001

Clone limpo até executável Windows

Logs completos, dependências, binário e lançamento

REG-001

Regressão transversal

Suíte relevante executada no commit e ambiente especificados

7. Documentação integral — fonte de verdade

Estrutura orientativa (preservar documentação preexistente válida):

docs/
  00-project/       vision, requirements, history, roadmap
  01-architecture/  as-is, to-be, bounded-contexts, ADRs, contracts
  02-subsystems/    ficha técnica de cada contexto e capacidade
  03-apis-tools/    catálogo de endpoints, ferramentas e permissões
  04-development/   environment, configuration, SYNAPSE_FROM_ZERO
  05-testing/       strategy, catalog, procedures, regression, evidence
  06-operations/    deployment, packaging, rollback, restore
  07-version-0.3/   inventory, audit, RFCs, migration, release-acceptance

Cada ficha relevante: propósito, status real, código/símbolos, contrato, inputs/outputs, consumidores, inicialização, estados, dependências, permissões, erros, eventos, casos de teste, evidências e limitações. Para histórico de criação, registrar somente fatos sustentados por commits, documentos e registros disponíveis; lacunas históricas permanecem declaradas.

Definição de documentação pronta: alguém com acesso autorizado e ambiente compatível consegue seguir o manual para reproduzir o resultado; se não for executado de fato, o procedimento fica como NOT VALIDATED.

8. Dependências e critérios de passagem

flowchart TD
    P0["0.3.0 Preservação e skills"] --> P1["0.3.1 Inventário AS-IS"]
    P1 --> P2["0.3.2 Auditoria e baseline"]
    P2 --> P3["0.3.3 Arquitetura e RFCs"]
    P3 --> P4["0.3.4 Runtime / Tools"]
    P4 --> P5["0.3.5 Models / Router"]
    P5 --> P6["0.3.6 Agents / Memory / Skills"]
    P6 --> P7["0.3.7 Swarm"]
    P7 --> P8["0.3.8 Integração UI / Voice"]
    P8 --> P9["0.3.9 E2E / Build / Docs"]
    P9 --> P10["0.3.10 Aceite"]

A ordem representa gates de integração, não uma proibição de testes ou documentação durante fases anteriores. Correções e testes de interface podem ocorrer antes da fase 0.3.8 quando necessários para validar um slice. Dependências descobertas na auditoria podem alterar a sequência por RFC aprovada.

9. Política de exclusão local e GitHub

Manter a árvore ativa de desenvolvimento.

Criar tag histórica, não um repositório diferente por versão, salvo justificativa demonstrada.

Investigar espaço consumido por caches, builds, ambientes virtuais, modelos e cópias redundantes.

Verificar o que não está no Git (dados locais e segredos, objetos LFS, bancos) e como recuperar.

Excluir somente alvos específicos após conferência, plano de recuperação e autorização separada.

Um push bem-sucedido sozinho não prova que todos os dados importantes foram preservados.

10. Próximas decisões humanas

Aprovar ou ajustar a arquitetura-alvo após auditoria AS-IS.

Autorizar mudanças que alterem contratos ou persistência.

Aprovar a instalação das skills que exigirem permissões/dependências adicionais.

Aprovar cada alteração do próprio Synapse em um eventual fluxo futuro de autoevolução.

Autorizar a remoção de cópias locais somente após relatório de recuperação.

11. Critério global de sucesso da 0.3

O Synapse 0.3 só é considerado pronto se:

A arquitetura executada corresponde aos contratos documentados.

As ferramentas do sistema funcionam com autorização e rastreabilidade reais.

Modelos, Router, Planner, Scheduler, agentes, skills e memória têm fluxos operacionais comprovados.

Swarm executa múltiplos modelos simultaneamente, com prova de residência e gestão de recursos, ou está claramente fora do escopo aprovado da release (nunca mascarado como pronto).

Frontend e backend funcionam conjuntamente no aplicativo Windows real.

Todos os casos críticos de regressão passaram na configuração-alvo.

O manual SYNAPSE_FROM_ZERO.md foi reproduzido e os passos não validados foram explicitados.

A documentação cobre integralmente as capacidades inventariadas e seus testes.

A versão anterior continua recuperável.

Há aceite explícito do usuário.

Fontes para avaliação das skills: obra/superpowers, Anthropic Skills, OpenAI Plugins, NVIDIA Skills, MLflow Skills, skills.sh. Confirmar versões e scripts no momento da instalação.