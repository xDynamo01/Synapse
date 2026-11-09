#requires -Version 7.6
[CmdletBinding()]
param([string] $ReceiptPath = '.local/gate-00/receipts.json')

$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
Set-Location -LiteralPath $root
$reportPath = 'docs/evidence/foundation/gate-00-report.md'
$required = @{
    host = 'PASS'; 'runtime-python' = '12 passed'; 'runtime-typescript' = '# pass 3'
    'transport-python' = '3 passed'; 'transport-typescript' = '# pass 2'
    persistence = '120 pre_commit=60 acknowledged=60 acknowledged_loss=0 partial_visibility=0 integrity_pass=120'
    security = 'PASS 13 negative cases'
}

# This is a local evidence-integrity gate, not an attestation or runtime security boundary.
function Get-GateErrors([hashtable] $State) {
    $errors = [Collections.Generic.List[string]]::new()
    if (-not $State.report) { $errors.Add('Missing Gate 00 report.') }
    foreach ($heading in 'Decisions', 'Measurements and budgets', 'Limitations', 'Reproduction', 'Decision Charter Compliance') {
        if ($State.report -notmatch "(?m)^## $([regex]::Escape($heading))\r?$") { $errors.Add("Missing report section: $heading.") }
    }
    if ($State.report -notmatch 'Gate result: \*\*PASS\*\*' -or $State.report -notmatch 'Scaffolding: \*\*AUTHORIZED within Plan 01 scope\*\*') {
        $errors.Add('Report does not authorize the scoped PASS handoff.')
    }
    foreach ($adr in $State.adrs.Keys) {
        if ($State.adrs[$adr] -notmatch '(?m)^Status.*ACCEPTED') { $errors.Add("ADR $adr is not accepted.") }
    }
    if ($State.adrs.Count -ne 3) { $errors.Add('Require ADRs 0001–0003.') }
    foreach ($path in $State.missing) { $errors.Add("Missing evidence: $path.") }
    if ($State.productRoots.Count) { $errors.Add('Product source root exists before Gate 00.') }
    if (-not $State.clean) { $errors.Add('Worktree is not clean.') }
    foreach ($commit in $State.commits) {
        if ($commit -notmatch '^[a-f0-9]{40}$' -or $State.report -notmatch $commit) { $errors.Add("Missing exact task commit: $commit.") }
    }
    $receipt = $State.receipt
    if (-not $receipt -or $receipt.commit -cne $State.head -or -not $receipt.initial_clean -or $receipt.clone -ne 'fresh-local-clone') {
        $errors.Add('Require clean-clone receipts for exact HEAD.')
    }
    foreach ($name in $required.Keys) {
        $rows = @($receipt.checks | Where-Object name -eq $name)
        if ($rows.Count -ne 1) { $errors.Add("Missing/duplicate receipt: $name."); continue }
        $row = $rows[0]
        if ($row.exit_code -ne 0 -or -not $row.command -or $row.started_utc -notmatch '^2026-\d\d-\d\dT') {
            $errors.Add("Failed/incomplete receipt: $name.")
        }
        if (-not $State.logs.ContainsKey($name) -or $State.logs[$name].hash -cne $row.sha256 -or
            $State.logs[$name].text -notmatch [regex]::Escape($required[$name])) { $errors.Add("Invalid log evidence: $name.") }
        if ($name -eq 'persistence' -and $State.logs[$name].text -notmatch '10 passed') { $errors.Add('Incomplete persistence suite.') }
    }
    return $errors.ToArray()
}

