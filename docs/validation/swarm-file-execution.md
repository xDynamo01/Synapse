# Swarm: execução de ferramentas e evidência de conclusão

Implementação: 2026-10-30. Revalidação final do executável: 2026-11-04. Escopo: correção do falso `completed` no comando natural de Swarm para analisar e corrigir um projeto local. O backend global continua **NOT READY**.

## Incidente confirmado

A interação `4015debd-560d-4448-897d-5f272e983036`, missão `438759f2-cc5e-4809-914f-2603e960f0c8`, marcou `completed` enquanto o modelo dizia não poder acessar `E:\Projetos\conversor-app`. Esse registro histórico não foi alterado. O projeto do usuário não foi modificado nesta validação.

As causas eram cumulativas: ferramentas herdadas de uma lista de preferências vazia; tarefas sem operações obrigatórias; verificação somente de texto não vazio; uma única rodada de ferramentas; conclusão da interação independente do estado de execução; retomada da aprovação sem retomar a missão.

## Contrato corrigido

- Os agentes temporários recebem o conjunto autorizado do agente responsável, limitado pelo escopo da tarefa e pelas proibições. Preferência de ferramenta não concede permissão.
- O comando com vírgula após `swarm` é reconhecido. A análise lê o projeto e a correção depende dos resultados da análise.
- A execução permite até oito rodadas. Os modelos locais recebem o resultado mais recente também no formato nativo de ferramenta, com contabilização do contexto. A seleção de ferramentas não consome a saída inteira em raciocínio interno.
- Uma tarefa de projeto exige recibos reais de leitura dentro da raiz solicitada. Uma correção exige mutação e releitura posterior; exclusão exige listagem posterior comprovando ausência. Texto, chamada pendente, acesso fora da raiz e falta de releitura não satisfazem a verificação.
- Edições aguardam aprovação. A retomada respeita a missão, a reserva do Swarm e o identificador da chamada. Missão cancelada não executa a edição pendente; uma aprovação consumida não repete a alteração.
- O estado da interação acompanha `waiting_approval`, `failed` ou `completed`. Seu resumo de operações em arquivos vem dos recibos, não de afirmações do modelo. A ausência de execução da suíte do projeto é explícita.
- NORMAL/SWARM e RESPONSIVE/ECONOMICAL permanecem separados. A retomada passa pelo ciclo de vida existente do Swarm. Não foi criado um caminho alternativo de carregamento ou coordenação.

## Prova com modelos reais

Foram utilizados os modelos locais já instalados `qwen2.5-0.5b-instruct-q4_k_m` e `gemma-4-E2B_q4_0-it`, com estimativas de residência medidas anteriormente. Não houve download de modelos grandes.

O projeto descartável continha `app.py` com `answer = 41`. O comando natural pediu análise e alteração para `answer = 42`.

1. O primeiro agente leu o arquivo real.
2. A alteração ficou aguardando aprovação; o arquivo continuou com 41.
3. O teste autorizou somente a alteração no projeto descartável.
4. O segundo agente aplicou a alteração e releu o arquivo, agora com 42.
5. As verificações passaram; os dois agentes temporários foram destruídos, as reservas liberadas e o regime voltou a NORMAL, mantendo ECONOMICAL.

O teste também foi executado no backend compilado através de `/api/frontend/conversations/{id}/turns/stream`, o mesmo endpoint da interface, e da aprovação pela API. Foram observados dois processos de modelo residentes e os dois modelos reservados durante a espera.

Artefatos locais:

- `artifacts/reports/real-swarm-file-repair.json`: inferência, recibos, estados, amostras de residência e resultado do arquivo.
- `artifacts/reports/real-swarm-compiled-file-repair.json`: verificações pelo executável e endpoint da interface.
- `tests/acceptance/test_swarm_project_tools_e2e.py`: recusa sem ferramentas, aprovação, cancelamento, retomada, releitura, repetição e resumo baseado em evidência.
- `tests/test_swarm_file_verification.py`: verificação negativa de operações, raiz e exclusão.
- `tests/test_local_swarm_tool_feedback.py`: transporte do recibo ao modelo local e isolamento das opções específicas do motor.

## Gates e limites

A regressão global executada durante o desenvolvimento registrou 4657 passes, 16 falhas e 5 skips. As falhas eram uma fixture que tratava preferência como autorização e quinze verificações da aresta adicional `workers -> tools`. A fixture passou a conceder permissões explícitas a uma ferramenta registrada; a aresta foi removida, preservando a fronteira por recibos serializados. Não foram relaxadas as expectativas de arquitetura.

A suíte de arquitetura e o cenário de projeto foram repetidos depois da correção: 276 passes. O conjunto de casos de ciclo de vida e evidência registrou 16 passes. A checagem global de tipos registrou 835 arquivos sem erros. A reexecução explícita das 16 falhas passou integralmente (16 passes; `swarm-global-failure-recheck.txt`). Não se apresenta isso como uma segunda execução global sem falhas. Os relatórios finais de reexecução, lint, tipos e build ficam em `artifacts/reports/swarm-*.txt`.

Esta prova confirma execução real de leitura, edição aprovada e conferência de arquivo por Swarm. Não comprova a correção funcional de qualquer projeto arbitrário nem a execução dos testes de `conversor-app`. Falta de capacidade do modelo, erro de ferramenta ou ausência de evidência deve permanecer falha visível, nunca conclusão presumida.

## Revalidação do executável final — 2026-11-04

As onze verificações do teste compilado passaram, incluindo resumo baseado nos recibos e limpeza das aprovações pendentes. Missão `73e2c385-b390-45fb-bde2-144f6655fc25`; Swarm `2ac16d87-c15d-460f-a71b-85925246f6a9`. O arquivo descartável terminou com `answer = 42`. A prova usa o binário instalado em `backend/dist/synapse_backend/synapse_backend.exe`, SHA-256 `8ac192df2890daace4ddcf9965d07e13fcc03eb2c7734fd5c836063e90024085`.

Build final e launcher: concluídos. Mypy final: 835 arquivos sem erros. Ruff e diff check: aprovados. A validação do executável foi pela API utilizada pela interface; não foi uma inspeção visual da janela. O serviço opcional de repositórios reportou divergência da raiz canônica no perfil isolado, sem impedir as ferramentas de arquivos testadas; não se declara esse serviço validado.

## Incidente posterior: seleção automática interpretada como nome de modelo

Em 2026-11-04, a interação `c046653a-7dc1-45b4-b10d-be9fd3da6fac` falhou antes de criar o Swarm. O pedido continha “utilize os modelos mais recomendados para cada açao”. O classificador registrou incorretamente `explicit_models: [mais]`; a validação de recursos rejeitou esse modelo inexistente. Isso não era ausência de ferramentas dos agentes: os agentes ainda não haviam sido criados.

O classificador agora distingue descrições de seleção automática de identificadores explícitos. Nomes explicitamente solicitados, inclusive desconhecidos, continuam sujeitos à validação de recursos, sem substituição silenciosa. A extração também aceita espaços após vírgulas em listas de modelos.

Validação específica: 23 testes de classificação/interação passaram; 5 cenários de projeto passaram, incluindo a redação original com quatro agentes, aprovação, conferência, cancelamento e repetição. Ruff e Mypy do módulo passaram. Relatórios: `swarm-model-selection-regression.txt`, `swarm-four-agents-regression.txt` e `swarm-model-selection-types.txt`, em `artifacts/reports/`.
