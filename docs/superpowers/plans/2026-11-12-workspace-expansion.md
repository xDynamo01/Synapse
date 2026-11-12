# Etapa 12 — Ampliação do Workspace

- [x] Registrar o vínculo entre `project:<id>`, pasta canônica e identidade
   física. Usar o broker para observar a pasta e rejeitar substituições.
   Validar consulta por escopo exato e persistência pelo CLI do Core.
- [x] Encaminhar cada missão pelo projeto que ela identifica. Fixar a identidade
   no planejamento e verificar na aprovação, execução, recuperação e ferramentas.
   A escolha do projeto pertence ao cliente. A memória continua por referência
   explícita e o Core permanece o único dono do estado.
- [x] Adicionar integração Git local isolada, com base fixada, diff revisável,
   verificação de alterações concorrentes, testes e reversão verificável.
   Operações remotas exigem autoridade expressa no contrato da missão.
- [x] Acrescentar adaptadores de build, testes e ferramentas por domínio. Validar
   um projeto existente e registrar os recibos e limites de cada adaptador.

O [Documento de Decisões](../../specs/2026-11-06-synapse-0.3-decision-charter.md)
rege o escopo do projeto, a memória por referência, o broker e os limites de
execução. A primeira entrega usa a identidade NTFS já verificada no broker.

## Registro inicial validado no Windows x64

O teste `project_bindings_survive_restart_and_detect_substitution` do CLI
registrou dois projetos no mesmo Core e consultou ambos após reinício. O
registro recusou compartilhar a mesma pasta entre escopos, trocar o vínculo
existente e reaproveitar um caminho cuja pasta foi substituída. A leitura
com referência de memória divergente foi recusada e a consulta com escopo
exato funcionou. A migração aditiva mantém os registros anteriores.

A [evidência de conclusão](../../evidence/backend/2026-11-12-workspace-expansion.md)
registra a missão Git real e os testes de conflito, reversão e entregáveis.
