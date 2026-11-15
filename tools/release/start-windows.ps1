[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'Synapse\distribution'),
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA 'Synapse\state-0.3'),
    [string]$Workspace = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Synapse Workspace'),
    [string]$Python = $env:SYNAPSE_PYTHON_EXECUTABLE,
    [switch]$Verify
)
$ErrorActionPreference = 'Stop'
$active = Get-Content -LiteralPath (Join-Path $InstallRoot 'active.json') -Raw | ConvertFrom-Json
if ($active.current -cnotmatch '^[a-f0-9]{64}$') { throw 'Instalação ativa inválida.' }
$programs = Join-Path (Join-Path $InstallRoot 'versions') $active.current
if (!$Python) { $Python = & py -3.14 -c 'import sys; print(sys.executable)' }
$env:SYNAPSE_PYTHON_EXECUTABLE = (Resolve-Path -LiteralPath $Python).Path
$state = [IO.Directory]::CreateDirectory($StateRoot).FullName
$workspace = [IO.Directory]::CreateDirectory($Workspace).FullName
$endpoint = 'desktop-' + [Guid]::NewGuid().ToString('n')
$info = [Diagnostics.ProcessStartInfo]::new((Join-Path $programs 'synapse-backend.exe'))
$info.UseShellExecute = $false
$info.CreateNoWindow = $true
foreach ($argument in '--state-dir', $state, '--workspace', $workspace, '--local-endpoint', $endpoint) {
    $info.ArgumentList.Add($argument)
}
$core = [Diagnostics.Process]::Start($info)
try {
    $pipe = [IO.Pipes.NamedPipeClientStream]::new('.', ('Synapse-0.3-' + $endpoint), [IO.Pipes.PipeDirection]::InOut)
    try { $pipe.Connect(10000) }
    finally { $pipe.Dispose() }
    $desktop = Join-Path $programs 'synapse-desktop.exe'
    if ($Verify) {
        $reply = '{"action":"state"}' | & $desktop --bridge $endpoint
        if ($LASTEXITCODE -ne 0) { throw "A ponte saiu com erro $LASTEXITCODE." }
        $stateReply = $reply | ConvertFrom-Json
        if (!$stateReply.ok -or !$stateReply.state.connected) { throw 'O desktop não conectou ao Core.' }
    } else {
        & $desktop $endpoint
        if ($LASTEXITCODE -ne 0) { throw "O Synapse saiu com erro $LASTEXITCODE." }
    }
} finally {
    if (!$core.HasExited) { $core.Kill() }
    $core.WaitForExit()
    $core.Dispose()
}
