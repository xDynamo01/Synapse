# Synapse 0.3 — MoM (Mixture of Models)
## Arquitetura de Orquestração Cognitiva

### 1. Conceito

O **MoM (Mixture of Models)** é a arquitetura central de orquestração cognitiva do Synapse.

Seu objetivo é coordenar diferentes modelos de inteligência artificial, cada um especializado em determinadas capacidades, permitindo que operem como partes de um único sistema inteligente.

Em vez de depender de uma única LLM para realizar todas as atividades, o Synapse distribui o processamento entre modelos especializados em conversação, raciocínio, programação, visão computacional, geração de imagens, áudio e outras capacidades.

A ideia central é semelhante à organização funcional de um cérebro: diferentes regiões possuem especializações, mas trabalham de maneira coordenada para produzir um comportamento integrado.

Essa analogia é conceitual. O MoM não pretende reproduzir biologicamente o cérebro humano.

O usuário não precisa escolher manualmente qual modelo utilizar para cada solicitação. O Synapse identifica a intenção, seleciona os recursos adequados e coordena sua execução.

**Princípio fundamental: o usuário interage com o Synapse, não diretamente com os modelos que o compõem.**

O MoM deve permanecer ativo como arquitetura padrão de todas as interações, inclusive nas conversas simples.

---

### 2. Objetivos arquiteturais

O MoM deve:

1. Utilizar modelos especializados conforme a necessidade.
2. Evitar ativar modelos desnecessários.
3. Minimizar latência, consumo de memória e custo computacional.
4. Permitir substituir modelos sem modificar a identidade do Synapse.
5. Coordenar tarefas que exigem diferentes capacidades.
6. Preservar continuidade contextual entre modelos.
7. Integrar memória, Skills, ferramentas e agentes.
8. Executar tarefas simples sem planejamento desnecessário.
9. Suportar tarefas complexas com planejamento e validação.
10. Funcionar tanto com modelos locais quanto com provedores externos.
11. Preservar a governança e as permissões do sistema.
12. Permitir observabilidade, recuperação de falhas e avaliação de resultados.

O MoM não deve transformar toda solicitação em um processo multiagente complexo.

A complexidade da execução deve ser proporcional à complexidade da tarefa.

---

### 3. Componentes principais

#### 3.1. Neural Router

O Neural Router é responsável por identificar a capacidade necessária para atender a uma solicitação e selecionar o caminho de execução adequado.

Ele deve considerar:

- Intenção do usuário.
- Contexto recente da conversa.
- Workspace e projeto ativos.
- Missão em andamento.
- Capacidades disponíveis.
- Modelos configurados.
- Restrições de recursos.
- Políticas e permissões.
- Preferências explícitas do usuário.

O Router não precisa executar raciocínio profundo para cada mensagem.

Sua estratégia deve priorizar decisões determinísticas quando houver sinais suficientes, utilizando classificação leve ou modelos adicionais apenas quando necessário.

O Router também não deve carregar toda a memória do usuário ou de todos os Workspaces.

Ele recebe somente os sinais contextuais necessários para tomar sua decisão.

Exemplos:

"Bom dia, Synapse."

Destino: modelo de conversação.

"Explique este código Python."

Destino: modelo especializado em programação.

"Crie um aplicativo completo."

Destino: fluxo de planejamento e execução coordenada.

"Agora corrija os problemas de segurança."

Se a conversa estiver associada ao desenvolvimento do aplicativo, o Router deve reconhecer essa continuidade e encaminhar a solicitação ao contexto correto.

O Neural Router seleciona o destino da execução, mas não substitui o Planner, o Scheduler ou os mecanismos de autorização.

#### 3.2. Model Registry

O Model Registry mantém informações sobre os modelos disponíveis.

Cada modelo deve possuir metadados como:

- Identificador.
- Provedor.
- Modalidades suportadas.
- Capacidades declaradas e avaliadas.
- Limites de contexto.
- Requisitos computacionais.
- Compatibilidade com ferramentas.
- Estado de disponibilidade.
- Configurações de execução.
- Restrições conhecidas.

As capacidades devem ser representadas de maneira independente dos nomes comerciais dos modelos.

Por exemplo, uma tarefa solicita a capacidade `code_generation`, não necessariamente um modelo específico.

