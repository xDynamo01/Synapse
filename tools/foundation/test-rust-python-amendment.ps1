#requires -Version 7.6
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$gate = Join-Path $PSScriptRoot 'test-gate-00.ps1'
# Legacy success labels cannot satisfy the new stack, irrespective of old logs.
$receipt = Join-Path ([IO.Path]::GetTempPath()) ("synapse-legacy-{0}.json" -f [guid]::NewGuid())
try {
    @{
        commit = (git -C (Join-Path $PSScriptRoot '../..') rev-parse HEAD)
        initial_clean = $true
        clone = 'fresh-local-clone'
        checks = @('host', 'runtime-python', 'runtime-typescript', 'transport-python',
            'transport-typescript', 'persistence', 'security') | ForEach-Object {
            @{ name = $_; exit_code = 0; command = 'historical fixture'; log = "$_.txt" }
        }
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $receipt
    $output = @(& pwsh -NoProfile -File $gate -ReceiptPath $receipt 2>&1)
    $code = $LASTEXITCODE
    if ($code -ne 1 -or $output -cnotcontains 'BLOCKED PL-006: Rust/Python foundation revalidation is NOT RUN; historical Node/Electron receipts cannot authorize product scaffolding.') {
        throw "Expected amended-stack BLOCKED before consuming legacy receipts (exit $code). Output: $($output -join [Environment]::NewLine)"
    }
    Write-Output 'PASS negative: legacy receipt claims rejected by PL-006; aggregate remains BLOCKED.'
} finally {
    Remove-Item -LiteralPath $receipt -Force
}
