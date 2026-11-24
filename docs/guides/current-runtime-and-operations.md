# Runtime atual e operação local

Referência das fontes em 2026-11-22. O charter continua vinculante. Este índice descreve componentes executados; não substitui os recibos de aceite nem declara validação física de outras plataformas.

## Caminho executado

O cliente nativo `backend/desktop-slint` envia contratos Core v1 pela ponte local. `core.rs` mantém a única conexão escritora SQLite e os recibos idempotentes. `intake.rs` registra a entrada e escolhe conversa, capacidade especializada ou missão. `context.rs` seleciona somente referências explícitas; o histórico recente pertence à conversa escolhida. Conteúdo de páginas, memória, Skills e modelos não concede autorização.

`planner.rs` produz propostas sem efeitos. Missão aprovada recebe política selada, tarefas e verificações em `task_graph.rs`, `mission_run.rs` e `integration.rs`. `orchestration.rs` mantém reservas e as dimensões independentes NORMAL/SWARM e RESPONSIVE/ECONOMICAL. Swarm requer consentimento e seus agentes são temporários. O modelo não recebe uma API para autorizar suas próprias ferramentas.

`worker.rs` supervisiona o processo Python e negocia worker v5 ou v4. `backend/python/synapse_ai/providers.py` acessa somente provedores locais permitidos; `model_ownership.py` controla instâncias pertencentes ao Synapse e preserva as do operador. O Python confiável de inferência necessita sockets; ele é distinto do runtime mínimo utilizado para executar código gerado em LPAC. O runtime de inferência não é uma prisão de código hostil.

`checks.rs` e `runner/` executam receitas fixas com identidade e limites verificados. `tools.rs`, `projects.rs` e os brokers controlam recursos exatos e publicação. O navegador usa integrações existentes com quarentena e permissões por missão; páginas e saídas externas continuam dados não confiáveis. O fluxo `self_change.rs` exige revisão concreta do diff e autorização humana específica antes de alterar o próprio produto; missão genérica não substitui essa autorização.

## Contratos e persistência

| Fronteira | Contrato | Recusa/limite |
| --- | --- | --- |
| Slint → Core | API JSON v1; consultar `compatibility` | Campos desconhecidos, versão e tamanho inválidos recusados; `request_id` identifica recibo, reutilização divergente é conflito |
| Core → Python | worker v5 com `operational_metrics_v1`; v4 legado negociado | v4 mantém sua forma anterior; métricas ausentes são desconhecidas |
| Missão/ferramenta | contrato v1, digest e recursos exatos | Aprovação não amplia modelo, recurso, ação ou política selada |
| SQLite | schema16, ledger `synapse-readiness-v1`, WAL/FULL | Versão futura, formato incompatível ou restauração incompleta impedem abertura |
| Backup | envelope v1, snapshot SQLite consistente, DPAPI CurrentUser | Chave do mesmo usuário necessária; sem restauração por cima de estado existente |
| Pacote | manifesto v2 com inventário/hash e matriz de compatibilidade | Digest deve vir de origem confiável independente; hash fornecido junto do arquivo não autentica a origem |

Erros são dados estruturados com `code` e mensagem limitada. As operações novas de manutenção retornam códigos sem ecoar conteúdo privado. Eventos têm envelope v1, cursor e conteúdo específico por operação. Métricas operacionais não contêm prompts. Métricas de GPU globais não equivalem a VRAM por missão; ausência de contador não é zero medido. Inferência remota permanece desativada.

## Fronteira de usuário e retenção

O produto atual atende a um usuário autenticado pelo sistema operacional. ACLs privadas e DPAPI protegem contra outras contas; rótulos de perfil, agente, conversa ou projeto não são credenciais de servidor. Um processo comprometido executado como o mesmo usuário está fora dessa fronteira. A implantação futura em servidor requer autenticação e autorização próprias antes de aceitar clientes de outras contas ou da rede.

O endurecimento por handles e fixação dos diretórios foi implementado e exercitado no Windows. As rotas Unix usam permissões do proprietário e verificações de caminho; não possuem a mesma garantia contra troca concorrente de ancestrais. Backup protegido recusa operação onde não há provedor de chave implementado. Builds de outras plataformas não recebem, por extensão, o aceite de segurança do Windows.

