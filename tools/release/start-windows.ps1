[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'Synapse\distribution'),
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA 'Synapse\state-0.3'),
    [string]$Workspace = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Synapse Workspace'),
    [string]$Python,
    [string]$ConfigRoot = (Join-Path $env:LOCALAPPDATA 'Synapse'),
    [switch]$Verify,
    [switch]$Diagnose
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'distribution-common.ps1')
Assert-NoLinks $InstallRoot
$lock = [IO.File]::Open((Join-Path $InstallRoot 'install.lock'),'Open','ReadWrite','None')
$core = $null
try {
    $active = Get-Content -LiteralPath (Join-Path $InstallRoot 'active.json') -Raw | ConvertFrom-Json
    if ($active.current -cnotmatch '^[a-f0-9]{64}$' -or !$active.manifest_sha256) { throw 'Unverified active installation; reinstall using a trusted archive digest.' }
    $programs = Join-Path (Join-Path $InstallRoot 'versions') $active.current
    if ((Get-FileHash -LiteralPath (Join-Path $programs 'manifest.json')).Hash -ine $active.manifest_sha256) { throw 'Active manifest changed.' }
    $manifest = Read-PackageManifest $programs
    if (!$Python) { $Python = Join-Path $programs 'runtime/python.exe' }
    if (!(Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Configure -Python with an absolute CPython 3.14 executable for a legacy installation.' }
    $Python = (Resolve-Path -LiteralPath $Python).Path
    & $Python -I -B -c 'import sys,socket,ssl,sqlite3; assert sys.version_info[:2] == (3,14)'
    if ($LASTEXITCODE -ne 0) { throw 'Incomplete Python 3.14 runtime.' }
    if ($Diagnose) {
        & $Python -I -B (Join-Path $PSScriptRoot 'diagnose.py') --programs $programs --config-root ([IO.Path]::GetFullPath($ConfigRoot))
        if ($LASTEXITCODE -ne 0) { throw 'Required dependencies unavailable; see diagnostic report.' }
        return
    }
    $stateGuard = Assert-StateCompatible $StateRoot $manifest $Python
    if ($stateGuard) { $stateGuard.Dispose() }
    $state = [IO.Directory]::CreateDirectory($StateRoot).FullName
    $workspace = [IO.Directory]::CreateDirectory($Workspace).FullName
    $endpoint = 'desktop-' + [Guid]::NewGuid().ToString('n')
    $info = [Diagnostics.ProcessStartInfo]::new((Join-Path $programs 'synapse-backend.exe'))
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.WorkingDirectory = $programs
    $info.Environment['SYNAPSE_PYTHON_EXECUTABLE'] = $Python
    if ($manifest.Contains('format')) { $info.Environment['SYNAPSE_CHECK_PYTHON_EXECUTABLE'] = Join-Path $programs 'check-runtime/runtime/python.exe' }
    $info.Environment['PYTHONDONTWRITEBYTECODE'] = '1'
    $info.Environment['SYNAPSE_CONFIG_ROOT'] = [IO.Path]::GetFullPath($ConfigRoot)
    Assert-NoLinks $ConfigRoot
    $toolchain = Join-Path $ConfigRoot 'native-toolchain.json'
    if (Test-Path -LiteralPath $toolchain) {
        Assert-NoLinks $toolchain
        if ((Get-Item -LiteralPath $toolchain).Length -gt 16384) { throw 'Invalid toolchain configuration size.' }
        $settings = Get-Content -Raw -LiteralPath $toolchain | ConvertFrom-Json -AsHashtable
        foreach ($key in $settings.Keys) {
            if ($key -cnotin @('SYNAPSE_RUNNER_RUST_SYSROOT','SYNAPSE_RUNNER_VC_X64_LIB','SYNAPSE_RUNNER_SDK_UM_X64_LIB','SYNAPSE_RUNNER_SDK_UCRT_X64_LIB') -or ![IO.Path]::IsPathFullyQualified($settings[$key]) -or !(Test-Path -LiteralPath $settings[$key] -PathType Container)) { throw 'Invalid local toolchain configuration.' }
            if (!$info.Environment.ContainsKey($key)) { $info.Environment[$key] = $settings[$key] }
        }
    }
    foreach ($argument in '--state-dir',$state,'--workspace',$workspace,'--local-endpoint',$endpoint) { $info.ArgumentList.Add($argument) }
    $core = [Diagnostics.Process]::Start($info)
    $pipe = [IO.Pipes.NamedPipeClientStream]::new('.',('Synapse-0.3-'+$endpoint),[IO.Pipes.PipeDirection]::InOut)
    try { $pipe.Connect(10000) } finally { $pipe.Dispose() }
    if ($manifest.compatibility.frontend -ceq 'slint') {
        $desktop = Join-Path $programs 'synapse-desktop-slint.exe'
        $ui = [Diagnostics.ProcessStartInfo]::new($desktop)
        $ui.UseShellExecute = $false
        $ui.WorkingDirectory = $programs
        $ui.Environment['SYNAPSE_CONFIG_ROOT'] = [IO.Path]::GetFullPath($ConfigRoot)
        $ui.ArgumentList.Add($endpoint)
        if ($Verify) { $ui.ArgumentList.Add('--smoke') }
        $process = [Diagnostics.Process]::Start($ui)
        try {
            if ($Verify -and !$process.WaitForExit(30000)) { $process.Kill(); throw 'Slint smoke timed out.' }
            $process.WaitForExit()
            if ($process.ExitCode -ne 0) { throw "Slint exited with error $($process.ExitCode)." }
        } finally { $process.Dispose() }
    } else {
        $desktop = Join-Path $programs 'synapse-desktop.exe'
        if ($Verify) {
            $reply = '{"action":"state"}' | & $desktop --bridge $endpoint
            $stateReply = $reply | ConvertFrom-Json
            if ($LASTEXITCODE -ne 0 -or !$stateReply.ok -or !$stateReply.state.connected) { throw 'Desktop bridge failed.' }
        } else { & $desktop $endpoint; if ($LASTEXITCODE -ne 0) { throw 'Desktop failed.' } }
    }
} finally {
    if ($core) { if (!$core.HasExited) { $core.Kill() }; $core.WaitForExit(); $core.Dispose() }
    $lock.Dispose()
}
