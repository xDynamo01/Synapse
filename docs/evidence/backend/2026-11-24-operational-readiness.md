# ProntidÃ£o operacional â€” software Windows

Retomada e entrega local: 2026-11-24. A validaÃ§Ã£o foi executada na branch `0.3-cleanroom`, com alteraÃ§Ãµes locais sobre `1d615b2514cba0c2c564317a2856ade4585ccd9a`, antes do commit e push de consolidaÃ§Ã£o na `0.3`. O ZIP descrito aqui Ã© um pacote local, nÃ£o uma nova release publicada. Este recibo cobre o runtime Windows atual; nÃ£o declara aceite fÃ­sico de Linux/macOS nem ensaio de reinÃ­cio ou perda de energia. A organizaÃ§Ã£o posterior do repositÃ³rio segue a [polÃ­tica de versÃµes](../../guides/github-versions.md).

## ImplementaÃ§Ã£o

| Grupo | CorreÃ§Ã£o e verificaÃ§Ã£o |
| --- | --- |
| Contratos | API Core v1, consulta `compatibility`, schema16 com identidade de migraÃ§Ã£o e validaÃ§Ã£o de estrutura. Fixture populado v15, recibos antigos, abertura repetida, schema futuro e restauraÃ§Ã£o incompleta foram exercitados. Worker negocia v5/v4, com inferÃªncia executada nas trÃªs combinaÃ§Ãµes antigo/novo do fixture preservado. |
| Isolamento | Estado e backups privados por usuÃ¡rio do Windows; criaÃ§Ã£o com ACL, handles de ancestrais, recusa de reparse points/hardlinks e proteÃ§Ã£o por proprietÃ¡rio. Contextos, ferramentas e missÃµes mantÃªm seus escopos. CanÃ¡rios sintÃ©ticos nÃ£o vazaram em recusas, eventos ou backups em texto. |
| Confiabilidade | Recibos idempotentes, recuperaÃ§Ã£o de publicaÃ§Ã£o, cancelamento, retomada, reconciliaÃ§Ã£o e reservas foram exercitados com falhas injetadas e morte de processos. O worker de voz ganhou JobObject para encerrar seus filhos apÃ³s morte do proprietÃ¡rio. |
| Observabilidade | Ledger de tentativas por lease, correlaÃ§Ã£o entre job/missÃ£o/grafo, duraÃ§Ã£o, fases, tokens reportados, amostras de RAM e diagnÃ³stico de GPU. `mission_plan_rejected` registra a regra estÃ¡tica do Core que recusou um plano, sem conservar sua saÃ­da bruta nos eventos. |
| Qualidade | Dataset de fronteiras com 16 casos rotulados em cinco classes; amostra de cinco fluxos com modelo real; missÃ£o real com dois arquivos dependentes. Valores medidos, denominadores e limites ficam separados dos testes de fixture. |
| Recursos | OrÃ§amento agregado inclui filhos, retries e planos anteriores de grafos manuais. Limites iniciados sÃ³ podem ser reduzidos. Tempo, chamadas, concorrÃªncia e indisponibilidade tÃªm recusa explÃ­cita. InferÃªncia remota permanece bloqueada. |
| DistribuiÃ§Ã£o | Slint, Core, manutenÃ§Ã£o, helpers, Python completo de inferÃªncia e runtime mÃ­nimo separado para checks LPAC. ZIP inventariado, hashes, configuraÃ§Ã£o limpa, atualizaÃ§Ã£o, downgrade recusado e restauraÃ§Ã£o seguida de rollback foram executados em instalaÃ§Ã£o descartÃ¡vel. |
| AutogovernanÃ§a | Proposta selada, revisÃ£o concreta do diff e aprovaÃ§Ã£o humana especÃ­fica, principal do SO, journal, publicaÃ§Ã£o e reversÃ£o. MissÃµes comuns nÃ£o podem registrar os fontes, executÃ¡veis ou arquivos de configuraÃ§Ã£o como projeto. Workspace separado sob a mesma pasta-base continua permitido. |
| OperaÃ§Ã£o | Arquitetura atual, matriz de contratos e runbooks em [runtime e operaÃ§Ã£o](../../guides/current-runtime-and-operations.md). DiagnÃ³stico de dependÃªncias nÃ£o importa ML nem baixa modelos. A configuraÃ§Ã£o de voz persistida dispensa variÃ¡veis do terminal. |

## Resultados executados

Recibos estruturados: [resumo do gate e artefatos](2026-11-24-readiness-validation.json), [evals com modelo local](2026-11-24-local-model-evals.json) e [compatibilidade dos workers](2026-11-24-worker-compatibility.json).

Os logs privados ficam em `.superpowers/readiness-20261122/`; usam fixtures descartÃ¡veis, sem credenciais reais.

