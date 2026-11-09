#requires -Version 7.6
[CmdletBinding()]
param([string] $RepositoryRoot = (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent))

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$requirements = [ordered]@{
    'docs/security/foundation-threat-model.md' = @('Scope and status', 'Assets', 'Trust boundaries', 'Entry points', 'Attacker capabilities', 'Threats and mitigations', 'Verification owners', 'Residual risks', 'Mandatory extensions', 'Decision Charter Compliance')
    'docs/security/authority-invariants.md' = @('Scope and status', 'Authority invariants', 'Context consumer tests', 'Verification owners', 'Residual risks', 'Decision Charter Compliance')
    'docs/evidence/foundation/security-review.md' = @('Scope and status', 'Review method', 'Validation', 'Residual risks', 'Decision Charter Compliance')
}

function Get-Section([string] $Text, [string] $Title) {
    $pattern = '(?ms)^## ' + [regex]::Escape($Title) + '\r?\n(.*?)(?=^## |\z)'
    $match = [regex]::Match($Text, $pattern)
    if ($match.Success) { return $match.Groups[1].Value.Trim() }
    return ''
}

function Get-DocumentErrors([hashtable] $Documents) {
    $errors = [System.Collections.Generic.List[string]]::new()
    foreach ($path in $requirements.Keys) {
        if (-not $Documents.ContainsKey($path)) {
            $errors.Add("Missing document $path; required sections: $($requirements[$path] -join ', ').")
            continue
        }
        $content = $Documents[$path]
        foreach ($section in $requirements[$path]) {
            $body = Get-Section $content $section
            if ($body.Length -lt 40 -or $body -match '^\s*(TODO|TBD|N/A)\s*$') {
                $errors.Add("Missing or empty section '$section' in $path.")
            }
        }
        if ($content -notmatch 'docs/specs/2026-11-06-synapse-0\.3-decision-charter\.md') {
            $errors.Add("Missing binding charter path in $path.")
        }
        # Check concrete source anchors. Exclude arbitrary prose/URLs from this grammar.
        foreach ($anchor in [regex]::Matches($content, '`((?:docs|experiments|tools)/[A-Za-z0-9_./-]+):(\d+)(?:-(\d+))?`')) {
            $source = Join-Path $RepositoryRoot $anchor.Groups[1].Value
            $first = [int] $anchor.Groups[2].Value
            $last = if ($anchor.Groups[3].Success) { [int] $anchor.Groups[3].Value } else { $first }
            if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
                $errors.Add("Missing citation source: $($anchor.Value).")
                continue
            }
            $lineCount = @(Get-Content -LiteralPath $source).Count
            if ($first -lt 1 -or $last -lt $first -or $last -gt $lineCount) {
                $errors.Add("Invalid citation range: $($anchor.Value).")
            }
        }
    }
    $tableRules = @(
        @{ Path='docs/security/foundation-threat-model.md'; Section='Threats and mitigations'; Prefix='T'; Count=9; Columns=7 },
        @{ Path='docs/security/foundation-threat-model.md'; Section='Mandatory extensions'; Prefix='E'; Count=5; Columns=4 },
        @{ Path='docs/security/foundation-threat-model.md'; Section='Residual risks'; Prefix='R'; Count=4; Columns=5 },
        @{ Path='docs/security/authority-invariants.md'; Section='Authority invariants'; Prefix='AI'; Count=10; Columns=5 },
        @{ Path='docs/security/authority-invariants.md'; Section='Context consumer tests'; Prefix='PC'; Count=4; Columns=5 }
    )
    foreach ($rule in $tableRules) {
        if (-not $Documents.ContainsKey($rule.Path)) { continue }
        $body = Get-Section $Documents[$rule.Path] $rule.Section
        for ($i=1; $i -le $rule.Count; $i++) {
            $id = '{0}-{1:d2}' -f $rule.Prefix, $i
            $rows = @([regex]::Matches($body, '(?m)^\|\s*' + $id + '\s*\|[^\r\n]*\|\s*$'))
            if ($rows.Count -ne 1) {
                $errors.Add("Expected one $id row in $($rule.Path).")
                continue
            }
            $cells = @($rows[0].Value.Trim().Trim('|').Split('|') | ForEach-Object { $_.Trim() })
            if ($cells.Count -ne $rule.Columns -or @($cells | Where-Object { $_.Length -eq 0 -or $_ -match '^(TODO|TBD|N/A|-)$' }).Count -gt 0) {
                $errors.Add("Incomplete $id row in $($rule.Path).")
            }
        }
    }
    # Redaction must preserve authorized local context, not erase all private data.
    foreach ($privacyRule in @(
        @{ Path='docs/security/authority-invariants.md'; Id='AI-07' },
        @{ Path='docs/security/foundation-threat-model.md'; Id='T-09' }
    )) {
        if (-not $Documents.ContainsKey($privacyRule.Path)) { continue }
        $row = [regex]::Match($Documents[$privacyRule.Path], '(?m)^\| ' + $privacyRule.Id + ' \|.*$').Value
        foreach ($consumer in 'Authorized local consumer:', 'Unauthorized consumer:') {
            if (-not $row.Contains($consumer)) {
                $errors.Add("Missing '$consumer' obligation in $($privacyRule.Id).")
            }
        }
    }
    $model = $Documents['docs/security/foundation-threat-model.md']
    if ($null -ne $model -and $model -notmatch 'No authority expansion or data egress risk is accepted') {
        $errors.Add('Missing explicit residual-risk acceptance status.')
    }
    return $errors.ToArray()
}

