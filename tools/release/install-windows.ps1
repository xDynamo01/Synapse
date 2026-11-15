[CmdletBinding(DefaultParameterSetName = 'Install')]
param(
    [Parameter(Mandatory, ParameterSetName = 'Install')][string]$Package,
    [Parameter(Mandatory, ParameterSetName = 'Install')][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$Sha256,
    [Parameter(Mandatory, ParameterSetName = 'Rollback')][switch]$Rollback,
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'Synapse\distribution')
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($InstallRoot)
$versions = Join-Path $root 'versions'
[IO.Directory]::CreateDirectory($versions) | Out-Null
$lock = [IO.File]::Open((Join-Path $root 'install.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
$pointer = Join-Path $root 'active.json'

function Set-Active($current, $previous) {
    $temporary = Join-Path $root ([Guid]::NewGuid().ToString('n') + '.json')
    try {
        $content = [ordered]@{ current = $current; previous = $previous } | ConvertTo-Json
        [IO.File]::WriteAllText($temporary, $content, [Text.UTF8Encoding]::new($false))
        [IO.File]::Move($temporary, $pointer, $true)
    } finally {
        [IO.File]::Delete($temporary)
    }
}

try {
    $active = if (Test-Path -LiteralPath $pointer -PathType Leaf) {
        Get-Content -LiteralPath $pointer -Raw | ConvertFrom-Json
    }
    if ($Rollback) {
        if (!$active -or $active.previous -cnotmatch '^[a-f0-9]{64}$' -or
            !(Test-Path -LiteralPath (Join-Path $versions $active.previous) -PathType Container)) {
            throw 'Não há versão anterior instalada.'
        }
        Set-Active $active.previous $active.current
        Write-Output $active.previous
        return
    }

    $resolved = (Resolve-Path -LiteralPath $Package).Path
    $identity = $Sha256.ToLowerInvariant()
    $inputStream = [IO.File]::Open($resolved, 'Open', 'Read', 'Read')
    try {
        $hasher = [Security.Cryptography.SHA256]::Create()
        try { $actual = [Convert]::ToHexString($hasher.ComputeHash($inputStream)).ToLowerInvariant() }
        finally { $hasher.Dispose() }
        if ($actual -cne $identity) { throw 'SHA-256 divergente.' }
        if ($active.current -ceq $identity) { Write-Output $identity; return }
        $inputStream.Position = 0
        $archive = [IO.Compression.ZipArchive]::new($inputStream, 'Read', $true)
        try {
            $reader = [IO.StreamReader]::new($archive.GetEntry('manifest.json').Open())
            try { $manifest = $reader.ReadToEnd() | ConvertFrom-Json -AsHashtable }
            finally { $reader.Dispose() }
            $machine = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
            if ($manifest.platform -cne 'windows' -or $manifest.architecture -cne $machine) {
                throw 'Pacote incompatível com a plataforma.'
            }
            $stage = Join-Path $versions ([Guid]::NewGuid().ToString('n') + '.staging')
            [IO.Directory]::CreateDirectory($stage) | Out-Null
            $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
            foreach ($entry in $archive.Entries) {
                $name = $entry.FullName
                if ($name -cnotmatch '^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$' -or
                    ($name.Split('/') | Where-Object { $_ -in '.', '..' -or $_.EndsWith('.') }) -or
                    !$seen.Add($name)) { throw 'Entrada de pacote inválida.' }
                if ($name -cne 'manifest.json' -and !$manifest.sha256.Contains($name)) {
                    throw 'Arquivo fora do manifesto.'
                }
                $path = Join-Path $stage $name
                [IO.Directory]::CreateDirectory((Split-Path -Parent $path)) | Out-Null
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $path)
                if ($name -cne 'manifest.json' -and
                    (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash -ine $manifest.sha256[$name]) {
                    throw 'Arquivo corrompido.'
                }
            }
            if ($seen.Count -ne $manifest.sha256.Count + 1) { throw 'Pacote incompleto.' }
            foreach ($required in 'synapse-backend.exe', 'synapse-desktop.exe', 'start-windows.ps1', 'python/synapse_ai/__init__.py') {
                if (!$seen.Contains($required)) { throw "Componente ausente $required" }
            }
            $destination = Join-Path $versions $identity
            if (Test-Path -LiteralPath $destination -PathType Container) {
                foreach ($name in $manifest.sha256.Keys) {
                    $installed = Join-Path $destination $name
                    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $installed).Hash -ine $manifest.sha256[$name]) {
                        throw 'A cópia instalada diverge do pacote.'
                    }
                }
                [IO.Directory]::Delete($stage, $true)
            } else {
                [IO.Directory]::Move($stage, $destination)
            }
            Set-Active $identity $active.current
            Write-Output $identity
        } finally { $archive.Dispose() }
    } finally { $inputStream.Dispose() }
} finally { $lock.Dispose() }
