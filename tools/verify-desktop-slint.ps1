$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$backend = if ($env:SYNAPSE_CORE_EXECUTABLE) { (Resolve-Path -LiteralPath $env:SYNAPSE_CORE_EXECUTABLE).Path } else { Join-Path $repo 'target/debug/synapse-backend.exe' }
$fixture = Join-Path $repo 'backend/python/tests/fixture_server.py'
$python = & py -3.14 -c 'import sys; print(sys.executable)'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.14 is required for this test.' }
$scratch = Join-Path ([IO.Path]::GetTempPath()) ('synapse-slint-' + [guid]::NewGuid().ToString('N'))
$endpoint = Split-Path -Leaf $scratch
$workspace = Join-Path $scratch 'workspace'
$state = Join-Path $scratch 'state'
$project = Join-Path $workspace 'project'
$null = New-Item -ItemType Directory -Path $project
$provider = $null
$core = $null
Push-Location $repo
try {
    if (-not $env:SYNAPSE_CORE_EXECUTABLE) {
        cargo build --locked -p synapse-core --bin synapse-backend
        if ($LASTEXITCODE -ne 0) { throw 'Core build failed.' }
    }
    $sourceBackend=$backend
    $binaryDirectory=Join-Path $scratch 'private-binaries'
    $null=New-Item -ItemType Directory -Path $binaryDirectory
    $backend=Join-Path $binaryDirectory 'synapse-backend.exe'
    Copy-Item -LiteralPath $sourceBackend -Destination $backend
    (Get-FileHash -LiteralPath $backend -Algorithm SHA256).Hash | Set-Content (Join-Path $scratch 'source-backend.sha256')
    $fixtureOut = Join-Path $scratch 'provider.out'
    $provider = Start-Process -FilePath $python -ArgumentList @('-u',"`"$fixture`"","`"$scratch/seen`"","`"$scratch/release`"",'normal') -RedirectStandardOutput $fixtureOut -WindowStyle Hidden -PassThru
    $port = 0
    for ($attempt = 0; $attempt -lt 80; $attempt++) {
        $line = Get-Content -LiteralPath $fixtureOut -TotalCount 1
        if ([int]::TryParse($line, [ref]$port) -and $port -gt 0) { break }
        if ($provider.HasExited) { throw 'Model fixture exited.' }
        Start-Sleep -Milliseconds 50
    }
    if ($port -le 0) { throw 'Model fixture did not publish a port.' }
    $commands = @(
        @{type='project_register';scope='project:fixture';root=$project}
        @{type='chat_create';chat_id='fixture-history';title='Conversa de teste';scope='project:fixture'}
        @{type='message_append';chat_id='fixture-history';message_id='first';role='user';content='Mensagem anterior'}
        @{type='model_register';model=@{id='selected';provider='lm_studio';endpoint="http://127.0.0.1:$port";capabilities=@('chat');memory_bytes=1024}}
    )
    $requests = for ($i = 0; $i -lt $commands.Count; $i++) {
        @{version=1;request_id="fixture-$i";command=$commands[$i]} | ConvertTo-Json -Depth 8 -Compress
    }
    $replies = $requests | & $backend --state-dir $state --workspace $workspace
    if ($LASTEXITCODE -ne 0 -or @($replies).Count -ne $commands.Count) { throw 'Core fixture setup failed.' }
    foreach ($reply in $replies) {
        if (-not ($reply | ConvertFrom-Json).ok) { throw "Fixture command failed: $reply" }
    }
    $core = Start-Process -FilePath $backend -ArgumentList @('--state-dir',"`"$state`"",'--workspace',"`"$workspace`"",'--local-endpoint',$endpoint) -Environment @{SYNAPSE_PYTHON_EXECUTABLE=$python;SYNAPSE_CHECK_PYTHON_EXECUTABLE=(Join-Path $repo 'target/check-runtime/runtime/python.exe')} -WindowStyle Hidden -PassThru
    $env:SYNAPSE_SLINT_TEST_ENDPOINT = $endpoint
    cargo test --locked -p synapse-desktop-slint core_pipe_workspace_library_and_conversation -- --ignored --nocapture
    if ($LASTEXITCODE -ne 0) { throw 'Desktop/Core integration test failed.' }
    @{summary='Criar nota de validação';artifacts=@(@{path='agent_result.json';purpose='Resultado verificável da tarefa'});checks=@(@{kind='json_validate';entrypoint='agent_result.json'})} | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $scratch 'mission-response') -Encoding utf8NoBOM
    @{artifacts=@(@{path='agent_result.json';content='{"agent":"ARTEMIS","executed":true}'})} | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $scratch 'mission_generate-response') -Encoding utf8NoBOM
    @{approved=$true;reason='O artefato satisfaz o objetivo e passou na validação JSON.'} | ConvertTo-Json | Set-Content (Join-Path $scratch 'mission_review-response') -Encoding utf8NoBOM
    $taskProject=Join-Path $workspace 'agent-project'
    $null=New-Item -ItemType Directory -Path $taskProject
    $env:SYNAPSE_SLINT_TEST_TASK_ROOT=$taskProject
    cargo test --locked -p synapse-desktop-slint core_pipe_plans_approves_and_executes_task -- --ignored --nocapture
    if ($LASTEXITCODE -ne 0) { throw 'Desktop agent task integration test failed.' }
    @{summary='Duas entregas dependentes';artifacts=@(@{path='first.json';purpose='Primeiro resultado'},@{path='second.json';purpose='Resultado dependente'});checks=@(@{kind='json_validate';entrypoint='first.json'},@{kind='json_validate';entrypoint='second.json'});tasks=@(@{task_id='first';objective='Criar first.json';dependencies=@();priority=0;artifacts=@('first.json')},@{task_id='second';objective='Usar first.json e criar second.json';dependencies=@('first');priority=1;artifacts=@('second.json')})} | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $scratch 'mission-response') -Encoding utf8NoBOM
    @{'first.json'=@{artifacts=@(@{path='first.json';content='{"step":1}'})};'second.json'=@{artifacts=@(@{path='second.json';content='{"step":2}'})}} | ConvertTo-Json -Depth 10 | Set-Content (Join-Path $scratch 'mission_generate-map') -Encoding utf8NoBOM
    $env:SYNAPSE_SLINT_TEST_TASK_ROOT=Join-Path $workspace 'graph-project'
    $null=New-Item -ItemType Directory -Path $env:SYNAPSE_SLINT_TEST_TASK_ROOT
    cargo test --locked -p synapse-desktop-slint core_pipe_executes_planner_graph_with_confirmed_swarm -- --ignored --nocapture
    if ($LASTEXITCODE -ne 0) { throw 'Desktop graph and Swarm integration test failed.' }
} finally {
    foreach ($process in @($core, $provider)) {
        if ($null -ne $process -and -not $process.HasExited) { Stop-Process -Id $process.Id }
    }
    Remove-Item Env:SYNAPSE_SLINT_TEST_ENDPOINT -ErrorAction SilentlyContinue
    Remove-Item Env:SYNAPSE_SLINT_TEST_TASK_ROOT -ErrorAction SilentlyContinue
    Pop-Location
    Write-Output "Isolated test artifacts: $scratch"
}