$documents = @{}
foreach ($path in $requirements.Keys) {
    $fullPath = Join-Path $RepositoryRoot $path
    if (Test-Path -LiteralPath $fullPath -PathType Leaf) {
        $documents[$path] = Get-Content -LiteralPath $fullPath -Raw
    }
}
$errors = @(Get-DocumentErrors $documents)
if ($errors.Count -gt 0) {
    $errors | ForEach-Object { Write-Output "FAIL $_" }
    exit 1
}
Write-Output 'PASS security documents: sections, threat/extension/risk/invariant rows and citation ranges.'

function Assert-Rejected([string] $Name, [hashtable] $Candidate, [string] $Expected) {
    $failures = @(Get-DocumentErrors $Candidate)
    if (-not ($failures | Where-Object { $_ -like "*$Expected*" })) {
        throw "Negative case '$Name' did not report '$Expected'."
    }
    Write-Output "PASS negative: $Name."
}

$threatPath = 'docs/security/foundation-threat-model.md'
$invariantPath = 'docs/security/authority-invariants.md'
$evidencePath = 'docs/evidence/foundation/security-review.md'
$case = $documents.Clone(); $case.Remove($threatPath)
Assert-Rejected 'missing document' $case 'Missing document'
$case = $documents.Clone(); $case[$threatPath] = $case[$threatPath] -replace '(?ms)^## Assets\r?\n.*?(?=^## )', "## Assets`n`n"
Assert-Rejected 'empty assets section' $case "Missing or empty section 'Assets'"
$case = $documents.Clone(); $case[$threatPath] = $case[$threatPath] -replace '(?m)^\| T-07 \|.*\r?\n', ''
Assert-Rejected 'missing replay threat' $case 'Expected one T-07 row'
$case = $documents.Clone(); $case[$invariantPath] = $case[$invariantPath] -replace '(?m)^\| AI-03 \|.*$', '| AI-03 | Core enforcement | Stop safely | | Negative case |'
Assert-Rejected 'invariant without enforcement owner' $case 'Incomplete AI-03 row'
$case = $documents.Clone(); $row = [regex]::Match($case[$invariantPath], '(?m)^\| AI-01 \|.*$').Value
$case[$invariantPath] += "`n" # Insert duplicate inside its section, not after it.
$case[$invariantPath] = $case[$invariantPath].Replace($row, "$row`n$row")
Assert-Rejected 'duplicate owner approval invariant' $case 'Expected one AI-01 row'
$case = $documents.Clone(); $case[$threatPath] = $case[$threatPath] -replace '(?m)^\| E-04 \|.*\r?\n', ''
Assert-Rejected 'missing remote extension' $case 'Expected one E-04 row'
$case = $documents.Clone(); $case[$threatPath] = $case[$threatPath].Replace('No authority expansion or data egress risk is accepted', 'Risk acceptance unspecified')
Assert-Rejected 'missing explicit risk acceptance status' $case 'Missing explicit residual-risk acceptance status'
$case = $documents.Clone(); $case[$evidencePath] += "`n``docs/absent-source.md:1``"
Assert-Rejected 'missing citation source' $case 'Missing citation source'
$case = $documents.Clone(); $case[$evidencePath] += "`n``docs/adr/0003-foundation-persistence.md:999999``"
Assert-Rejected 'citation outside source range' $case 'Invalid citation range'
$case = $documents.Clone(); $case[$evidencePath] = $case[$evidencePath].Replace('docs/specs/2026-11-06-synapse-0.3-decision-charter.md', 'charter-unspecified.md')
Assert-Rejected 'missing binding charter' $case 'Missing binding charter path'
$case = $documents.Clone(); $case[$invariantPath] = $case[$invariantPath] -replace '(?m)^\| PC-01 \|.*\r?\n', ''
Assert-Rejected 'missing authorized local context positive test' $case 'Expected one PC-01 row'
$case = $documents.Clone(); $case[$invariantPath] = $case[$invariantPath] -replace '(?m)(^\| AI-07 \|.*)Authorized local consumer:', '$1Consumer:'
Assert-Rejected 'redaction invariant missing authorized consumer obligation' $case "Missing 'Authorized local consumer:' obligation in AI-07"
$case = $documents.Clone(); $case[$threatPath] = $case[$threatPath] -replace '(?m)(^\| T-09 \|.*)Unauthorized consumer:', '$1Consumer:'
Assert-Rejected 'leakage threat missing unauthorized consumer obligation' $case "Missing 'Unauthorized consumer:' obligation in T-09"
Write-Output 'PASS 13 negative cases; document structure is not runtime security validation.'
