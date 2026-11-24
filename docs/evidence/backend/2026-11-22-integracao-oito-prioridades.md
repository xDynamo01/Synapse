# Aceite Windows — integração das oito prioridades

Data: 2026-11-22. Plataforma: Windows x64. Base Git: `1d615b2514cba0c2c564317a2856ade4585ccd9a` e árvore de trabalho identificada pelos hashes abaixo. As alterações locais anteriores foram preservadas.

Os 27 itens do [checklist A–E](../../superpowers/plans/2026-11-22-auditoria-conexoes-e-backlog.md) foram conectados e verificados. Este aceite cobre o Core e os novos callbacks Slint; as releases publicadas anteriormente constituem registros de revisões anteriores.

## Matriz de aceite

| Prioridade | Conexão entregue | Verificação |
| --- | --- | --- |
| 1. Entrada e roteamento | `input_submit` persistido encaminha conversa, especialista e missão. Voz comum reutiliza a decisão; o tradutor ativo conserva sua semântica. Escolha manual compatível prevalece. | `intake_cli`: saudação, pergunta, especialização, continuidade, idempotência e saída truncada. `ai_cli`: voz comum e tradução bidirecional. |
| 2. MoM e Swarm | NORMAL/SWARM e RESPONSIVE/ECONOMICAL são independentes. Consentimento e transições são vinculados à missão; atividade só aparece após início real. | Testes `orchestration`, callback Slint de grafo com Swarm e ECONOMICAL; falha, revisão e retomada restauram o regime correto. |
| 3. Conversa, contexto e memória | Handoff selado transporta objetivo, histórico recente, Skill, referências exatas com revisão/digest e resultados anteriores para planejamento, geração e revisão. | `intake_cli` e `ai_cli`: referências entre projetos, referências inválidas, continuação, histórico longo identificado como abreviado e isolamento da aprendizagem. Saudações após missão continuam sendo conversa. |
| 4. Planejamento e execução | RFC → plano → tarefas seladas com dependências, prioridade, entregas e checks. Aprovação do conjunto precede execução. Pausa drena a tarefa ativa; retomada e cancelamento preservam o journal. | `task_graph_cli`: tarefas reais, pausa/retomada, dependente bloqueada até publicação verificada, falha e nova revisão com tentativa de autoridade idêntica. `project_check_cli`: recuperação e edição Git com restauração. |
| 5. Modelos e ferramentas | Admissão e reservas duráveis, propriedade por tentativa, exclusão por provedor entre estados independentes, preservação de instâncias do operador e reconciliação após interrupção. Ferramentas conservam seus limites e permissões. | 23 testes Python; testes `orchestration`; encerramento abrupto do Core; indisponibilidade explícita; compilação e testes nativos Rust/Python em LPAC. |
| 6. Validação e replanejamento | Pré-check, revisão independente, publicação e pós-check participam da decisão. Dependências entram somente para leitura nos testes e na revisão; recibos vinculam seus digests. Nova tentativa conserva o contrato e exige aprovação da revisão. | Candidato inválido não é publicado. Importação Python de módulo predecessor funciona. Alterar bytes/identidade ou adulterar recibos invalida a dependência. Check e revisão reprovados bloqueiam a sequência. |
| 7. Interface e preferências | Conversa e Workspace usam o Core. Seleções e políticas persistem; rota, modelo, missões, tarefas, confirmações, bloqueios e erros derivam das respostas reais. | Três fluxos pelos callbacks Slint, restauração das preferências após reabrir o Store, compilação do cliente eframe e inicialização do executável atualizado. |
| 8. Observabilidade e integração | Entradas, decisões, handoffs, reservas, tarefas, estados e falhas têm IDs correlacionáveis. Os eventos não precisam expor o conteúdo das conversas. | Concordância entre callbacks, Core, worker, banco, journals e arquivos do Workspace; testes com provedor controlado e inferência local real. |

## Execução observada

- Core: 109 execuções aprovadas na regressão com injeção controlada de falhas e nos gates nativos, incluindo os testes inicialmente marcados para execução com ferramentas locais configuradas.
- Após acrescentar o diagnóstico de limite de saída: `ai_cli` 25/25 e `intake_cli` 1/1 aprovados.
- Python: 23/23 testes de protocolo e propriedade do provedor aprovados.
- Slint: 9/9 testes comuns; três fluxos com Core release pelos callbacks reais aprovados: conversa, missão simples com Swarm, grafo dependente com Swarm e ECONOMICAL.
- Inferência local real, Qwen2.5 Coder 7B Q4_K_M com contexto 32768: identidade ARTEMIS, missão JSON, missão Rust e duas tarefas JSON dependentes concluíram geração, verificações, revisão, publicação e leitura do resultado.
- O grafo real publicou `first.json = {"agent":"ARTEMIS","step":1}` e `second.json = {"step":2,"previous_step":1}`; ambas as tarefas encerraram em `passed` e o grafo em `integrated`.
- Um candidato Rust gerado com sintaxe inválida foi rejeitado pelo compilador antes da publicação. A tarefa posterior com fonte Rust explícita passou pelo aplicativo, sem as quatro variáveis de ferramentas presentes na sessão: o iniciador leu a configuração local validada.
- `Synapse.exe` da raiz foi substituído pelo aplicativo Slint otimizado e passou na inicialização automática em estado isolado, com saída 0. Seu hash coincide com o build release.