Chats, memória canônica, recibos e journals são estado persistente deliberado. Backup contém esse estado e a configuração JSON selecionada; não contém automaticamente projetos nem perfis completos de navegador. Temporários de teste e evidências usam dados sintéticos. Arquivos de projeto, histórico e evidência não são apagados automaticamente por uma rotina de manutenção. O descarte deve preservar journals necessários à recuperação; apagar o banco para resolver um erro não é procedimento de operação.

## Runbooks

| Sintoma | Procedimento |
| --- | --- |
| `state_in_use` | Identificar o Core que possui o estado e encerrá-lo normalmente. Não remover o lock para forçar um segundo escritor. Executar manutenção após o término. |
| `unsupported_storage_version` / `incompatible_storage_schema` | Preservar o estado. Usar executável compatível ou restaurar snapshot anterior em diretório novo e apontar a versão antiga para ele. Não reduzir `user_version` manualmente. |
| `state_restore_incomplete` | Preservar o destino parcial para diagnóstico. Reexecutar a restauração validada em outro destino novo. Não remover o marcador para aceitar bytes incompletos. |
| Backup | Parar o Core dono do estado e usar `synapse-maintenance backup --state-dir ESTADO --output NOVO_ARQUIVO --config-root CONFIG`. Proteger também o perfil/chave DPAPI do usuário; este backup não é portável entre contas. |
| Restaurar | `synapse-maintenance restore --archive ARQUIVO --state-dir NOVO_ESTADO --config-root NOVA_CONFIG`. O workspace original precisa continuar disponível; a vinculação do estado ao workspace é preservada. Validar antes de trocar os caminhos do aplicativo. |
| Provedor indisponível / modelo não encontrado | Executar `diagnose.py`; conferir endereço local, modelo e recursos. Não substituir silenciosamente um modelo escolhido manualmente nem encaminhar prompts a serviços remotos. |
| `invalid_mission_plan` | Consultar o evento correlacionado `mission_plan_rejected`: ele informa a regra estática que recusou o resultado. Não publicar nem aprovar JSON parcial. Um arquivo possui um único responsável; suas validações são checks desse responsável, não uma segunda tarefa proprietária. |
| Reserva incerta | Consultar orquestração e tentativa; reconciliar com o provedor. Preservar instâncias do operador; não descarregar todas as instâncias para liberar uma reserva. |
| Ferramenta indisponível | Conferir runtime de checks separado e compilador/SDK pinados. Recusa de ferramenta não deve virar aprovação fictícia de QA. |
| `unsupported_rust_toolchain` | O runner exige Rust 1.96.0 e hashes fixos. Instalar `rustup toolchain install 1.96.0 --profile minimal` e apontar `native-toolchain.json` para a pasta versionada `1.96.0-x86_64-pc-windows-msvc`. Não usar a pasta mutável `stable` nem remover a verificação de hashes. `rust-toolchain.toml` fixa a versão de desenvolvimento sem alterar o padrão global do usuário. |
| Publicação interrompida | Consultar `mission_recovery_inspect` e resolver somente efeitos cuja identidade/digest sejam reconhecidos. Modificações externas exigem análise; não sobrescrever para forçar o estado final. |
| Autoalteração interrompida | Consultar journal com o contexto/digest original; recuperar ou reverter pelo fluxo dedicado. Bytes desconhecidos exigem nova confirmação humana concreta. |
| Atualização | Verificar digest de origem independente, manter snapshot compatível e instalar em versão separada. Rollback do programa não implica downgrade do banco; restaurar estado compatível em destino novo. |
| Sem GPU ou pouca memória | Tratar diagnóstico como indisponível/insuficiente, manter uma instância quando permitido e reduzir carga explicitamente. Não relatar contadores inexistentes como uso zero. |

## Gate de versão

Executar `tools/readiness/run_evals.py` contra o Core escolhido e guardar seu hash. Executar os testes Core incluindo a campanha de falhas, testes Python, cliente e a aceitação do pacote atual com runtime incluído. Vincular recibos ao mesmo artefato distribuído. Os critérios completos ficam na [auditoria operacional](../superpowers/plans/2026-11-22-auditoria-prontidao-operacional.md), e os resultados nas evidências datadas.

Desligamento limpo, morte do processo, reboot e interrupção abrupta são ensaios diferentes. Não desligar a máquina de trabalho para preencher uma caixa. Reinício/perda de energia exige ambiente descartável apropriado e recibo próprio. Windows, Linux e macOS têm aceites físicos separados. A existência de builds ou testes determinísticos não prova funcionamento de todo tipo de projeto nem ausência universal de vulnerabilidades.
