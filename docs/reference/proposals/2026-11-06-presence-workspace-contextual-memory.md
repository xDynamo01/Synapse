# Synapse 0.3 — Presence, Workspace & Contextual Memory Architecture

## 1. Visão geral

O Synapse deve possuir uma identidade operacional contínua, denominada **Presence**, capaz de interagir com o usuário independentemente do Workspace ativo.

Os Workspaces representam ambientes de trabalho isolados logicamente, cada um com suas próprias conversas, projetos, arquivos, tarefas, configurações e memórias contextuais.

A memória não deve funcionar como um histórico ilimitado de mensagens carregado em todas as interações. Ela deve representar conhecimentos persistentes, fatos canônicos, decisões, relações e experiências relevantes, recuperados seletivamente conforme a necessidade.

**Princípio central:**

A Presence é contínua. Os Workspaces são contextuais. A memória é compartilhável apenas por regras explícitas de escopo e acesso.

---

## 2. Presence — Identidade contínua

A Presence representa o Synapse como assistente persistente.

Ela não é um modelo específico, uma janela de conversa ou um Workspace.

Suas responsabilidades incluem:

- Manter a continuidade da interação com o usuário.
- Identificar o Workspace e o contexto ativos.
- Encaminhar solicitações ao sistema de orquestração.
- Recuperar memórias autorizadas e relevantes.
- Preservar a continuidade entre conversas e sessões.
- Apresentar notificações e resultados de tarefas.
- Manter referências a missões em andamento.
- Coordenar a transição entre Workspaces.

A Presence não deve executar diretamente todas essas operações. Ela atua como ponto de integração com os bounded contexts responsáveis.

### Propriedades

- Uma Presence pode atuar em múltiplos Workspaces.
- Trocar de Workspace não cria outra identidade.
- Trocar de modelo não substitui a Presence.
- Encerrar uma conversa não elimina a continuidade da Presence.
- A Presence não possui acesso irrestrito às memórias de todos os Workspaces.
- Seu estado de sessão deve ser recuperável após reinicializações.

A continuidade é uma propriedade da arquitetura e do estado persistido, não da memória interna de uma LLM.

---

## 3. Workspace — Ambiente contextual

Um Workspace é uma fronteira lógica para organizar informações e atividades.

Exemplos:

- Personal
- Synapse Development
- Game Development
- Smart Home
- Research
- Professional

Cada Workspace pode possuir:

- Conversas e sessões.
- Projetos e artefatos.
- Arquivos e fontes de conhecimento.
- Memórias contextuais.
- Missões e tarefas.
- Configurações específicas.
- Skills habilitadas.
- Permissões e políticas.
- Preferências de modelos.
- Índices de recuperação semântica.

O Workspace não deve criar automaticamente uma nova Presence.

### Relação

Presence 1 → Workspace A

Presence 1 → Workspace B

Presence 1 → Workspace C

A mesma Presence pode alternar entre eles, preservando a identidade e respeitando o isolamento contextual.

---

## 4. Arquitetura de memória

A memória deve ser organizada por escopo, finalidade e ciclo de vida.

### 4.1. Core Memory

Memória de escopo global, contendo informações estáveis necessárias à continuidade do assistente.

Exemplos:

- Preferências gerais de interação.
- Configurações persistentes autorizadas.
- Informações canônicas do usuário.
- Referências aos Workspaces existentes.
- Preferências globais de comunicação.

A Core Memory deve ser pequena, estruturada e carregada seletivamente.

Ela não deve armazenar o conteúdo completo das conversas.

### 4.2. Workspace Memory

Memória pertencente a um Workspace específico.

Exemplos:

Workspace: Synapse Development

- Decisões arquiteturais.
- Tecnologias utilizadas.
- Convenções de desenvolvimento.
- Restrições técnicas.
- Estado de projetos.
- Problemas conhecidos.
- Decisões substituídas.

Workspace: Game Development

- Mecânicas de jogos.
- Personagens.
- Sistemas de progressão.
- Direção artística.
- Decisões narrativas.

Essas memórias não devem ser injetadas em outros Workspaces sem autorização ou necessidade explícita.

### 4.3. Project Memory

Memória específica de um projeto dentro de um Workspace.

Um Workspace pode conter múltiplos projetos, cada um com sua própria memória.

Exemplo:

Workspace: Game Development

