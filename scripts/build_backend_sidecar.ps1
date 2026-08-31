param(
    [Parameter(Mandatory = $true)]
    [string]$PythonPath
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = (Resolve-Path $PythonPath).Path
$version = & $python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
if ($LASTEXITCODE -ne 0 -or -not $version.StartsWith("3.12.")) {
    throw "Release backend requires Python 3.12.x; received $version"
}
$pyinstallerVersion = & $python -c "import PyInstaller; print(PyInstaller.__version__)"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller is unavailable" }

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --name synapse_backend `
    --onedir `
    --console `
    --paths (Join-Path $repositoryRoot "backend") `
    --add-data "$((Join-Path $repositoryRoot "backend\synapse\resources"));synapse\resources" `
    --additional-hooks-dir (Join-Path $repositoryRoot "scripts\pyinstaller-hooks") `
    --collect-submodules synapse `
    --collect-all faster_whisper `
    --hidden-import ctranslate2 `
    --hidden-import tokenizers `
    --hidden-import av `
    --hidden-import huggingface_hub `
    --exclude-module pytest `
    --exclude-module py `
    --distpath (Join-Path $repositoryRoot "backend\dist") `
    --workpath (Join-Path $repositoryRoot "backend\build\rc-sidecar") `
    --specpath (Join-Path $repositoryRoot "backend\build") `
    (Join-Path $repositoryRoot "backend\synapse\sidecar.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

Write-Output "python=$version"
Write-Output "pyinstaller=$pyinstallerVersion"
Write-Output "output=$(Join-Path $repositoryRoot 'backend\dist\synapse_backend')"