As verificações de arquivos, JSON, TOML, CSV, SVG, Markdown, VTT, níveis de jogo e manifestos continuam usando receitas fixas. A configuração Rust do aplicativo lê apenas quatro pastas locais autorizadas em `%LOCALAPPDATA%/Synapse/native-toolchain.json`; ela não admite comandos ou nomes arbitrários de ferramentas. Os pins do compilador e o isolamento permanecem no Core.

O limite de saída é tratado como `provider_output_limit`, sem aceitar JSON parcial ou transferir raciocínio interno para o plano. No ensaio com Qwen3.5, uma resposta consumiu seu limite sem concluir o plano e foi rejeitada; o Qwen de código instalado foi usado no aceite final. O adaptador do Synapse usa a [API compatível do LM Studio](https://lmstudio.ai/docs/developer/openai-compat/chat-completions) somente em loopback; os recibos de execução são produzidos pelo Synapse.

## Reprodução

Os logs e recibos desta execução estão em `.superpowers/integration-20261122/`. Os cenários verificáveis ficam em `backend/core/tests/intake_cli.rs`, `task_graph_cli.rs`, `project_check_cli.rs`, `backend/python/tests/test_worker.py`, `backend/desktop-slint/src/main.rs` e `tools/verify-desktop-slint.ps1`.

```powershell
cargo test --locked -p synapse-core --features test-fault-injection
# Com o runtime Python dedicado e as quatro pastas Rust/VC/SDK configuradas:
cargo test --locked -p synapse-core --features test-fault-injection -- --ignored --test-threads=1
py -3.14 -m unittest discover -s backend/python/tests -p test_worker.py
cargo test --locked -p synapse-desktop-slint
$env:SYNAPSE_CORE_EXECUTABLE = (Resolve-Path target/release/synapse-backend.exe).Path
pwsh -File tools/verify-desktop-slint.ps1
```

O script verifica o Core escolhido em uma cópia privada por execução, preservando a possibilidade de recompilar enquanto o aplicativo está em uso. Os ensaios de falha deliberada não concedem rede aos testes nem ampliam os caminhos autorizados.

## Artefatos entregues

| Artefato | SHA-256 |
| --- | --- |
| `Synapse.exe` / `target/release/synapse-desktop-slint.exe` | `E3412D07A8BD1EA251962E41665218BE2B91E9128EA9CF3D3C0A722C827E27C6` |
| `target/release/synapse-backend.exe` | `9EC2C724E0014405C61EF4C387E70CB3F9CFEC7DABEF96D06E3DBAC6AD58E493` |

A cópia anterior do executável foi preservada em `.superpowers/integration-20261122/previous-Synapse.exe`.

## Identificação das fontes

| Arquivo | SHA-256 |
| --- | --- |
| `Cargo.toml` | `2A982FA9A6E73D9EB4FBB8E91C11CC86172DCA5BC6CE92FD1C5DAFCD57BC22C2` |
| `Cargo.lock` | `D65FC88050FC374FFCC699818B52B91A29F906606FD7E08151063D2571854FC3` |
| `backend/core/src/intake.rs` | `3FF2DC3B22C4ECB5735F4FAF297E141840B485FEDA1EE3AB8672CC0FB6F968F8` |
| `backend/core/src/orchestration.rs` | `4182C5D09FE04CD3359A9585BDE3594C9D115AE91FF2FF3E270FAB5E0CBAEBB6` |
| `backend/core/src/task_graph.rs` | `F5F34CBEBB613DB5B79A597F262F58D82DE326CC09BEC52E8E0502E984404547` |
| `backend/core/src/core.rs` | `0EE9D5A68007822EC5FEAA199D39C5C57BC0C17AF96C2D995A2470205F86037A` |
| `backend/core/src/contracts.rs` | `8D77D1DA9EAA46B9E5A10AB9669CB9B9D1B7ED4D03B82E537084886D7A8C16EC` |
| `backend/core/src/checks.rs` | `BA389791FA4052AFA3F18002FD546D183E3E1F7DA0403F99A775822264D2CDD2` |
| `backend/core/src/planner.rs` | `EB86DA070F1A4B4E5254B26A2A807D89666051311B204A588F2B8E198DD022E3` |
| `backend/core/src/mission_run.rs` | `6AC4A3AA096EB28D92226A13B12F2FFE96CFBDB0F99AE7795EE1D04F889FC29D` |
| `backend/core/src/worker.rs` | `199480C3E8560187E0D1FED0512BE6DE148FD01125D658EE0395138EDA753424` |
| `backend/desktop-slint/src/main.rs` | `FFEC807FAB74DA538560861C7628BBF0E24A4D3848007AEA2BE8BA78C1084056` |
| `backend/desktop-slint/src/session.rs` | `908CE6599FCBBC0CC42674D1E10E3C0E20FA3F376646A3DC4157CE2AB104A679` |
| `backend/desktop-slint/src/local_runtime.rs` | `DA8721A9DD2010FAB1D218438C405C63103581B7F4B093D634161A13533C59B2` |
| `backend/desktop-slint/ui/app.slint` | `DCAFE1090E3789F514BEB010C26E3A5D25649173510D23C9FB2DB5A72351E12F` |
| `backend/python/synapse_ai/providers.py` | `A4F70AD90C39390634A5FABDC703B3E3DCB83F4E6E9DA3C91E15AB309B6CAD4D` |
| `backend/python/synapse_ai/model_ownership.py` | `9F7D184D80845AAD1B915FF078224DE85A454107B76DDBF8C9E30E9BCFADE818` |