Isso permite substituir modelos sem alterar a lógica geral de orquestração.

#### 3.3. Planner

O Planner é responsável por transformar objetivos complexos em planos executáveis.

Ele determina:

- Quais tarefas precisam ser realizadas.
- Quais dependências existem.
- Quais resultados são esperados.
- Quais capacidades serão necessárias.
- Quais validações devem ocorrer.
- Quais etapas podem ser executadas independentemente.

O resultado pode ser representado por um DAG (Directed Acyclic Graph), com tarefas e dependências explícitas.

O Planner não precisa escolher antecipadamente todos os modelos específicos.

Ele deve preferencialmente definir capacidades necessárias, permitindo que o Router selecione os modelos adequados durante a execução.

O Planner também não deve executar diretamente as tarefas.

Sua responsabilidade é estruturar o trabalho.

#### 3.4. Scheduler

O Scheduler é responsável por coordenar a execução das tarefas planejadas.

Ele considera:

- Dependências.
- Prioridades.
- Recursos disponíveis.
- Estados das tarefas.
- Limites de concorrência.
- Políticas de execução.
- Tentativas de recuperação.
- Resultados de validação.
- Cancelamentos e interrupções.

O Scheduler decide quando uma tarefa está pronta para execução.

O Router determina qual modelo poderá executá-la.

O Scheduler deve manter estados persistentes para permitir recuperação após interrupções.

Exemplos de estados:

- Pending.
- Ready.
- Running.
- Waiting.
- Validating.
- Completed.
- Failed.
- Cancelled.

A execução pode ser sequencial ou concorrente, conforme o plano e as restrições do sistema.

Entretanto, concorrência de tarefas não significa automaticamente ativação do Swarm.

#### 3.5. Model Lifecycle Manager

O Model Lifecycle Manager gerencia o ciclo de vida dos modelos.

Suas responsabilidades incluem:

- Carregamento.
- Inicialização.
- Disponibilidade.
- Reutilização.
- Descarregamento.
- Reservas de recursos.
- Controle de RAM e VRAM.
- Tratamento de falhas.
- Monitoramento de consumo.

O Lifecycle Manager não deve decidir sozinho qual modelo é semanticamente adequado para uma tarefa.

Essa decisão pertence ao Router.

O Lifecycle Manager determina se e como o modelo selecionado poderá ser disponibilizado.

Ele também deve respeitar as reservas de recursos e as regras específicas do Swarm.

#### 3.6. Validator

O Validator verifica se os resultados produzidos atendem aos critérios definidos.

As validações podem incluir:

- Conformidade com contratos.
- Integridade de dados.
- Testes automatizados.
- Verificação de formatos.
- Critérios funcionais.
- Evidências de execução.
- Requisitos de qualidade.
- Verificações de segurança.

Sempre que possível, a validação deve utilizar mecanismos determinísticos.

Uma segunda LLM pode ser utilizada quando houver necessidade de avaliação semântica, mas não deve ser considerada uma fonte infalível de verdade.

Falhas podem produzir solicitações de correção, novas tentativas ou propostas de replanejamento.

O Validator não deve modificar arbitrariamente o plano ou aprovar suas próprias alterações sem respeitar a governança.

---

### 4. Caminhos de execução

O MoM deve suportar três caminhos principais.

#### Caminho A — Conversação direta

Utilizado para interações simples.

Fluxo:

Usuário → Presence → Context Resolution → Neural Router → Modelo de conversação → Resposta.

Exemplos:

- Cumprimentos.
- Perguntas simples.
- Conversas informais.
- Explicações que não exigem ferramentas ou planejamento complexo.

Esse caminho deve minimizar latência e overhead.

#### Caminho B — Execução especializada direta

Utilizado quando uma solicitação exige uma capacidade específica, mas não necessita de planejamento complexo.

Fluxo:

Usuário → Presence → Context Resolution → Neural Router → Modelo especializado → Validação quando necessária → Resposta.

Exemplos:

- Analisar uma imagem.
- Explicar código.
- Resumir um documento.
- Gerar uma imagem.
- Transcrever áudio.

Skills, ferramentas e memória podem ser disponibilizadas conforme a tarefa.

A utilização de um modelo especializado não exige automaticamente a criação de uma Mission.