Project A: God Like

Project B: LifeXP

Project C: Mythos Engine

Cada projeto possui fatos, decisões, artefatos e histórico próprios.

A memória de um projeto não deve contaminar automaticamente os demais.

### 4.4. Session Memory

Representa o estado temporário da interação atual.

Inclui:

- Mensagens recentes.
- Intenção atual.
- Referências e entidades mencionadas.
- Artefatos em edição.
- Workspace ativo.
- Projeto ativo.
- Missão associada.

Seu objetivo é manter a continuidade imediata da conversa.

Informações relevantes podem ser promovidas para memórias persistentes por um processo controlado.

### 4.5. Mission Memory

Memória operacional de uma missão.

Inclui:

- Objetivo.
- Plano e dependências.
- Estado de execução.
- Decisões tomadas.
- Resultados intermediários.
- Evidências.
- Artefatos.
- Erros e tentativas de recuperação.
- Referências às versões de Skills utilizadas.

Essa memória deve permitir pausar, retomar, auditar e recuperar missões.

Não deve ser confundida com conhecimento canônico permanente.

### 4.6. Episodic Memory

Registra experiências relevantes do sistema.

Exemplos:

- Uma estratégia que resolveu determinado problema.
- Uma falha recorrente de execução.
- Uma combinação de modelo e Skill que funcionou adequadamente.
- Uma correção validada.
- Uma decisão tomada durante uma missão.

Experiências não são automaticamente fatos universais.

Devem preservar contexto, evidências e limitações.

### 4.7. Semantic Knowledge / RAG

Responsável pela recuperação de conhecimento em documentos, arquivos e outras fontes autorizadas.

O RAG não substitui a memória canônica.

Diferença:

- Memória canônica: registra o que o sistema considera uma informação persistente e validada.
- RAG: recupera trechos de fontes que podem ser relevantes para uma consulta.
- Memória episódica: registra acontecimentos e experiências anteriores.

As três fontes podem colaborar, mas devem manter proveniência distinta.

---

## 5. Identificação contextual

O Synapse poderá utilizar identificadores estáveis para organizar os contextos.

Exemplo conceitual:

- #001 — Personal
- #002 — Smart Home
- #003 — Synapse Development
- #004 — God Like
- #005 — LifeXP

Esses códigos são identificadores lógicos, não instruções para carregar toda a memória correspondente.

Cada registro deve possuir um identificador interno estável e metadados de escopo.

Um projeto poderá pertencer a um Workspace sem depender da ordem numérica dos códigos.

O mecanismo de recuperação deve utilizar a identidade do contexto e as relações registradas, não apenas correspondência textual.

---

## 6. Recuperação seletiva de memória

A cada solicitação, o Synapse deve determinar:

1. Qual é a intenção do usuário?
2. Qual Workspace está ativo?
3. Existe um projeto ativo?
4. Existe uma missão em andamento?
5. Quais memórias são relevantes?
6. Quais memórias estão autorizadas para esse contexto?
7. Qual quantidade de contexto é necessária?

Fluxo conceitual:

User Input
    ↓
Presence
    ↓
Context Resolution
    ↓
Workspace / Project / Mission Identification
    ↓
Memory Retrieval
    ↓
Scope & Permission Filtering
    ↓
Context Assembly
    ↓
Neural Router / MoM
    ↓
Selected Model(s)
    ↓
Response / Execution
    ↓
Memory Evaluation
    ↓
Selective Persistence

O Router não deve receber obrigatoriamente todo o conteúdo recuperado.

O sistema deve utilizar apenas os sinais contextuais necessários para decidir o encaminhamento.

A montagem completa do contexto ocorre conforme as necessidades da execução.

---

## 7. Escrita e consolidação de memórias

Nem toda mensagem deve se tornar memória persistente.

O sistema deve diferenciar:

- Informação temporária.
- Preferência duradoura.
- Fato canônico.
- Hipótese.
- Decisão.
- Experiência.
- Informação contraditória.
- Informação obsoleta.

### Processo de consolidação

1. Detectar uma informação potencialmente relevante.
2. Identificar o escopo correto.
3. Verificar se já existe registro equivalente.
4. Comparar a informação nova com o estado existente.
5. Determinar se deve criar, atualizar, relacionar ou rejeitar.
6. Aplicar políticas de persistência e autorização.
7. Registrar proveniência e versão.
8. Atualizar índices de recuperação quando necessário.

