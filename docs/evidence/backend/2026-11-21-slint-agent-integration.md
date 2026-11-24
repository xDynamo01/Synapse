# Integração de conversa e tarefas no Slint

Windows x64, 21/11/2026. Alterações locais sobre `1d615b2`.

O cliente enviava somente `conversation_start` no chat, sem contexto ou pins
de Skills e sem controles de missões. O Core não incluía identidade da ARTEMIS
na conversa. A inferência bem-sucedida não comprovava execução de tarefas.

## Correções

- Identidade e limites da conversa definidos no Core.
- Restauração da última conversa, nova conversa, saúde periódica, eventos
  atualizados e erros visíveis na interface.
- Workspace ligado a cadastro de projeto, planejamento, consulta da proposta,
  aprovação pelo digest, execução, recibos e cancelamento de missões.
- Runtime dedicado de verificações detectado pelo iniciador local. Pacote
  com manifesto original disponível em `target/check-runtime`. Receita também
  reconstruída em `target/windows-check-python`.
- Revisão confere a fase final da receita aprovada. Validações de documentos
  terminam em `validate`, compilação Python em `compile` e suites em `test`.
  Antes, a revisão exigia `test` para todas as receitas, recusando JSON válido.
- Pedidos de tarefa aguardam ocupação transitória do modelo local.

## Evidências

- 25 testes de CLI de conversa, contexto, Skills, memória e recuperação
  passaram em `target/core-identity-tests-final.log`.
- Cinco testes de candidatos passaram em `target/agent-check-receipts-tests.log`.
- Oito testes do cliente passaram e quatro dependentes de ambiente ficaram
  ignorados no comando padrão em `target/desktop-agent-tests-final.log`.
- Conversa e tarefa pelo Slint com Core e provedor controlados passaram em
  `target/desktop-agent-execution-final.log`.
- O modelo local real respondeu `Meu nome é ARTEMIS.` pelo cliente em
  `target/desktop-agent-live-identity.log`.
- O modelo local real planejou, gerou, validou, revisou e integrou
  `agent_result.json` através dos callbacks do Slint. A leitura confirmou
  `{"agent":"ARTEMIS","executed":true}`. O recibo contém arquivo confirmado
  e estado `integrated` em `target/desktop-agent-live-task-final.log`.

O artefato real ficou em
`C:/Users/arthu/AppData/Local/Temp/synapse-live-agent-1d1fbe73f556488b91b74984b42bc8e4/workspace/project/agent_result.json`.

## Limites

O ícone de tarefa ao lado do chat abre o objetivo no Workspace. Pasta e proposta
ficam visíveis antes da aprovação e execução. O chat comum continua sendo
diálogo. Não existe seleção automática irrestrita de ferramentas nesse canal.

A seleção de contexto e Skills, atribuições MoM, edição Git e outros painéis
ainda precisam da migração completa ao Slint. A tarefa validada criou um
artefato novo em Workspace sem Git. Captura e reprodução de voz de ponta a
ponta continuam pendentes no cliente Slint.
