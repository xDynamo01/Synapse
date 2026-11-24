# Shared distribution validation. Run only from a trusted installer/source checkout.
function Assert-NoLinks([string]$Path) {
    $item = [IO.Path]::GetFullPath($Path)
    while ($item) {
        try {
            if ([IO.File]::GetAttributes($item) -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse points are not allowed in distribution paths.' }
        } catch [IO.FileNotFoundException] {
            # A not-yet-created leaf is allowed; inspect every existing ancestor.
        } catch [IO.DirectoryNotFoundException] {
        }
        $item = [IO.Path]::GetDirectoryName($item)
    }
}
function Read-PackageManifest([string]$Directory) {
    Assert-NoLinks $Directory
    $manifest = Get-Content -Raw -LiteralPath (Join-Path $Directory 'manifest.json') | ConvertFrom-Json -AsHashtable
    if ($manifest.platform -cne 'windows' -or $manifest.architecture -cne [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()) { throw 'Pacote incompatível com a plataforma.' }
    $required = @('synapse-backend.exe','synapse-image-decoder.exe','synapse-page-analyzer.exe','python/synapse_ai/__init__.py','start-windows.ps1')
    if ($manifest.Contains('format')) {
        $c = $manifest.compatibility
        if ($manifest.format -ne 2 -or $c.core_api -ne 1 -or (@($c.worker_protocol) -join ',') -cne '4,5' -or $c.storage_min -ne 0 -or $c.storage_max -ne 16 -or $c.frontend -cne 'slint' -or $c.python -cne '3.14' -or $c.remote_inference -ne $false) { throw 'Unsupported compatibility contract.' }
        $required += @('check-runtime/runtime-manifest.json','check-runtime/runtime/python.exe','synapse-maintenance.exe','synapse-desktop-slint.exe','runtime/python.exe','runtime/python314.dll','runtime/Lib/socket.py','runtime/DLLs/_socket.pyd','runtime/DLLs/_ssl.pyd','runtime/DLLs/_sqlite3.pyd','distribution-common.ps1','diagnose.py','install-windows.ps1')
    } else { $required += 'synapse-desktop.exe' }
    if ($manifest.Contains('format')) {
        $checker = Get-Content -Raw -LiteralPath (Join-Path $Directory 'check-runtime/runtime-manifest.json') | ConvertFrom-Json -AsHashtable
        if ($checker.cpython -cne '323c59a5e348347be2ce2b7ea55fcb30bf68b2d3' -or $checker.dependencies.Count -ne 2 -or $checker.dependencies['zlib-ng-2.2.4'] -cne 'a502e047655c31db29601def76ad6539acacf43d' -or $checker.dependencies['sqlite-3.50.4.0'] -cne 'ef547e549b49a2822214ef7880c0ca212b32929e') { throw 'Unsupported checker provenance.' }
        foreach ($name in 'python.exe','python314.dll','DLLs/_sqlite3.pyd') { if (!$checker.files.Contains($name)) { throw 'Incomplete checker runtime.' } }
        foreach ($name in $checker.files.Keys) { if ($manifest.sha256['check-runtime/runtime/' + $name] -cne $checker.files[$name]) { throw 'Checker inventory mismatch.' } }
        foreach ($name in $manifest.sha256.Keys) { if ($name.StartsWith('check-runtime/runtime/') -and !$checker.files.Contains($name.Substring(22))) { throw 'Unexpected checker runtime file.' } }
    }
    foreach ($name in $required) { if (!$manifest.sha256.Contains($name)) { throw "Componente ausente: $name" } }
    $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($name in $manifest.sha256.Keys) {
        if ($name -cnotmatch '^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$' -or ($name.Split('/') | Where-Object { $_ -in '.', '..' -or $_.EndsWith('.') -or $_ -match '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)' }) -or !$seen.Add($name)) { throw 'Entrada de pacote inválida.' }
        $path = Join-Path $Directory $name
        Assert-NoLinks $path
        if ($manifest.sha256[$name] -cnotmatch '^[a-f0-9]{64}$' -or !(Test-Path -LiteralPath $path -PathType Leaf) -or (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash -ine $manifest.sha256[$name]) { throw "Arquivo corrompido: $name" }
    }
    foreach ($entry in Get-ChildItem -LiteralPath $Directory -Recurse -Force) {
        if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Installed reparse point refused.' }
    }
    foreach ($file in Get-ChildItem -LiteralPath $Directory -File -Recurse -Force) {
        $name = [IO.Path]::GetRelativePath($Directory,$file.FullName).Replace('\','/')
        if ($name -cne 'manifest.json' -and !$seen.Contains($name)) { throw "Arquivo fora do manifesto: $name" }
    }
    return $manifest
}
function Assert-StateCompatible([string]$StateRoot, $Manifest, [string]$Python) {
    Assert-NoLinks $StateRoot
    [IO.Directory]::CreateDirectory($StateRoot) | Out-Null
    # Same file lock as Rust's sole-writer guard; reject updating an active state.
    $guard = [IO.File]::Open((Join-Path $StateRoot '.synapse-core.lock'), 'OpenOrCreate','ReadWrite','None')
    try {
        $db = Join-Path $StateRoot 'core.sqlite3'
        if (Test-Path -LiteralPath $db) {
            if (!$Python -or !(Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Python is required to verify storage compatibility.' }
            $schema = & $Python -I -B -c 'import sqlite3,sys,pathlib; c=sqlite3.connect(pathlib.Path(sys.argv[1]).resolve().as_uri()+"?mode=ro",uri=True); print(c.execute("PRAGMA user_version").fetchone()[0]); c.close()' $db
            if ($LASTEXITCODE -ne 0) { throw 'Cannot read storage schema.' }
            $maximum = if ($Manifest.Contains('format')) { $Manifest.compatibility.storage_max } else { 15 }
            if ([int]$schema -gt $maximum) { throw "Storage schema $schema incompatible with target maximum $maximum. Restore a compatible backup to a separate StateRoot before rollback." }
        }
        return $guard
    } catch { $guard.Dispose(); throw }
}
