# Synapse 0.3 no Windows — distribuição atual

Referência vinculante: [Decision Charter](../specs/2026-11-06-synapse-0.3-decision-charter.md), PL-001–006, SE-001–006 e QA-001–003.

O pacote v2 inclui Slint, Core, manutenção, analisadores de imagens/páginas, módulos Python, CPython 3.14 completo para workers e um runtime separado para checks de código gerado em LPAC. Recursos visuais Slint estão incorporados ao executável. Modelos, Chromium, dependências opcionais de voz e ferramentas de projeto são capacidades externas; a ausência aparece como indisponibilidade. Nenhum estado pessoal ou credencial entra no ZIP.

## Gerar e verificar

```powershell
cargo build --locked --workspace --release
$pythonRoot = & py -3.14 -c 'import sys; print(sys.base_prefix)'
py -3.14 tools/release/package.py build --version 0.3.1 --output target/distribution --python-runtime $pythonRoot --check-runtime target/check-runtime
py -3.14 tools/release/package.py verify $zip --trusted-sha256 $trustedDigest
```

O manifesto v2 publica API Core 1, protocolos worker 4/5, SQLite 0–16, frontend Slint e inferência remota desativada. Inclui hashes de cada arquivo e inventário da árvore fonte com modificações locais e fontes não commitadas. O fingerprint identifica fontes; não prova sozinho que o executável foi compilado delas. Registre compilação e smoke do artefato exato. ZIPs de entradas idênticas têm ordenação, metadados e timestamps fixos; isso não afirma compilação binária reproduzível.

`--python-runtime` exige CPython 3.14 completo, com socket, SSL e SQLite. A cópia usa uma lista fechada de executáveis/bibliotecas, DLLs e stdlib, excluindo site-packages, caches e `.pth`. Não use um ambiente virtual.

`--check-runtime` exige o runtime mínimo separado, com inventário e revisões CPython/dependências fixadas por `tools/runner/build_windows_python.py`. O CI compila essas revisões. O starter usa `SYNAPSE_CHECK_PYTHON_EXECUTABLE` para esse runtime. O runtime mínimo não serve ao worker confiável de rede; sua ausência de socket é intencional.

## Instalar e diagnosticar

Use PowerShell 7. Obtenha o instalador e `distribution-common.ps1` de uma origem confiável, por exemplo um checkout revisado fixado numa revisão. Não execute primeiro um script extraído de um ZIP ainda não autenticado. ZIP e hash da mesma origem desconhecida não autenticam nada. `TrustedSha256` deve vir de canal independente confiável ou de uma release/revisão cuja origem foi verificada; o arquivo `.sha256` sozinho detecta corrupção.

```powershell
& $trustedInstaller -Package $zip -TrustedSha256 $trustedDigest -InstallRoot $installation -StateRoot $state
$active = (Get-Content (Join-Path $installation 'active.json') -Raw | ConvertFrom-Json).current
$programs = Join-Path (Join-Path $installation 'versions') $active
& (Join-Path $programs 'start-windows.ps1') -InstallRoot $installation -StateRoot $state -Workspace $workspace -Diagnose
& (Join-Path $programs 'start-windows.ps1') -InstallRoot $installation -StateRoot $state -Workspace $workspace
```

O starter verifica o inventário instalado, usa o Python empacotado e conecta Slint a um Core explícito. Não procura Python pelo terminal, inicia LM Studio ou carrega modelos automaticamente. `-Python` é um override explícito, necessário para um pacote legado sem runtime. `-ConfigRoot` seleciona a configuração restaurada, incluindo `native-toolchain.json` validado. `-Verify` inicia Core e Slint em smoke sem inferência; execute somente em estado e Workspace descartáveis.

`-Diagnose` é somente leitura: dependências, porta local do provedor, ferramentas, RAM medida e contador GPU quando disponível. Porta aberta não prova modelo carregado. GPU/contador indisponível permanece desconhecido, nunca zero medido. Sem carga definida, suficiência é `not_evaluated_no_workload`. O relatório não inicia provedores nem baixa/carrega modelos.

O runtime Python do Core inclui a biblioteca padrão e é separado do checker LPAC. Ele não copia o `site-packages` do ambiente de desenvolvimento. Voz e navegação complexa têm dependências próprias: o diagnóstico mostra `SYNAPSE_VOICE_PYTHON`, presença dos pacotes e modelos em `SYNAPSE_VOICE_MODELS`, e Playwright/cache Chromium quando disponíveis. Presença de arquivo não certifica integridade nem execução; `external_setup_required` não deve aparecer como capacidade pronta. O diagnóstico não instala esses pacotes nem importa os runtimes de ML para testar sua presença.