- ApÃ³s o gate, removeu-se somente uma linha vazia no fim de `planner.rs`; o hash anterior foi reconstruÃ­do para comprovar essa diferenÃ§a. Os binÃ¡rios reconstruÃ­dos passaram novamente por instalaÃ§Ã£o, evals de modelo e fronteiras, compatibilidade dos workers e startup do executÃ¡vel entregue.
- Gate integral: Core, Python, Slint, distribuiÃ§Ã£o e checks nativos, com inventÃ¡rio de fontes antes/depois em `final-gate-aligned/gate.json`.
- Core: 141 testes padrÃ£o e nove gates nativos, incluindo compilaÃ§Ã£o/execuÃ§Ã£o isolada de Python e Rust, publicaÃ§Ã£o, reversÃ£o, recuperaÃ§Ã£o e dependÃªncias.
- Python: 47 testes executados, dois skips preexistentes e nenhuma falha na suÃ­te aceita.
- Slint: 23 testes padrÃ£o; trÃªs fluxos adicionais de interface exercitaram conversa, missÃ£o e grafo/Swarm confirmado. Os casos de admissÃ£o incluem preservaÃ§Ã£o do payload, cancelamento, respostas tardias e transiÃ§Ã£o de traduÃ§Ã£o para chat.
- DistribuiÃ§Ã£o: dez testes de guardas. O verificador instalado concluiu planejamento, geraÃ§Ã£o, check JSON em LPAC com runtime incluÃ­do, revisÃ£o, publicaÃ§Ã£o e leitura do resultado.
- Voz: health real do worker com `voice-runtime.json`, wake/STT/TTS disponÃ­veis e identidade `supertonic-3:F1`. NÃ£o capturou microfone nem reproduziu Ã¡udio. O teste sintÃ©tico de morte abrupta do proprietÃ¡rio comprovou encerramento do filho.
- Evals determinÃ­sticos: [16/16 aceitos](2026-11-24-readiness-evals-v1.json), zero falsos positivos/negativos nos denominadores publicados e zero vazamentos dos canÃ¡rios.
- Modelo real: Qwen2.5 Coder 7B Q4_K_M, contexto residente de 32768, saÃ­da mÃ¡xima 1400 e prazo de 120 s. Os cinco casos aceitos cobriram identidade, memÃ³ria nÃ£o referenciada, memÃ³ria explÃ­cita, traduÃ§Ã£o e projeto JSON verificado. O grafo real com `first.json` e `second.json` terminou `integrated`, com ambas as tarefas `passed`.
- Compatibilidade executada: Core anterior/worker atual, Core atual/worker anterior e ambos atuais concluÃ­ram inferÃªncia sintÃ©tica em loopback. O fixture anterior Ã© uma montagem de artefatos preservados schema15, nÃ£o uma release publicada certificada.

Os ensaios identificaram incompatibilidade de greeting, orÃ§amento separado indevidamente em grafos manuais, cancelamento tardio da voz, dependÃªncia de variÃ¡veis do terminal e divergÃªncia de cardinalidade no schema do planejador. Esses pontos foram corrigidos e retestados. Uma captura sintÃ©tica mostrou o modelo separando criaÃ§Ã£o e validaÃ§Ã£o do mesmo arquivo em duas tarefas; o Core recusou o plano sem efeitos. A instruÃ§Ã£o agora explicita um Ãºnico proprietÃ¡rio por arquivo, inclui exemplo vÃ¡lido de plano simples e mantÃ©m a recusa estrita. Resultados anteriores rejeitados nÃ£o sÃ£o apresentados como aprovaÃ§Ã£o ou publicaÃ§Ã£o bem-sucedida.

A rodada integral foi repetida antes do push, sem alteração dos fontes durante a execução: [gate pré-push](2026-11-24-pre-push-gate.json). As cinco suítes passaram, incluindo os nove testes nativos.

## Pacote aceito

VersÃ£o local `0.3.1`, Windows x64:

| Artefato | SHA-256 |
| --- | --- |
| ZIP `target/operational-distribution-accepted/synapse-0.3.1-windows-x64.zip` | `66de6910a81dfbfa7b2160315442e899a56a168ca4eee8877f37321228a87afe` |
| Core instalado | `9aa0ef6f0791fbbe8b9fdbab1f538198d16c602ba903da2187b203427fecb4b0` |
| Slint de entrega | `6d9e824950563f6048d2257c4c3c9323d47f8e27235bebddf6ea78814bedc9df` |
| Python do checker LPAC | `746b19e096cf1cab86afb704ed974763961452ba0470a945c54b974602f0e6a0` |

