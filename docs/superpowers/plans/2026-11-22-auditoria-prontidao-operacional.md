# Synapse — critérios de prontidão operacional

Data: 2026-11-22. Estado em 2026-11-24: 33/34 critérios verificados no escopo de software Windows; reinício/falha abrupta do computador não realizado, dispensado expressamente pelo usuário em 2026-11-24.

Esta lista amplia o escopo do [aceite das oito prioridades de integração](../../evidence/backend/2026-11-22-integracao-oito-prioridades.md). Os 27 itens anteriores continuam sendo evidência dos fluxos testados; não certificam automaticamente segurança completa, métricas operacionais, recuperação de falta de energia ou distribuição do cliente atual. A inspeção inicial leu código e verificadores. A implementação e os ensaios posteriores estão no [recibo de prontidão operacional](../../evidence/backend/2026-11-24-operational-readiness.md). A validação de interrupção elétrica/reinício não foi substituída por morte de processo.

Referências vinculantes: [Documento de Decisões](../../specs/2026-11-06-synapse-0.3-decision-charter.md), especialmente MI-002–007, SE-001–006, PL-001–006 e QA-001–003. Rust nativo e Python; uma ARTEMIS permanente; inferência local; Swarm com consentimento; preservação do trabalho local. A exigência de aprovação explícita para autoalterações vem desta nova lista e não pode ser substituída por uma aprovação genérica de tarefas.

## Situação inicial encontrada em 2026-11-22 (histórico)

| Grupo | Base existente verificada no código | Lacuna para fechar o grupo |
| --- | --- | --- |
| 1. Contratos e compatibilidade | API Core v1, worker Python v4, validação de campos, digests e migrações SQLite até v15. | As extensões de entrada, orquestração e grafo são criadas fora de uma revisão numerada própria. Falta matriz atual de compatibilidade, teste de downgrade recusado e procedimento de restauração compatível. |
| 2. Segurança e isolamento | Escopos exatos, consentimento, broker, LPAC, proteção de credenciais do navegador e testes negativos específicos. | Falta revisão abrangente e atual de todos os consumidores e canais; isolamento por projeto não prova isolamento entre usuários. Perfil de preferências não equivale a identidade autenticada. |
| 3. Confiabilidade | Idempotência, journals, morte de processo, recuperação de publicação, leases e reconciliação de modelos. | Falta evidência de reinício do computador/falta de energia e campanha de falhas com reservas, arquivos, banco e provedor reconciliados em conjunto. |
| 4. Observabilidade | Eventos correlacionáveis, motivos de rota, erros e duração de verificações. | Não foi identificado um sistema completo de métricas de tokens, latência por fase, RAM/VRAM medidas, retries e custo. Capacidade física total e estimativa de pico não são medição de uso. |
| 5. Qualidade | Testes de integração, verificadores nativos, benchmarks de Skills e tarefas locais reais. | Falta conjunto versionado de evals de roteamento/memória/ferramentas/replanejamento com rótulos, métricas de falsos positivos/negativos e limites de regressão. |
| 6. Performance e custos | Contexto limitado, reutilização de instâncias, um slot de modelo, orçamento declarado de memória e prazos por inferência/check. | Falta orçamento agregado por missão, medição de VRAM, análise de carga e política de esgotamento. Inferência remota deve continuar desativada; orçamento de chamadas remotas de inferência é zero enquanto essa direção não mudar. |
| 7. Operação e distribuição | Empacotador, instalador com hashes, troca de versão, rollback de programa e verificadores de instalação anteriores. | O empacotador e o instalador ainda exigem `synapse-desktop`, enquanto o executável atual usa Slint. Falta aceite de instalação do conjunto atual e backup/restauração completos da memória, preferências e configuração. Hash conferido não prova, sozinho, autenticidade da origem. |
| 8. Autogovernança | Aprovação de missão, candidato selado, QA antes de publicação e reversão de efeitos específicos. | Não foi identificado um fluxo dedicado de autoalteração do Synapse com identificação do proponente/executor, revisão do diff antes de aplicar e aprovação humana específica da mudança. |
| 9. Documentação | Charter, especificações, guias, registros de aceite e checklist anterior. | Parte dos documentos preserva estados históricos e componentes substituídos. Faltam índice de arquitetura atual, contratos por componente e runbooks com critérios executáveis para a versão corrente. |