Para persistir um ambiente de voz já provisionado, crie `voice-runtime.json` na pasta indicada por `-ConfigRoot` (padrão `%LOCALAPPDATA%/Synapse`) com somente os campos `python` e `models`, ambos caminhos absolutos locais. `python` aponta para `python.exe` do ambiente de voz; `models` contém os pacotes locais `whisper-base` e `supertonic-3`. Exemplo estrutural:

```json
{"python":"C:\\caminho\\voz\\Scripts\\python.exe","models":"C:\\caminho\\voice-models"}
```

O arquivo não aceita comandos, argumentos ou chaves adicionais. O cliente rejeita caminhos ausentes, relativos e com reparse points; também rejeita JSON inválido ou maior que 16 KiB. `SYNAPSE_VOICE_PYTHON` e `SYNAPSE_VOICE_MODELS` continuam como overrides explícitos e não são necessários quando o arquivo está configurado. As opções só entram no processo filho; o aplicativo não modifica o ambiente global. O worker inicia sem escrever caches Python na instalação. O diagnóstico lê o mesmo arquivo; configuração inválida produz indicação de setup, sem executar o caminho configurado. Backup/restauração da pasta de configuração inclui esse JSON, mas não copia automaticamente ambientes Python nem os modelos apontados.

No Windows, o worker de voz pertence a um JobObject privado com encerramento dos processos ao fechar seu proprietário. Nenhuma operação de voz é enviada antes da associação; se a supervisão não puder ser estabelecida, o processo recém-criado é encerrado e o início é recusado. O teste sintético de morte abrupta do proprietário não usa microfone nem ML. O teste ignorado `persisted_voice_runtime_starts_real_worker_health` verifica o bootstrap real com a configuração e os modelos locais existentes, sem abrir dispositivos de áudio; ele não equivale a um teste de reconhecimento ou síntese.

## Atualizar, fazer backup e reverter

Feche o Synapse. Faça backup consistente antes da atualização:

```powershell
& $maintenance backup --state-dir $state --output $backup --config-root $configuration
```

O snapshot inclui WAL e é protegido para o usuário Windows atual. Copiar somente `core.sqlite3` aberto não prova backup válido. Preserve arquivo e recibo fora da pasta de versões. Execute o instalador com o novo ZIP autenticado e o mesmo `-StateRoot`; ativação ocorre após hashes, inventário e compatibilidade. Locks impedem atualizar pelo starter aberto ou enquanto outro Core possui o estado. A cópia já instalada também é reverificada.

```powershell
& $trustedInstaller -Rollback -InstallRoot $installation -StateRoot $state
```

Rollback revalida a cópia anterior e o manifesto registrado na ativação. Pacotes legados sem `format` continuam instaláveis, com teto conservador SQLite 15. Estado em 16 recusa rollback para esse pacote sem alterar ponteiro ou banco. Uma instalação antiga sem recibo de manifesto precisa ser reinstalada do ZIP autenticado antes de servir de destino de rollback.

Para recuperar o programa anterior com dados antigos, preserve o estado atual e restaure para **novas pastas**:

```powershell
& $maintenance restore --archive $backup --state-dir $restoredState --config-root $restoredConfig
& $maintenance inspect --state-dir $restoredState
& $trustedInstaller -Rollback -InstallRoot $installation -StateRoot $restoredState
```

Passe `$restoredState` em `-StateRoot` e `$restoredConfig` em `-ConfigRoot` no starter. Backup DPAPI não é transferência entre usuários. O instalador não restaura nem reduz schemas automaticamente.

## Evidência executável

```powershell
py -3.14 -m unittest discover -s tools/release -p test_distribution.py -v
py -3.14 tools/release/smoke.py --archive target/distribution
py -3.14 tools/release/verify_windows_install.py $trustedInstaller $previousZip $candidateZip
```

Guardas usam arquivos sintéticos para entradas maliciosas, incompatibilidade, determinismo e preservação do ponteiro; não certificam executáveis. O verificador real usa ZIPs e diretórios descartáveis: instalação, atualização, migração, memória preservada, worker Python contra provedor sintético loopback, missão JSON realmente gerada/validada pelo checker LPAC incluído/revisada/integrada, smoke Slint e rollback compatível ou restauração após downgrade recusado. O starter usa configuração descartável e retira overrides do terminal de desenvolvimento. Esse ensaio não carrega modelos. Aceite Windows não certifica hardware Linux/macOS, reboot, falta de energia, voz ou inferência real.
