# Swarm real com modelos leves — 27/10/2026

Teste solicitado pelo usuário: produzir uma to-do list usando modelos reais,
com residência simultânea, sem depender de modelos grandes.

## Ambiente e escopo

- Windows, aproximadamente 16 GiB de RAM física; disponibilidade variável durante o teste.
- Inferência CPU pelo llama-server AVX2 já instalado, sem uso de VRAM para inferência.
- Dados, agentes, missões e perfis de recursos isolados em `.cache/synapse/real-swarm/`.
- Runtime, Planner, dispatcher, WorkerExecutionAdapter, ModelRouter, verificador e
  coordenador Swarm reais; sem substituir a geração por mocks.
- Perfis de RAM obtidos por geração individual e RSS do processo, acrescidos de
  10% para a admissão. Também exigida margem livre de 1 GiB antes da rodada.
- Nenhuma configuração real de modelos, missões ou preferência do usuário foi alterada.

## Rodada 1: duas listas em paralelo

Modelos: Gemma 2 2B Q4_K_M e Gemma 4 E2B Q4_0 já presentes no computador.
Uma subtarefa pediu quatro tarefas para uma manhã de trabalho; outra, quatro
tarefas para organizar a casa.

- Missão concluída em 46,2 segundos, incluindo ativação do Swarm.
- Dois processos distintos carregados e observados em estado BUSY simultaneamente.
- Pico da soma de RSS: 5,47 GiB; menor RAM livre observada: 2,01 GiB.
- Política alterada para ECONOMICAL enquanto os dois modelos estavam BUSY:
  ambos permaneceram carregados e reservados.
- Ao concluir, modelos e reservas foram liberados; nenhum llama-server do teste permaneceu.

Qualidade: ambos produziram listas utilizáveis em português. O Gemma 2 extrapolou
sua subtarefa e incluiu também uma lista doméstica; isso é uma falha de aderência
ao escopo, embora a execução e a validação estrutural tenham sido concluídas.
O verificador `non_empty` não prova obediência a todos os critérios semânticos.

Evidência completa: `artifacts/reports/real-swarm-todo.json`, com outputs,
identidades dos modelos, tentativas, PIDs e amostras de memória/residência.

## Preparação da rodada com dependências

Uma nova tentativa foi recusada pelo preflight do teste quando a memória livre
caiu abaixo da margem exigida. Nenhum modelo foi carregado nessa tentativa.
Para reduzir a carga, foi obtido o Qwen 2.5 0.5B Instruct Q4_K_M do repositório
oficial, licença Apache-2.0, para uso apenas no ambiente de teste.

- Fonte: https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF
- Revisão: `9217f5db79a29953eb74d5343926648285ec7e67`.
- Arquivo: `qwen2.5-0.5b-instruct-q4_k_m.gguf`, 491.400.032 bytes.
- SHA-256 verificado: `74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db`.
- RSS após calibração: 553.242.624 bytes (aproximadamente 528 MiB).

Na calibração curta, o Qwen recusou indevidamente um pedido inofensivo de lista.
Esse resultado reforça que testar a orquestração não equivale a certificar a
qualidade de um modelo pequeno. A rodada com dependências avalia separadamente
o funcionamento do DAG e a utilidade do resultado final.

## Rodada 2: paralelismo seguido de consolidação

Modelos: Qwen 2.5 0.5B Q4_K_M e Gemma 4 E2B Q4_0, em CPU.
Duas tarefas independentes precedem uma terceira que recebe os dois resultados.

- Três tentativas concluídas em 137,45 segundos, incluindo carregamento.
- Pico da soma de RSS: 3,03 GiB; mínimo de RAM livre amostrada: 2,01 GiB.
- Ambos os modelos observados BUSY; troca para ECONOMICAL preservou reservas.
- Após o primeiro lote: duas tarefas completed e consolidação pending.
- A consolidação recebeu dois dependency_outputs, sem repetir as tarefas anteriores.
- PIDs preservados entre lotes; nenhuma recarga de modelo.
- Reservas e modelos liberados ao término; nenhum processo do teste permaneceu.

Resultado final real:

1. Ver e responder e-mails urgentes — alta, 20 minutos.
2. Planejar as prioridades do dia — alta, 30 minutos.
3. Revisar relatórios pendentes — média, 45 minutos.
4. Organizar a área de trabalho/mesa de estudo — alta, 40 minutos.
5. Limpeza rápida da cozinha — média, 15 minutos.
6. Arrumar o quarto e dobrar a roupa — baixa, 10 minutos.

### Limitações observadas

- O Qwen tentou chamar `recall` com nomes fictícios de workspaces, apesar do
  pedido sem ferramentas. A consulta falhou com `cross-workspace retrieval
  requires explicit intent`; nenhum resultado foi retornado. A proteção atuou.
- O Gemma respondeu além do escopo de sua subtarefa doméstica, incluindo trabalho.
- A consolidação é utilizável e tem seis tarefas, prioridades e durações, mas
  introduziu tarefas não presentes literalmente nas dependências. O handoff foi
  comprovado pelos snapshots; fidelidade semântica perfeita não foi comprovada.