$state = @{ head = (git rev-parse HEAD); clean = -not (git status --porcelain); report = ''; adrs = @{}; missing = @(); productRoots = @(); logs = @{}; receipt = $null; commits = @() }
if (Test-Path -LiteralPath $reportPath) { $state.report = Get-Content -LiteralPath $reportPath -Raw }
foreach ($path in 'docs/adr/0001-core-runtime-and-toolchain.md', 'docs/adr/0002-client-core-transport.md', 'docs/adr/0003-foundation-persistence.md') {
    if (Test-Path -LiteralPath $path) { $state.adrs[$path] = Get-Content -LiteralPath $path -Raw }
}
foreach ($path in @('docs/evidence/foundation/host-capabilities.windows.json', 'docs/evidence/foundation/host-capabilities.schema.json',
    'docs/evidence/foundation/runtime-compatibility.md', 'docs/evidence/foundation/runtime-artifact.sha256.json',
    'docs/evidence/foundation/runtime-toolchain.windows.json', 'docs/evidence/foundation/transport-spike.md',
    'docs/evidence/foundation/transport-measurements.windows.json', 'docs/evidence/foundation/persistence-spike.md',
    'docs/evidence/foundation/security-review.md', 'docs/security/foundation-threat-model.md', 'docs/security/authority-invariants.md',
    'docs/specs/subprojects/01-repository-and-skeleton.md', 'docs/superpowers/plans/2026-11-06-repository-and-cross-platform-skeleton.md')) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { $state.missing += $path }
}
# Fail on untracked product roots too; restrict committed top-level executable roots.
$state.productRoots = @(git ls-files | Where-Object { $_ -notmatch '^(docs/|experiments/|tools/|README\.md$|\.gitignore$)' })
foreach ($path in 'apps', 'core', 'packages', 'src', 'backend', 'frontend') {
    if (Test-Path -LiteralPath $path) { $state.productRoots += $path }
}
foreach ($short in 'f1c1676', '54ab41c', '52cb737', '009fe94', 'e3933f2') {
    $commit = git rev-parse "$short^{commit}"
    if ($LASTEXITCODE -ne 0) { throw "Cannot resolve task commit $short" }
    git merge-base --is-ancestor $commit HEAD
    if ($LASTEXITCODE -ne 0) { throw "Task commit is not an ancestor: $commit" }
    $state.commits += $commit
}
if (Test-Path -LiteralPath $ReceiptPath) {
    $state.receipt = Get-Content -LiteralPath $ReceiptPath -Raw | ConvertFrom-Json -AsHashtable
    $receiptRoot = Split-Path -Parent ([IO.Path]::GetFullPath($ReceiptPath))
    foreach ($row in $state.receipt.checks) {
        if ($row.name -notin $required.Keys -or $row.log -ne "$($row.name).txt") { continue }
        $path = Join-Path $receiptRoot $row.log
        if (Test-Path -LiteralPath $path -PathType Leaf) { $state.logs[$row.name] = @{ hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant(); text = Get-Content -LiteralPath $path -Raw } }
    }
}
$errors = @(Get-GateErrors $state)
if ($errors.Count) { $errors | ForEach-Object { Write-Output "FAIL $_" }; exit 1 }

function Assert-Rejected([string] $Name, [scriptblock] $Mutate, [string] $Expected) {
    $copy = $state | ConvertTo-Json -Depth 30 | ConvertFrom-Json -AsHashtable
    & $Mutate $copy
    if (-not (@(Get-GateErrors $copy) | Where-Object { $_ -like "*$Expected*" })) { throw "Negative case did not reject: $Name" }
    Write-Output "PASS negative: $Name."
}
Assert-Rejected 'missing report' { param($s) $s.report = '' } 'Missing Gate 00 report'
Assert-Rejected 'unaccepted ADR' { param($s) $s.adrs['docs/adr/0002-client-core-transport.md'] = 'Status: PROPOSED' } 'not accepted'
Assert-Rejected 'missing evidence' { param($s) $s.missing = @('host fixture') } 'Missing evidence'
Assert-Rejected 'failed experiment' { param($s) $s.receipt.checks[0].exit_code = 1 } 'Failed/incomplete receipt'
Assert-Rejected 'stale commit' { param($s) $s.receipt.commit = '0' * 40 } 'exact HEAD'
Assert-Rejected 'altered log' { param($s) $s.logs.host.hash = '0' * 64 } 'Invalid log evidence'
Assert-Rejected 'missing selected fixture' { param($s) $s.receipt.checks = @($s.receipt.checks | Where-Object name -ne 'transport-python') } 'Missing/duplicate receipt'
Assert-Rejected 'product root' { param($s) $s.productRoots = @('core') } 'Product source root'
Assert-Rejected 'missing limitations' { param($s) $s.report = $s.report.Replace('## Limitations', '## Other') } 'Missing report section: Limitations'
Assert-Rejected 'dirty clone' { param($s) $s.clean = $false } 'not clean'
Write-Output "PASS Gate 00: seven selected check receipts at $($state.head); ten negative cases. Windows foundation only; no product/security/platform operation claim."
