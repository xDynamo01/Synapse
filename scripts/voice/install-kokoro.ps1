param([string]$PythonPath = "$PSScriptRoot/../../.venv/Scripts/python.exe")
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path "$PSScriptRoot/../..").Path
$root = Join-Path $repo 'data/voice'
$runtime = Join-Path $root 'runtimes/kokoro'
$models = Join-Path $root 'models/kokoro'
New-Item -ItemType Directory -Force $models | Out-Null
if (-not (Test-Path "$runtime/Scripts/python.exe")) {
    & uv venv $runtime --python $PythonPath
    if ($LASTEXITCODE -ne 0) { throw 'Kokoro environment creation failed' }
}
& uv pip sync "$PSScriptRoot/requirements.txt" --python "$runtime/Scripts/python.exe" --require-hashes --only-binary :all:
if ($LASTEXITCODE -ne 0) { throw 'Kokoro dependencies failed' }
$assets = @{
    'kokoro-v1.0.int8.onnx' = '6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb'
    'voices-v1.0.bin' = 'bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d'
}
foreach ($name in $assets.Keys) {
    $destination = Join-Path $models $name
    if (-not (Test-Path -LiteralPath $destination)) {
        Invoke-WebRequest "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/$name" -OutFile $destination
    }
    if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $assets[$name]) {
        throw "Invalid Kokoro artifact: $name. Not activating."
    }
}
Write-Output 'Kokoro installed and hashes verified. Runtime use is offline.'
