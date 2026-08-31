param(
    [Parameter(Mandatory = $true)]
    [string] $SidecarPath
)

$ErrorActionPreference = "Stop"

$resolvedSidecar = (Resolve-Path -LiteralPath $SidecarPath).Path
$dataDir = Join-Path $env:TEMP ("SynapsePackedVoiceSmoke" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $dataDir | Out-Null

$processInfo = New-Object System.Diagnostics.ProcessStartInfo
$processInfo.FileName = $resolvedSidecar
$processInfo.WorkingDirectory = Split-Path -Parent $resolvedSidecar
$processInfo.UseShellExecute = $false
$processInfo.RedirectStandardOutput = $true
$processInfo.RedirectStandardError = $true
$processInfo.Environment["SYNAPSE_DATA_DIR"] = $dataDir
$processInfo.Environment["SYNAPSE_LOG_LEVEL"] = "warning"
$processInfo.Arguments = "--host 127.0.0.1 --port 0"

$process = [System.Diagnostics.Process]::Start($processInfo)
try {
    $handshakePath = Join-Path $dataDir "runtime\backend-handshake.json"
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline -and -not (Test-Path -LiteralPath $handshakePath)) {
        Start-Sleep -Milliseconds 250
    }
    if (-not (Test-Path -LiteralPath $handshakePath)) {
        throw "Sidecar handshake timeout."
    }

    $handshake = Get-Content $handshakePath -Raw | ConvertFrom-Json
    $base = "http://127.0.0.1:$($handshake.port)/api"
    $health = Invoke-RestMethod -Uri "$base/health" -Method Get
    $packs = Invoke-RestMethod -Uri "$base/voice/packs" -Method Get
    $voices = Invoke-RestMethod -Uri "$base/voice/voices" -Method Get

    $pack = $packs | Where-Object { $_.pack_id -eq "synapse-default-v0.01" } | Select-Object -First 1
    if (-not $pack) {
        throw "Default voice pack was not discovered."
    }
    if ($pack.status -ne "ready") {
        throw "Default voice pack is not ready: $($pack.status)."
    }
    if (@($voices).Count -ne 6) {
        throw "Expected exactly 6 voices, got $(@($voices).Count)."
    }

    $synthBody = @{
        text = "Hello from Synapse voice runtime."
        provider_id = "piper"
        voice_id = "synapse-bryce"
        language = "en-US"
        metadata = @{}
    } | ConvertTo-Json -Depth 8
    $synth = Invoke-RestMethod -Uri "$base/audio/synthesize" -Method Post -ContentType "application/json" -Body $synthBody
    if (-not $synth.audio_base64 -or $synth.audio_base64.Length -le 1000) {
        throw "TTS did not return a usable audio payload."
    }

    $transcribeBody = @{
        audio_base64 = $synth.audio_base64
        audio_format = "audio/wav"
        provider_id = "faster_whisper"
        model = "tiny"
        language = "en-US"
        duration_ms = $synth.duration_ms
        metadata = @{}
    } | ConvertTo-Json -Depth 8
    $transcription = Invoke-RestMethod -Uri "$base/audio/transcribe" -Method Post -ContentType "application/json" -Body $transcribeBody
    if ($transcription.provider_id -ne "faster_whisper") {
        throw "Unexpected STT provider: $($transcription.provider_id)."
    }
    if ($transcription.status -notin @("success", "no_speech_detected")) {
        throw "Unexpected STT status: $($transcription.status)."
    }

    [pscustomobject]@{
        health = $health.status
        pack_status = $pack.status
        voice_count = @($voices).Count
        synth_provider = $synth.provider_id
        synth_voice = $synth.voice_id
        synth_audio_chars = $synth.audio_base64.Length
        synth_duration_ms = $synth.duration_ms
        stt_provider = $transcription.provider_id
        stt_status = $transcription.status
        stt_text = $transcription.text
        stt_resolved_model = $transcription.metadata.resolved_model
    } | Format-List
}
finally {
    if (-not $process.HasExited) {
        $process.Kill()
        $process.WaitForExit()
    }
    Remove-Item -LiteralPath $dataDir -Recurse -Force -ErrorAction SilentlyContinue
}
