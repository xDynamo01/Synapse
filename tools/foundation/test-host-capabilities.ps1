#requires -Version 7.6

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$evidencePath = Join-Path $PSScriptRoot '../../docs/evidence/foundation'
$schemaPath = Join-Path $evidencePath 'host-capabilities.schema.json'

function Get-ScalarValues {
    param($Value)

    if ($Value -is [string]) {
        $Value
    } elseif ($Value -is [ValueType]) {
        ConvertTo-Json -InputObject $Value -Compress
    } elseif ($Value -is [System.Collections.IDictionary]) {
        foreach ($item in $Value.Values) {
            Get-ScalarValues $item
        }
    } elseif ($Value -is [System.Collections.IList]) {
        foreach ($item in $Value) {
            Get-ScalarValues $item
        }
    }
}

function Assert-HostCapabilities {
    param([string] $Json)

    if (-not (Test-Json -Json $Json -SchemaFile $schemaPath -ErrorAction SilentlyContinue)) {
        throw 'Host capabilities JSON does not match the schema.'
    }

    $document = ConvertFrom-Json -InputObject $Json -AsHashtable -DateKind String
    $gpuLimitations = @($document.limitations | Where-Object probe -eq 'gpu')
    $gpuCodes = if ($document.gpus.Count -eq 0) {
        'unsupported_platform', 'probe_failed', 'no_devices'
    } else {
        'dedicated_vram_unverified'
    }
    if ($gpuLimitations.Count -ne 1 -or $gpuLimitations[0].code -notin $gpuCodes -or $gpuLimitations[0].fallback -ne 'cpu') {
        throw 'GPU inventory requires a matching GPU limitation and explicit CPU fallback.'
    }

    $secretNamePattern = 'token|secret|pass(?:word|wd|phrase)|(?:api|access|private|signing|client|ssh)[_-]?key|credential|connection[_-]?string|auth(?:orization)?[_-]?header|cookie|database[_-]?url|(?:^|[_-])(?:auth|pat|pwd)(?:$|[_-])'
    $secretValues = Get-ChildItem Env: | Where-Object { $_.Name -match $secretNamePattern -and $_.Value } |
        Select-Object -ExpandProperty Value
    foreach ($value in (Get-ScalarValues $document)) {
        foreach ($secret in $secretValues) {
            if ($value -ceq $secret -or ($secret.Length -ge 8 -and $value.Contains($secret))) {
                throw 'Host capabilities JSON contains a value from a secret-like environment variable.'
            }
        }
    }
}

function Assert-Rejected {
    param(
        [System.Collections.IDictionary] $Document,
        [string] $Case,
        [string] $ExpectedError
    )

    try {
        Assert-HostCapabilities (ConvertTo-Json -InputObject $Document -Depth 8)
    } catch {
        if ($_.Exception.Message -ne $ExpectedError) {
            throw "Unexpected result for negative case '$Case'."
        }
        return
    }
    throw "Validator accepted negative case '$Case'."
}

$collectorPath = Join-Path $PSScriptRoot 'collect-host-capabilities.ps1'
$fixturePath = Join-Path $evidencePath 'host-capabilities.windows.json'
if (-not (Test-Path -LiteralPath $collectorPath -PathType Leaf)) {
    throw 'Missing collector script collect-host-capabilities.ps1.'
}
if (-not (Test-Path -LiteralPath $fixturePath -PathType Leaf)) {
    throw 'Missing Windows fixture host-capabilities.windows.json.'
}

$fixture = Get-Content -LiteralPath $fixturePath -Raw
Assert-HostCapabilities $fixture
$document = ConvertFrom-Json -InputObject $fixture -AsHashtable -DateKind String

$missing = $document.Clone()
[void] $missing.Remove('cpu')
Assert-Rejected $missing 'missing required field' 'Host capabilities JSON does not match the schema.'

$negative = $document.Clone()
$negative.memory = @{ total_bytes = -1; available_bytes = $null }
Assert-Rejected $negative 'negative byte quantity' 'Host capabilities JSON does not match the schema.'

$noGpu = $document.Clone()
$noGpu.gpus = @()
$noGpu.limitations = @(@{ probe = 'audio'; code = 'probe_failed' })
Assert-Rejected $noGpu 'empty GPU inventory without a GPU limitation' 'GPU inventory requires a matching GPU limitation and explicit CPU fallback.'
$noGpu.limitations = @(@{ probe = 'gpu'; code = 'dedicated_vram_unverified'; fallback = 'cpu' })
Assert-Rejected $noGpu 'empty GPU inventory with an inapplicable GPU limitation' 'GPU inventory requires a matching GPU limitation and explicit CPU fallback.'

$secret = $document.Clone()
$secret.os = $document.os.Clone()
$secret.os.version = '95432.84521.73610'
$prior = $env:SYNAPSE_TEST_API_TOKEN
try {
    $env:SYNAPSE_TEST_API_TOKEN = $secret.os.version
    Assert-Rejected $secret 'secret-like environment value' 'Host capabilities JSON contains a value from a secret-like environment variable.'
} finally {
    $env:SYNAPSE_TEST_API_TOKEN = $prior
}

$identifier = $document.Clone()
$identifier.os = $document.os.Clone()
$identifier.os.serial = 'invented-serial-number'
Assert-Rejected $identifier 'unexpected device identifier' 'Host capabilities JSON does not match the schema.'

& {
    $gpuProbe = @{ requested = $false }
    function Get-CimInstance {
        [CmdletBinding()]
        param([string] $ClassName, [string[]] $Property, [string] $Filter)

        if ($ClassName -eq 'Win32_VideoController') {
            $gpuProbe.requested = $true
        }
    }

    . $collectorPath
    $temporary = [System.IO.Path]::GetTempFileName()
    try {
        Get-SynapseHostCapabilities -OutputPath $temporary
        $json = Get-Content -LiteralPath $temporary -Raw
        Assert-HostCapabilities $json
        $result = ConvertFrom-Json -InputObject $json -AsHashtable -DateKind String
        $gpu = $result.limitations | Where-Object probe -eq 'gpu'
        $expectedCode = if ($IsWindows) { 'no_devices' } else { 'unsupported_platform' }
        if ($IsWindows -and -not $gpuProbe.requested) {
            throw 'The collector did not query the controlled Windows GPU probe.'
        }
        if ($result.gpus.Count -ne 0 -or $gpu.code -ne $expectedCode -or $gpu.fallback -ne 'cpu') {
            throw "Collector must emit an empty GPU inventory with the '$expectedCode' limitation and CPU fallback."
        }
        Write-Output "PASS collector emitted '$expectedCode' with an empty GPU inventory and CPU fallback."
    } finally {
        Remove-Item -LiteralPath $temporary
    }
}

Write-Output 'PASS host capabilities fixture and six negative cases.'