`windows-installed-final.log` registra instalaÃ§Ã£o schema15, snapshot DPAPI, atualizaÃ§Ã£o para16, memÃ³ria preservada, worker incluÃ­do, missÃ£o JSON, Slint conectado, pacote adulterado recusado, downgrade incompatÃ­vel recusado, restauraÃ§Ã£o para estado/configuraÃ§Ã£o novos e rollback do programa compatÃ­vel com o estado restaurado. SHA obtido junto de um arquivo comprova consistÃªncia; autenticidade exige origem independente confiÃ¡vel.

O `Synapse.exe` da raiz foi atualizado por substituiÃ§Ã£o do arquivo jÃ¡ verificado e seu hash confere com o Slint do pacote. O startup do executÃ¡vel entregue passou. TambÃ©m foi validado o perfil real do aplicativo: snapshot DPAPI antes da mudanÃ§a, migraÃ§Ã£o15â†’16, histÃ³rico e memÃ³ria preservados, `quick_check=ok` e conexÃ£o do aplicativo ao Core. O recibo detalhado e o backup com dados do perfil sÃ£o privados; nÃ£o foram copiados para a documentaÃ§Ã£o pÃºblica. A cÃ³pia anterior do executÃ¡vel foi preservada.

Rust 1.96.0 estÃ¡ fixado em `rust-toolchain.toml`. A atualizaÃ§Ã£o automÃ¡tica da pasta `stable` para1.100 foi detectada pela recusa do runner, sem afrouxar hashes. A versÃ£o exigida foi instalada em paralelo e a configuraÃ§Ã£o local passou a usar sua pasta versionada; o compilador padrÃ£o do usuÃ¡rio foi preservado.

## Limites e pendÃªncia real

O limite de usuÃ¡rio Ã© a conta autenticada pelo SO. Perfis nÃ£o sÃ£o autenticaÃ§Ã£o de servidor. A proteÃ§Ã£o por handles foi exercitada no Windows; as rotas Unix nÃ£o recebem a mesma certificaÃ§Ã£o. Recursos de voz e navegador com dependÃªncias externas sÃ£o diagnosticados como configuraÃ§Ã£o necessÃ¡ria quando ausentes; presenÃ§a de arquivo nÃ£o prova execuÃ§Ã£o. O pacote padrÃ£o nÃ£o contÃ©m automaticamente todos os modelos de voz, perfis de navegador nem modelos do LM Studio.

Um orÃ§amento estrito de tokens recusa admissÃ£o sem limite confiÃ¡vel da tokenizaÃ§Ã£o de entrada; RAM/VRAM de provedor desconhecidas tambÃ©m recusam limites finitos correspondentes. Amostras globais de GPU nÃ£o sÃ£o consumo por missÃ£o. ReutilizaÃ§Ã£o de modelo nÃ£o Ã© cache de respostas. Os evals sÃ£o amostras delimitadas, nÃ£o promessa de acerto em todos os projetos ou de ausÃªncia universal de falhas.

**ReinÃ­cio real do computador/interrupÃ§Ã£o abrupta de energia: nÃ£o realizado, dispensado expressamente pelo usuÃ¡rio em 2026-11-24.** O usuÃ¡rio informou nÃ£o possuir ISO ou VM de teste e autorizou encerrar o trabalho apÃ³s validar o restante. Os testes comprovam morte de processos e recuperaÃ§Ã£o dos pontos injetados, nÃ£o falta de energia. A inspeÃ§Ã£o encontrou Hyper-V e Windows Sandbox desativados e nenhum ambiente descartÃ¡vel adequado disponÃ­vel. A mÃ¡quina de trabalho nÃ£o foi desligada/reiniciada para forÃ§ar esse ensaio. O checklist conserva essa caixa desmarcada.

A revisÃ£o automÃ¡tica bloqueou a limpeza de uma pasta de estado temporÃ¡rio criada para os testes, informando somente bloqueio por polÃ­tica. Ela foi preservada em `.superpowers/readiness-20261122/retained-native-test-state`; nÃ£o foi usada para dados de produÃ§Ã£o.

## ReproduÃ§Ã£o

Com o Python do checker e as quatro pastas do compilador/SDK configuradas conforme os runbooks:

```powershell
py -3.14 -B tools/readiness/run_gate.py --include-native --output target/readiness-gate
py -3.14 -B tools/readiness/run_evals.py --binary target/release/synapse-backend.exe --output target/boundary-evals.json
py -3.14 -B tools/readiness/run_model_evals.py --binary target/release/synapse-backend.exe --model qwen2.5-coder-7b-instruct --check-runtime target/check-runtime/runtime/python.exe --output target/model-evals.json
py -3.14 -B tools/release/verify_windows_install.py tools/release/install-windows.ps1 target/distribution-schema15-fixture-gryrxgau/legacy-schema15-fixture.zip target/operational-distribution-accepted/synapse-0.3.1-windows-x64.zip
```

O modelo deve estar residente com32k antes do eval. Os fixtures, runtimes e modelos externos precisam existir; os comandos nÃ£o os substituem por resultados simulados.