## Checklist de aceite — os nove grupos

Cada caixa representa o requisito completo. Evidência parcial não fecha a caixa. Registrar revisão das fontes, artefato, plataforma, comando, resultado e limitações antes de marcar.

### 1. Contratos e compatibilidade

- [x] Versionar os contratos entre frontend, Core, worker/modelos, ferramentas e missões; publicar matriz de versões e capabilities negociadas.
- [x] Validar mudanças de schema e leitura de dados antigos com fixtures representativas, inclusive os dados novos de entrada, preferências, grafos e reservas.
- [x] Definir e testar migração, recusa de downgrade incompatível e rollback por restauração consistente, sem apagar dados válidos.

Arquivos iniciais: `backend/core/src/contracts.rs`, `store.rs`, `intake.rs`, `orchestration.rs`, `task_graph.rs`, `backend/python/synapse_ai/protocol.py` e testes de compatibilidade existentes.

### 2. Segurança e isolamento

- [x] Revisar permissões por ferramenta, modelo, agente temporário e missão, incluindo revogação durante execução e tentativas de autoampliação de autoridade.
- [x] Provar isolamento entre conversas, usuários, projetos e Swarms; definir o limite de usuário do produto local e o limite futuro do servidor, sem presumir que um campo de perfil forneça autenticação.
- [x] Proteger credenciais, prompts, temporários e saídas externas em seus consumidores: canários sintéticos, ACLs, retenção, descarte, logs, erros e backups.

Aceite: operações autorizadas continuam funcionando; tentativas não autorizadas falham sem vazamento em prompts, logs, arquivos publicados ou consumidores de outro escopo. Não reutilizar credenciais reais para os testes negativos.

### 3. Confiabilidade

- [x] Provar idempotência de retries em comandos, aprovação, tarefas, publicação, reconciliação e retomada.
- [ ] Provar recuperação após morte do processo e reinício do computador, distinguindo desligamento limpo de interrupção abrupta. **Reinício: não realizado por dispensa do usuário em 2026-11-24. Morte de processos e recuperação injetada: verificadas.**
- [x] Prevenir tarefas duplicadas, jobs órfãos, efeitos repetidos e estados ativos sem proprietário vivo.
- [x] Reconciliar reservas e modelos após falhas parciais de carga, inferência, descarga e persistência, preservando instâncias do operador.

Aceite: matriz de pontos de falha antes/depois de cada persistência e efeito; comprovação no banco, no provedor e nos arquivos. Ensaios de falta de energia exigem ambiente descartável apropriado, não desligamento destrutivo da máquina de trabalho.

### 4. Observabilidade operacional

- [x] Disponibilizar logs estruturados e rastreáveis por conversa, missão, tarefa, job e tentativa, com versão do evento.
- [x] Medir latência, tokens/custo aplicável, RAM/VRAM, falhas e retries; diferenciar estimativa, valor medido e informação indisponível.
- [x] Registrar por que rota, modelo e ferramenta foram escolhidos ou recusados, incluindo escolha manual, disponibilidade, orçamento e fallback.

Aceite: uma missão permite reconstruir sua execução sem consultar conteúdo privado desnecessário. Ausência de GPU ou contador não pode aparecer como uso zero medido.

### 5. Qualidade dos resultados

- [x] Criar evals versionados de roteamento, memória, ferramentas, validação e replanejamento, com casos positivos, negativos e ambíguos.
- [x] Medir falsos positivos e negativos, definir denominadores, classes, limites de aceite e comparação com uma base fixa.
- [x] Executar tarefas reais representativas e registrar resultado verificável; separar testes determinísticos, evals de modelo e aceite do artefato distribuído.

Aceite: relatório reproduzível com modelo/configuração, conjunto de casos, resultados por classe e critérios de regressão; uma missão simples bem-sucedida não cobre todos os tipos de projeto.

