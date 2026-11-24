param([ValidateSet('idle','thinking','listening')][string[]]$Mode = @('idle','thinking','listening'))

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$source = Join-Path $repo 'target/presence-blender/desktop-hd'
$assets = Join-Path $repo 'backend/desktop-slint/ui/assets'
foreach ($state in $Mode) {
    $folder = Join-Path $source $state
    foreach ($index in 1..480) {
        if (!(Test-Path -LiteralPath (Join-Path $folder ('frame-{0:D4}.png' -f $index)) -PathType Leaf)) {
            throw "Quadro ausente em $state ($index)."
        }
    }
    & ffmpeg -hide_banner -loglevel error -y -i (Join-Path $folder 'frame-%04d.png') -frames:v 480 -pix_fmt yuvj444p -q:v 2 (Join-Path $folder 'encoded-%04d.jpg')
    if ($LASTEXITCODE -ne 0) { throw "Falha ao codificar $state." }
    $destination = Join-Path $assets "presence-$state.frames"
    $staged = "$destination.tmp"
    $writer = [IO.BinaryWriter]::new([IO.File]::Create($staged))
    try {
        $paths = 1..480 | ForEach-Object { Join-Path $folder ('encoded-{0:D4}.jpg' -f $_) }
        $offset = 481 * 4
        $writer.Write([uint32]$offset)
        foreach ($path in $paths) {
            $offset += (Get-Item -LiteralPath $path).Length
            $writer.Write([uint32]$offset)
        }
        foreach ($path in $paths) { $writer.Write([IO.File]::ReadAllBytes($path)) }
    } finally { $writer.Dispose() }
    [IO.File]::Move($staged, $destination, $true)
}