#### Caminho C — Execução coordenada

Utilizado para tarefas complexas, compostas por múltiplas etapas ou dependências.

Fluxo:

Usuário → Presence → Context Resolution → Neural Router → Planner → Scheduler → Router → Modelo especializado → Validator → Próxima tarefa ou replanejamento → Resultado.

Exemplos:

- Desenvolver uma aplicação.
- Analisar um repositório e implementar correções.
- Produzir um projeto com código, documentação e recursos visuais.
- Executar pesquisas extensas com diferentes ferramentas.
- Coordenar atividades dependentes de múltiplas capacidades.

O Planner define o trabalho.

O Scheduler organiza sua execução.

O Router seleciona os modelos.

O Lifecycle Manager disponibiliza os recursos.

Os Validators verificam os resultados.

O sistema de governança controla as ações que exigem autorização.

---

### 5. Relação entre MoM e Swarm

MoM e Swarm são conceitos diferentes.

**MoM é a arquitetura permanente de orquestração do Synapse.**

**Swarm é um regime específico de execução caracterizado pela residência simultânea de múltiplos modelos.**

O MoM está sempre ativo.

O Swarm não está.

#### Regime NORMAL

No regime NORMAL:

- O Router seleciona modelos conforme a necessidade.
- Os modelos podem ser carregados e descarregados dinamicamente.
- O sistema pode alternar entre especializações.
- O Scheduler pode executar tarefas independentes conforme os recursos disponíveis.
- Não existe exigência de manter múltiplos modelos residentes simultaneamente.

#### Regime SWARM

No regime SWARM:

- Múltiplos modelos permanecem carregados simultaneamente.
- O sistema reserva recursos para os participantes.
- Os modelos podem atuar em tarefas coordenadas.
- O Scheduler considera a disponibilidade dos participantes residentes.
- O Lifecycle Manager respeita as reservas do Swarm.
- O encerramento do Swarm libera suas reservas de forma controlada.

O Swarm deve possuir mecanismos próprios de ativação, transição e encerramento.

Uma tarefa complexa não deve ativar automaticamente o Swarm apenas por possuir múltiplas etapas ou oportunidades de paralelismo.

O Swarm deve continuar sendo uma funcionalidade distinta e explicitamente controlada.

---

### 6. Modos Responsivo e Econômico

O Synapse deve possuir duas políticas principais de gerenciamento de recursos.

Essas políticas não ativam nem desativam o MoM.

#### Responsivo

Prioriza baixa latência.

Características:

- Reutilização de modelos carregados.
- Cache de modelos frequentemente utilizados.
- Menor frequência de descarregamento.
- Concorrência adaptativa quando houver recursos.
- Transições mais rápidas entre capacidades.

Pode consumir mais RAM e VRAM.

#### Econômico

Prioriza eficiência de recursos.

Características:

- Descarregamento mais agressivo de modelos ociosos.
- Menor quantidade de modelos mantidos em cache.
- Concorrência mais restrita.
- Carregamento sob demanda.
- Redução do consumo de RAM e VRAM.

Pode apresentar maior latência.

#### Separação de conceitos

Arquitetura: MoM, sempre ativo.

Regime de execução: NORMAL ou SWARM.

Política de recursos: RESPONSIVE ou ECONOMICAL.

Essas três dimensões devem permanecer independentes.

Quando o Swarm estiver ativo, suas reservas e garantias de residência devem prevalecer sobre políticas normais de descarregamento.

O modo Econômico não deve descarregar participantes ativos do Swarm de maneira arbitrária.

---

### 7. Contexto e memória

O MoM não deve possuir um sistema de memória separado.

Ele deve utilizar a arquitetura central de memória do Synapse 0.3.

A memória pertence ao sistema, não aos modelos.

O contexto fornecido a cada modelo deve ser construído conforme:

- Solicitação atual.
- Workspace ativo.
- Projeto associado.
- Sessão.
- Missão.
- Memórias relevantes.
- Artefatos disponíveis.
- Permissões aplicáveis.
- Limites de contexto do modelo.

O Context Assembly deve produzir uma visão adequada à tarefa.

Um modelo de programação não precisa receber todas as informações pessoais do usuário.

Um modelo de conversação não precisa receber todo o repositório de um projeto.