Memórias contraditórias não devem ser silenciosamente mescladas.

Decisões substituídas devem poder ser rastreadas historicamente.

### Estrutura conceitual de um registro

memory_id: identificador estável

scope: global | workspace | project | mission

owner_id: identificador do escopo proprietário

type: fact | preference | decision | hypothesis | episode

content: informação canônica ou referência estruturada

source: origem da informação

confidence: nível de confiança, quando aplicável

status: active | superseded | disputed | archived

created_at: data de criação

updated_at: última atualização

version: versão do registro

relations: referências a outras memórias

access_policy: regras de leitura e utilização

O formato final deve respeitar os contratos e mecanismos de persistência já existentes.

---

## 8. Relação entre Presence e Workspace

A Presence deve manter um vínculo com o Workspace ativo, sem se tornar proprietária de todas as informações dele.

### Exemplo A — Conversa geral

Usuário: "Bom dia, Synapse."

Presence identifica uma interação social simples.

O sistema utiliza o modelo de conversação.

Não é necessário carregar memórias de projetos ou executar planejamento complexo.

### Exemplo B — Trabalho em um projeto

Usuário: "Continue a implementação do sistema de memória."

Workspace ativo: Synapse Development.

O sistema recupera o contexto do projeto, a missão relevante e as decisões arquiteturais necessárias.

O Router encaminha a solicitação ao fluxo apropriado.

### Exemplo C — Mudança de Workspace

Usuário: "Agora vamos trabalhar no God Like."

A Presence mantém sua identidade.

O contexto ativo passa para o Workspace correspondente.

As memórias do Synapse Development deixam de compor o contexto de trabalho, salvo referências explicitamente necessárias e autorizadas.

### Exemplo D — Referência entre Workspaces

Usuário: "Use no God Like uma arquitetura semelhante à do Synapse."

O sistema identifica uma solicitação explícita de conhecimento entre contextos.

A recuperação deve consultar as fontes autorizadas do Synapse Development e fornecer somente as informações relevantes ao projeto God Like.

A consulta não transfere automaticamente a propriedade dessas memórias.

### Exemplo E — Missão em segundo plano

O usuário inicia uma missão no Workspace Synapse Development e depois alterna para Personal.

A missão permanece associada ao Workspace de origem.

A Presence pode receber e apresentar eventos autorizados dessa missão sem mudar automaticamente o Workspace ativo.

---

## 9. Integração com MoM e Swarm

A memória pertence ao Synapse, não aos modelos individuais.

Os modelos devem receber visões contextuais controladas.

### MoM normal

- Recuperar o contexto necessário.
- Selecionar o modelo adequado.
- Fornecer apenas as informações relevantes.
- Preservar estado e artefatos entre etapas.
- Evitar replicação desnecessária de contexto.

### Swarm

- Vários modelos podem permanecer carregados simultaneamente.
- Cada participante recebe uma visão contextual apropriada.
- O acesso às memórias deve respeitar permissões e escopos.
- Alterações persistentes devem ser coordenadas.
- Escritas concorrentes devem utilizar mecanismos de consistência.
- Memórias compartilhadas não devem ser modificadas diretamente por múltiplos modelos sem controle transacional.

O Swarm não deve criar um segundo sistema de memória.

---

## 10. Integração com Skills evolutivas

Skills e memória são sistemas distintos, mas relacionados.

A arquitetura existente de Skills inspirada no Hermes Agent deve ser preservada.

As Skills podem consultar memórias autorizadas e produzir evidências para seu próprio mecanismo de evolução.

Entretanto:

- Skills não possuem acesso global automático.
- Evoluir uma Skill não altera memórias canônicas por consequência implícita.
- Evidências de execução podem alimentar memória episódica.
- O histórico de evolução das Skills deve permanecer rastreável.
- A recuperação contextual deve ser independente do modelo que executa a Skill.

A integração deve ocorrer pelos contratos existentes ou por adaptadores mínimos, evitando sistemas paralelos.

---

## 11. Isolamento, segurança e privacidade

O sistema deve tratar Workspaces como fronteiras lógicas de acesso.

Requisitos:

- Filtragem de escopo antes da entrega de contexto aos modelos.
- Verificação de autorização nas operações de leitura e escrita.
- Proteção contra vazamento entre Workspaces.
- Exclusão e retenção controladas.
- Proveniência de informações persistentes.
- Separação entre instruções confiáveis e conteúdo recuperado.
- Tratamento de conflitos e atualizações concorrentes.
- Recuperação consistente após falhas.
- Possibilidade de exportação e remoção de dados conforme as políticas aplicáveis.

O isolamento por Workspace não deve depender apenas de instruções no prompt.

---

## 12. Persistência e ciclo de vida

A memória deve sobreviver ao descarregamento de modelos e ao encerramento da aplicação, conforme sua política de retenção.

A Presence pode ser restaurada a partir de estado persistido.

Uma Session pode ser retomada quando houver estado recuperável.

Uma Mission deve preservar seus próprios checkpoints e resultados.

O Workspace deve manter suas referências independentemente da janela de interface aberta.

Fechar uma janela não deve significar apagar a memória do Workspace.

Descarregar uma LLM não deve significar perder o estado da Presence.

---

## 13. Regras arquiteturais fundamentais

1. Presence não é uma LLM.
2. Workspace não é uma Presence.
3. Memória não é histórico bruto de conversas.
4. RAG não substitui memória canônica.
5. O Router não deve carregar todos os contextos.
6. Modelos não são proprietários das memórias.
7. Skills não concedem permissões de acesso.
8. Swarm não possui uma memória paralela.
9. Contextos são isolados por padrão.
10. Compartilhamento entre Workspaces deve ser explícito e autorizado.
11. Informações persistentes devem possuir proveniência.
12. Alterações devem preservar rastreabilidade e consistência.
13. O sistema deve evitar duplicação de fontes de verdade.
14. A arquitetura existente deve ser auditada antes de qualquer substituição.

---

## 14. Estratégia de implementação para Synapse 0.3

### Fase 0 — Auditoria

Identificar os mecanismos existentes de:

- Memória.
- RAG.
- Sessions.
- Workspaces.
- Presence ou mecanismos equivalentes.
- Missions.
- Context routing.
- Persistência.
- Skills.
- Permissões.

Mapear contratos, dependências e fluxos reais.

Não presumir ausência de funcionalidades apenas porque utilizam nomenclaturas diferentes.

### Fase 1 — Contratos de escopo

Definir as relações entre Presence, Workspace, Project, Session e Mission.

Estabelecer regras de propriedade, visibilidade e persistência.

### Fase 2 — Recuperação contextual

Consolidar a seleção de memórias relevantes e autorizadas.

Integrar com Neural Router e Context Assembly.

### Fase 3 — Consolidação de memória

Implementar ou adaptar mecanismos de extração, deduplicação, atualização, versionamento e resolução de conflitos.

### Fase 4 — Continuidade da Presence

Garantir transições entre Workspaces, retomada de sessões e acompanhamento de missões sem perda de identidade operacional.

### Fase 5 — Integração MoM / Swarm / Skills

Validar acesso contextual por modelo, concorrência, compartilhamento de artefatos e compatibilidade com Skills evolutivas.

### Fase 6 — Testes integrados

Validar:

- Troca de Workspace sem vazamento de contexto.
- Continuidade da Presence após troca de modelo.
- Recuperação seletiva de memórias.
- Atualização de fatos canônicos.
- Resolução de contradições.
- Recuperação de sessões e missões.
- Acesso autorizado entre Workspaces.
- Escritas concorrentes no Swarm.
- Compatibilidade com Skills existentes.
- Persistência após reinicialização.

---

## 15. Critério de conclusão

A arquitetura estará consolidada quando o Synapse conseguir:

- Manter uma Presence contínua.
- Alternar entre Workspaces sem perder identidade.
- Preservar isolamento contextual.
- Recuperar somente memórias relevantes e autorizadas.
- Retomar sessões e missões persistidas.
- Compartilhar informações entre contextos sob controle explícito.
- Operar com MoM e Swarm sem duplicar o sistema de memória.
- Preservar a arquitetura evolutiva de Skills.
- Registrar e atualizar conhecimento canônico com rastreabilidade.

**Resultado esperado:**

Um Synapse com identidade contínua, memória modular e ambientes de trabalho independentes, no qual modelos, Skills e ferramentas podem ser substituídos ou coordenados sem comprometer a continuidade do assistente nem a integridade dos contextos.