# Configuração e recuperação de missões no Windows

Use o CLI Rust da 0.3 com um Workspace sem Git e um diretório de estado
privado separado. O Core permite uma instância ativa por diretório de estado.

## Preparar o CLI

1. Instale Rust MSVC, Python 3.14, MSBuild e as bibliotecas x64 de Visual
   Studio e Windows SDK. Use as versões das
   [receitas nativas verificadas](../evidence/backend/2026-11-11-windows-runner-recipes.md).
2. Escolha o executável do MSBuild em `$msbuild` e um caminho absoluto de
   build ainda inexistente em `$runtimeBuild`. Prepare o runtime dedicado
   e mantenha o manifesto que o builder grava junto do pacote.

   ```powershell
   $env:SYNAPSE_PYTHON_EXECUTABLE = py -3.14 -c "import sys; print(sys.executable)"
   & $env:SYNAPSE_PYTHON_EXECUTABLE tools/runner/build_windows_python.py --msbuild $msbuild --work-dir $runtimeBuild
   $env:SYNAPSE_CHECK_PYTHON_EXECUTABLE = Join-Path $runtimeBuild 'runtime/python.exe'
   ```

3. Para os testes Rust, configure `SYNAPSE_RUNNER_RUST_SYSROOT` com a saída de
   `rustc --print sysroot`. Aponte `SYNAPSE_RUNNER_VC_X64_LIB`,
   `SYNAPSE_RUNNER_SDK_UM_X64_LIB` e `SYNAPSE_RUNNER_SDK_UCRT_X64_LIB`
   para as bibliotecas x64. Se o linker precisar de outra área de preparação,
   configure `SYNAPSE_CHECK_RUST_RUN_ROOT` com um diretório absoluto confiável
   fora do Workspace.
4. Escolha `$state` para o estado privado e `$workspace` para o Workspace
   existente. Inicie o CLI e confira o diagnóstico com `health`.

   ```powershell
   cargo run -p synapse-core --bin synapse-backend -- --state-dir $state --workspace $workspace
   ```

   ```json
   {"version":1,"request_id":"health-1","command":{"type":"health"}}
   ```

O modelo local é necessário para planejar, gerar e revisar. A recuperação
de uma missão já registrada usa o estado local e os recibos disponíveis.

## Resolver uma interrupção

Reabra o CLI com os mesmos diretórios. Inspecione a missão e consulte os
caminhos, identidades e hashes registrados.

```json
{"version":1,"request_id":"inspect-1","command":{"type":"mission_recovery_inspect","mission_id":"minha-missao"}}
```

Use `finalize` quando a escrita tiver identidade comprovada e os pós-testes
duráveis estiverem completos. Use `rollback` para reverter efeitos
comprovados e ainda intactos enquanto a aprovação estiver vigente.

```json
{"version":1,"request_id":"resolve-1","command":{"type":"mission_recovery_resolve","mission_id":"minha-missao","mode":"rollback"}}
{"version":1,"request_id":"status-1","command":{"type":"mission_run_get","mission_id":"minha-missao"}}
```

Use IDs novos para consultar o estado atual. Repetir o ID de uma resolução
retorna o recibo original. Após outra interrupção, inspecione novamente
antes de decidir sobre uma nova resolução. Arquivos alterados ou com
identidade inconclusiva permanecem preservados. Consulte o
[protocolo v1](../../backend/contracts/v1/README.md) para os campos e erros.
