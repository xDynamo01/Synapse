[CmdletBinding(DefaultParameterSetName = 'Install')]
param(
    [Parameter(Mandatory, ParameterSetName = 'Install')][string]$Package,
    [Parameter(Mandatory, ParameterSetName = 'Install')][Alias('Sha256')][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$TrustedSha256,
    [Parameter(Mandatory, ParameterSetName = 'Rollback')][switch]$Rollback,
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'Synapse\distribution'),
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA 'Synapse\state-0.3'),
    [string]$Python
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'distribution-common.ps1')
$root = [IO.Path]::GetFullPath($InstallRoot)
Assert-NoLinks $root
Assert-NoLinks $StateRoot
$versions = Join-Path $root 'versions'
[IO.Directory]::CreateDirectory($versions) | Out-Null
$lock = [IO.File]::Open((Join-Path $root 'install.lock'), 'OpenOrCreate','ReadWrite','None')
$pointer = Join-Path $root 'active.json'
$stage = $null
$stateLock = $null
function Set-Active($current,$previous,$manifestHash,$previousManifestHash) {
    $temporary = Join-Path $root ([Guid]::NewGuid().ToString('n') + '.json')
    try {
        $content = @{current=$current;previous=$previous;manifest_sha256=$manifestHash;previous_manifest_sha256=$previousManifestHash} | ConvertTo-Json
        [IO.File]::WriteAllText($temporary,$content,[Text.UTF8Encoding]::new($false))
        [IO.File]::Move($temporary,$pointer,$true)
    } finally { [IO.File]::Delete($temporary) }
}
try {
    $active = if (Test-Path -LiteralPath $pointer) { Get-Content -Raw -LiteralPath $pointer | ConvertFrom-Json }
    if ($active -and $active.current -cnotmatch '^[a-f0-9]{64}$') { throw 'Invalid active pointer.' }
    if (!$Python -and $active) { $Python = Join-Path $versions ($active.current + '/runtime/python.exe') }
    if ($Rollback) {
        if (!$active -or $active.previous -cnotmatch '^[a-f0-9]{64}$' -or !$active.previous_manifest_sha256) { throw 'No verified previous version; reinstall a trusted legacy archive to establish provenance.' }
        $destination = Join-Path $versions $active.previous
        if ((Get-FileHash -LiteralPath (Join-Path $destination 'manifest.json')).Hash -ine $active.previous_manifest_sha256) { throw 'Previous manifest changed.' }
        $manifest = Read-PackageManifest $destination
        $stateLock = Assert-StateCompatible $StateRoot $manifest $Python
        Set-Active $active.previous $active.current $active.previous_manifest_sha256 $active.manifest_sha256
        Write-Output $active.previous
        return
    }
    $identity = $TrustedSha256.ToLowerInvariant()
    $stream = [IO.File]::Open((Resolve-Path -LiteralPath $Package).Path,'Open','Read','Read')
    try {
        $actual = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($stream)).ToLowerInvariant()
        if ($actual -cne $identity) { throw 'Archive differs from independently trusted SHA-256.' }
        $stream.Position = 0
        $archive = [IO.Compression.ZipArchive]::new($stream,'Read',$true)
        try {
            $stage = Join-Path $versions ([Guid]::NewGuid().ToString('n') + '.staging')
            [IO.Directory]::CreateDirectory($stage) | Out-Null
            $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
            [long]$expandedBytes = 0
            foreach ($entry in $archive.Entries) {
                $expandedBytes += $entry.Length
                if ($expandedBytes -gt 2147483648) { throw 'Expanded package size limit exceeded.' }
                $name = $entry.FullName
                if ($name -cnotmatch '^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$' -or ($name.Split('/') | Where-Object { $_ -in '.', '..' -or $_.EndsWith('.') -or $_ -match '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)' }) -or !$seen.Add($name) -or $entry.Length -gt 536870912) { throw 'Invalid ZIP entry.' }
                if ($seen.Count -gt 20000) { throw 'Package entry limit exceeded.' }
                $path = Join-Path $stage $name
                [IO.Directory]::CreateDirectory((Split-Path -Parent $path)) | Out-Null
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry,$path)
            }
            $manifest = Read-PackageManifest $stage
            if (!$Python -or !(Test-Path -LiteralPath $Python)) { $Python = Join-Path $stage 'runtime/python.exe' }
            $stateLock = Assert-StateCompatible $StateRoot $manifest $Python
            $destination = Join-Path $versions $identity
            $manifestHash = (Get-FileHash -LiteralPath (Join-Path $stage 'manifest.json')).Hash.ToLowerInvariant()
            if (Test-Path -LiteralPath $destination) {
                $null = Read-PackageManifest $destination
                if ((Get-FileHash -LiteralPath (Join-Path $destination 'manifest.json')).Hash -ine $manifestHash) { throw 'Installed manifest differs.' }
            } else { [IO.Directory]::Move($stage,$destination); $stage=$null }
            if ($active.current -ceq $identity) { Write-Output $identity; return }
            Set-Active $identity $active.current $manifestHash $active.manifest_sha256
            Write-Output $identity
        } finally { $archive.Dispose() }
    } finally { $stream.Dispose() }
} finally {
    if ($stage -and (Test-Path -LiteralPath $stage)) {
        Assert-NoLinks $stage
        if ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($stage)) -ine $versions -or !$stage.EndsWith('.staging')) { throw 'Unsafe staging cleanup refused.' }
        [IO.Directory]::Delete($stage,$true)
    }
    if ($stateLock) { $stateLock.Dispose() }
    $lock.Dispose()
}
