param([Parameter(Mandatory)][string]$Frames)

$ErrorActionPreference = 'Stop'
$source = (Resolve-Path -LiteralPath $Frames).Path
foreach ($index in 1..144) {
    if (!(Test-Path -LiteralPath (Join-Path $source ('presence-{0:D4}.png' -f $index)) -PathType Leaf)) {
        throw "Missing Blender frame $index."
    }
}
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$dest = Join-Path $repo 'backend/desktop-slint/ui/assets'
$scratch = Join-Path $repo ('target/presence-slint-' + [Guid]::NewGuid().ToString('n'))
$null = New-Item -ItemType Directory -Path $scratch
$inputPattern = Join-Path $source 'presence-%04d.png'
$outputPattern = Join-Path $scratch 'artemis-loop-%d.png'
& ffmpeg -hide_banner -loglevel error -framerate 24 -start_number 1 -i $inputPattern -vf 'fps=16,scale=360:360:flags=lanczos,tile=8x6:nb_frames=48' -frames:v 2 -start_number 0 $outputPattern
if ($LASTEXITCODE -ne 0) { throw "FFmpeg exited with code $LASTEXITCODE." }
foreach ($index in 0, 1) {
    $file = "artemis-loop-$index.png"
    Copy-Item -LiteralPath (Join-Path $scratch $file) -Destination (Join-Path $dest $file)
}