### 6. Performance e custos

- [x] Aplicar limites de contexto e política explícita de truncamento/compactação, preservando objetivo e restrições necessárias.
- [x] Medir cache e reutilização de modelos, invalidação e liberação segura; reaproveitamento de instância não deve ser chamado de cache de respostas.
- [x] Controlar concorrência entre inferência, verificações e missões com admissão e prioridades observáveis.
- [x] Aplicar orçamento agregado de tempo, tokens, RAM e VRAM por missão, com comportamento definido quando faltar recurso.
- [x] Manter chamadas remotas de inferência bloqueadas e custo remoto zero; ferramentas de internet seguem a autorização da missão e limites próprios.

Aceite: carga repetida, entrada grande, cancelamento e pressão de recursos dentro de um perfil registrado; nenhuma troca silenciosa de modelo explicitamente escolhido.

### 7. Operação e distribuição

- [x] Gerar instalação reproduzível incluindo o frontend Slint, Core, workers, recursos e dependências necessárias da revisão atual.
- [x] Verificar dependências e configuração inicial sem depender do ambiente do terminal de desenvolvimento.
- [x] Validar atualização segura e rollback do programa, incluindo compatibilidade do banco e origem do pacote.
- [x] Implementar e testar backup/restauração de memória, preferências e configuração com snapshot consistente e proteção adequada; copiar somente o arquivo principal de SQLite em uso não é prova de backup correto.
- [x] Diagnosticar ausência de GPU, ausência de provedor local, ferramentas indisponíveis e recursos insuficientes sem simular sucesso.

Arquivos iniciais: `tools/release/package.py`, `install-windows.ps1`, `start-windows.ps1`, verificadores de instalação/recuperação e `backend/desktop-slint/src/local_runtime.rs`. Validar num diretório e estado descartáveis; não alterar a instalação de uso para testar falhas.

### 8. Governança do próprio Synapse

- [x] Exigir aprovação humana explícita para autoalterações, vinculada à mudança concreta e à revisão de base.
- [x] Fazer code review antes de aplicar a mudança; QA por execução de testes não substitui revisão do diff.
- [x] Registrar quem ou qual agente propôs, revisou, autorizou e executou, com IDs e digests verificáveis.
- [x] Reverter mudanças feitas pelo sistema e validar recuperação após publicação parcial ou falha de atualização.

Aceite: referências web, modelos, Skills e agentes temporários não podem autorizar a alteração. Uma aprovação genérica de projeto não deve ser promovida silenciosamente a autorização para modificar o próprio Synapse.

### 9. Documentação e manutenção

- [x] Sincronizar o índice da arquitetura com os componentes executados e identificar claramente referências históricas.
- [x] Documentar versões, entradas, saídas, erros, limites e compatibilidade dos contratos de cada componente.
- [x] Criar runbooks para banco, provedor, ferramentas, reservas incertas, publicação interrompida, atualização e restauração.
- [x] Definir critérios claros e executáveis para considerar a versão pronta, diferenciando código local, pacote instalado e validação por plataforma.

## Ordem recomendada de implementação

1. Contratos, migrações e inventário do pacote atual: estabilizar a base de dados e a identidade dos artefatos.
2. Proteção de consumidores, autogovernança e recuperação: fechar limites antes de ampliar automação.
3. Métricas e orçamentos: produzir dados para diagnosticar execução e estabelecer limites de carga.
4. Evals e campanha de falhas: medir resultados e regressões com os critérios anteriores.
5. Backup/restauração e aceite de instalação/atualização do pacote atual.
6. Consolidar runbooks, arquitetura e gate final da versão com os recibos produzidos em cada frente.

A ordem preserva as integrações já existentes. As marcações acima remetem à revisão e aos ensaios atuais no Windows. O usuário informou que não possui mídia/VM e dispensou esse ensaio em 2026-11-24; ele permanece registrado como não realizado, sem reiniciar a máquina de trabalho. Não há aceite global das demais plataformas.