- A validação padrão non_empty aceitou saídas com essas limitações. Os testes
  aprovam residência, concorrência, DAG, política e liberação; não certificam
  precisão nem obediência irrestrita dos modelos pequenos.

Evidência: `artifacts/reports/real-swarm-dependent-todo.json`. O modelo adicional
permanece somente no cache deste teste (491 MB), sem mudar o catálogo do usuário.
Scripts usados: `.cache/synapse/real-swarm-calibrate.py` e
`.cache/synapse/real-swarm-run.py`. Nenhum código de produção foi modificado.

## Correção de criação pelo chat — 28/10/2026

As duas rodadas anteriores usavam workers registrados pelo teste. Elas não
comprovavam o provisionamento automático solicitado pelo usuário. Esta rodada
começou sem workers e chamou `chat.submit_turn` com o comando em português:
“Faça um swarm para criar uma lista de 4 tarefas simples para organizar a manhã.”

Correções aplicadas:

- O comando explícito autoriza a escolha automática de uma equipe limitada.
  Pedidos que excedem os limites continuam sujeitos à confirmação da redução.
- Cada identidade temporária recebe seu próprio worker, vinculado à missão e
  à tarefa. Nenhum CONFIG persistente é criado para uma identidade efêmera.
- O executor usa a autoridade herdada do pai, restringe as ferramentas ao escopo
  temporário e não carrega a memória privada do pai. O resultado temporário só
  é concluído após a verificação da tentativa.
- Swarms originados pelo chat drenam rodadas prontas; a execução incremental
  dos Swarms existentes é preservada. Os resultados são devolvidos na conversa.
- Falhas de provisionamento desfazem a criação parcial. Ao encerrar a missão,
  os workers temporários são desabilitados e o contexto temporário é eliminado.
- A capacidade para identidades temporárias mede o volume de dados da execução.
  Uma unidade G: cheia e não utilizada não bloqueia mais a criação. A visão
  global de saúde continua informando essa unidade cheia.
- As rotas locais automáticas usam perfis de RAM/VRAM medidos. A reserva
  continua rejeitando falta de memória, slots ou perfis válidos.

Evidência: `artifacts/reports/real-swarm-chat-todo.json`, script
`.cache/synapse/real-swarm-chat.py`. Resultado observado: 2 agentes criados e
encerrados automaticamente; 2 tentativas verificadas e concluídas; Qwen 0.5B e
Gemma E2B simultaneamente BUSY; 81,91 segundos; mínimo de RAM livre 3,18 GiB.
Estado final NORMAL/ECONOMICAL, sem modelos nem reservas do teste. As duas
listas apareceram na resposta. A qualidade da lista do Qwen foi inferior à do
Gemma; essa prova certifica o fluxo, não a qualidade de qualquer tarefa arbitrária.

Para disponibilizar o fluxo no aplicativo, o Qwen já verificado foi copiado para
a pasta de modelos instalada e os dois perfis medidos foram acrescentados à
configuração local, com limite de 2 modelos. O modelo de conversa normal não foi
substituído. Foi guardada cópia da configuração anterior em
`artifacts/restore-points/swarm-chat-fix/system.yaml`.

A suíte `test_swarm_chat_execution_e2e.py` cobre chat sem workers prévios,
falha de inferência, rollback parcial, resultado vazio, execução em um slot e
agente pai sem permissão de leitura para tarefas somente de texto. A governança
de projetos continua obrigatória. O status global do backend permanece NOT READY.


### Verificação do executável entregue

O backend recompilado foi iniciado com perfil isolado e descoberta normal dos
modelos instalados, sem workers prévios e sem permissões de filesystem para o
agente pai. O teste usou `/api/frontend/conversations/open` e
`/api/frontend/conversations/{id}/turns/stream`, os mesmos endpoints da interface.
O comando foi aceito sem confirmação extra; criou e executou dois agentes,
devolveu duas saídas, desabilitou os workers e liberou as reservas. A política
ECONOMICAL foi persistida antes de iniciar o executável. Não restaram processos
de modelos deste teste. Evidência: `artifacts/reports/real-swarm-compiled-chat.json`.
O Gemma entregou uma lista útil; o Qwen produziu itens pouco relacionados ao pedido.
O comando de orquestração foi removido do objetivo enviado aos modelos.

Gates desta correção:

- Regressão final dos módulos afetados: **91 passed**, incluindo todas as falhas
  encontradas na rodada ampla. `artifacts/reports/swarm-fix-final-regression.txt`.
- Interface: **142 passed** em 16 arquivos.
- Ruff: aprovado; Mypy global: aprovado em 834 arquivos; diff check: aprovado.
- Builds do frontend, backend e launcher raiz: aprovados.
- Rodada ampla anterior às correções finais: **4644 passed, 5 failed, 5 skipped**;
  não é declarada como uma rodada global integralmente verde. As cinco falhas
  foram corrigidas e seus módulos foram repetidos na regressão final acima.
- Architecture suite executada na rodada combinada anterior: sem falhas
  arquiteturais. O único erro daquela rodada era a expectativa de execução de
  projeto sem vínculo RFC, corrigida para preservar a governança.

As missões antigas do perfil real não foram repetidas automaticamente. O teste
compilado não alterou o histórico de conversas do usuário.