Um modelo de imagem não precisa receber o histórico completo de execução do Scheduler.

A recuperação deve ser seletiva, contextual e autorizada.

---

### 8. Context Handoff

O Context Handoff permite transferir informações relevantes entre modelos.

Exemplo:

Modelo de planejamento → Modelo de código → Modelo de visão → Modelo de código.

Cada etapa deve receber:

- Objetivo da tarefa.
- Instruções relevantes.
- Artefatos necessários.
- Resultados anteriores.
- Restrições aplicáveis.
- Critérios de aceitação.
- Referências de evidências.

Não deve ser necessário transferir todo o histórico textual entre modelos.

O sistema deve preferir artefatos estruturados, referências persistentes e resumos verificáveis.

O Context Handoff deve preservar a proveniência das informações e evitar que conteúdo produzido por modelos seja confundido com instruções de maior autoridade.

---

### 9. Integração com Skills

O MoM deve utilizar a arquitetura de Skills evolutivas já existente no Synapse, inspirada no Hermes Agent.

Não deve criar um segundo sistema independente de Skills.

A integração deve permitir:

- Descoberta de Skills disponíveis.
- Seleção contextual.
- Compatibilidade com capacidades de modelos.
- Disponibilização seletiva.
- Utilização por diferentes modelos.
- Versionamento e rastreabilidade.
- Evolução controlada.
- Integração com ferramentas.
- Compatibilidade com o Swarm.

Um Skill Resolver poderá atuar como adaptador entre o MoM e a infraestrutura existente.

O Router seleciona a capacidade ou o modelo.

O Skill Resolver identifica as Skills adequadas.

O mecanismo existente permanece responsável pelo ciclo de vida e pela evolução das Skills, conforme seus contratos reais.

Skills não devem conceder permissões adicionais por meio de suas próprias instruções.

A evolução de uma Skill não deve alterar silenciosamente o comportamento de uma missão já iniciada.

---

### 10. Integração com agentes

Modelos e agentes não são equivalentes.

Um modelo é um mecanismo de inferência.

Um agente é uma unidade operacional que pode possuir objetivos, estado, ferramentas, Skills, políticas e responsabilidades.

Um agente pode utilizar diferentes modelos por meio do MoM.

Diferentes agentes também podem utilizar o mesmo modelo.

O MoM não deve duplicar o sistema de agentes existente.

A integração deve preservar:

- Identidade dos agentes.
- Responsabilidades.
- Estados.
- Permissões.
- Ferramentas autorizadas.
- Continuidade das missões.
- Contratos de comunicação.

O Planner e o Scheduler podem coordenar atividades envolvendo agentes, mas não devem substituir automaticamente suas responsabilidades existentes.

---

### 11. Replanejamento dinâmico

O MoM deve permitir modificar planos quando surgirem novas informações.

Exemplos:

- Uma tarefa falha.
- Uma dependência não está disponível.
- Um teste identifica um defeito.
- O usuário altera um requisito.
- Um artefato exige processamento adicional.
- Um modelo não consegue concluir determinada etapa.

O fluxo deve permitir:

1. Detectar a necessidade de alteração.
2. Registrar evidências.
3. Produzir uma proposta de mudança.
4. Verificar dependências e impactos.
5. Aplicar as regras de governança.
6. Atualizar o plano.
7. Retomar a execução a partir de um estado consistente.

O Scheduler não deve modificar arbitrariamente os objetivos da missão.

Replanejamentos devem preservar histórico e rastreabilidade.

---

### 12. Governança e autonomia

O MoM deve respeitar o sistema de governança do Synapse.

A escolha automática de um modelo não significa autorização automática para executar qualquer ação.

O sistema deve distinguir:

- Seleção de capacidade.
- Planejamento.
- Execução.
- Permissão.
- Validação.
- Aprovação.

Ações que exigem autorização devem continuar submetidas às políticas existentes.

O MoM não deve permitir que modelos, agentes ou Skills contornem os mecanismos de governança.

O usuário permanece como autoridade sobre decisões e alterações que dependam de sua aprovação.

---

### 13. Observabilidade

O MoM deve permitir compreender como uma solicitação foi processada.

Informações relevantes incluem:

- Caminho de execução selecionado.
- Modelos utilizados.
- Capacidades solicitadas.
- Skills disponibilizadas.
- Ferramentas executadas.
- Estados das tarefas.
- Tempo de execução.
- Consumo de recursos.
- Resultados de validação.
- Falhas e tentativas de recuperação.
- Alterações de plano.
- Autorizações aplicadas.

A observabilidade deve ser proporcional à complexidade da execução.

Uma conversa simples não precisa produzir a mesma quantidade de eventos de uma missão extensa.

Os registros devem respeitar políticas de privacidade, retenção e segurança.

---

### 14. Exemplo de execução integrada

Solicitação:

"Synapse, desenvolva uma aplicação que permita cadastrar produtos, gerar imagens e verificar automaticamente a qualidade das imagens produzidas."

O fluxo esperado seria:

1. A Presence recebe a solicitação.
2. O Context Resolution identifica o Workspace e o projeto.
3. O Neural Router reconhece uma tarefa complexa.
4. O Planner define as etapas necessárias.
5. O Scheduler organiza as dependências.
6. O Router seleciona um modelo de programação.
7. O Skill Resolver disponibiliza as Skills relevantes.
8. O modelo implementa o backend e os contratos necessários.
9. O Validator executa as verificações aplicáveis.
10. O Scheduler libera a próxima tarefa.
11. O Router seleciona um modelo de geração de imagens.
12. O modelo produz os recursos visuais.
13. O Router seleciona um modelo de visão para análise.
14. O Validator registra os resultados.
15. Caso necessário, o Planner propõe ajustes.
16. O Scheduler coordena as correções.
17. O sistema consolida os artefatos e evidências.
18. A Presence apresenta o resultado ao usuário.

Durante esse processo, os modelos podem ser carregados e descarregados conforme a política de recursos.

A execução não precisa utilizar o Swarm.

Se o Swarm estiver explicitamente ativo, vários modelos poderão permanecer residentes simultaneamente, respeitando suas reservas e políticas.

---

### 15. Requisitos de integração para o Synapse 0.3

A implementação deve partir de uma auditoria da arquitetura existente.

Devem ser identificados:

- MoM atual.
- Swarm atual.
- Model Registry.
- Sistema de agentes.
- Planejamento e missões.
- Scheduler ou mecanismos equivalentes.
- Lifecycle de modelos.
- Skills evolutivas.
- Memória e RAG.
- Presence e Workspace.
- Governança.
- Frontend e controles de execução.
- Persistência e observabilidade.

A implementação não deve presumir que esses componentes estejam ausentes apenas porque utilizam nomes diferentes.

A prioridade é consolidar responsabilidades e contratos, não multiplicar serviços.

Mudanças devem ser incrementais, verificáveis e compatíveis com os mecanismos existentes sempre que possível.

---

### 16. Princípios fundamentais

1. O MoM é permanente.
2. O Synapse possui uma identidade independente dos modelos.
3. Modelos são recursos substituíveis.
4. O Router seleciona capacidades e destinos.
5. O Planner estrutura tarefas complexas.
6. O Scheduler coordena a execução.
7. O Lifecycle Manager gerencia recursos e residência.
8. Validators verificam resultados.
9. Skills pertencem à arquitetura do Synapse.
10. A memória pertence ao Synapse, não aos modelos.
11. O Swarm é um regime independente.
12. Responsivo e Econômico são políticas de recursos.
13. Tarefas simples não exigem planejamento complexo.
14. A execução deve preservar contexto, permissões e proveniência.
15. O sistema deve priorizar integração e reutilização em vez de duplicação.
16. A complexidade arquitetural deve ser justificada por necessidades reais.

---

## 17. Resultado esperado

O MoM do Synapse 0.3 deve funcionar como um sistema de coordenação cognitiva modular, capaz de selecionar e combinar modelos especializados sem exigir que o usuário gerencie manualmente cada etapa.

Sua função não é simplesmente executar várias LLMs.

Sua função é transformar diferentes capacidades de inteligência artificial em um sistema operacionalmente integrado, com memória compartilhada sob controle, execução coordenada, recursos administrados, Skills reutilizáveis, validação e governança.

**O Synapse é o sistema inteligente contínuo. Os modelos são os componentes cognitivos que ele utiliza para realizar suas atividades.**