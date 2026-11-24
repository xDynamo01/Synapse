$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$renderRoot = Join-Path $repo 'target/presence-blender'
$assets = Join-Path $repo 'backend/desktop-slint/ui/assets'
$sources = @{
    idle = @('orbit-loop-v1', 'orbit')
    thinking = @('thinking-loop-v2', 'thinking')
    listening = @('listening-loop-v1', 'listening')
}

foreach ($mode in $sources.Keys) {
    $folder, $prefix = $sources[$mode]
    $frames = Join-Path $renderRoot "$folder/frames"
    foreach ($page in 0..3) {
        $manifest = Join-Path $frames "slint-atlas-$page.ffconcat"
        $entries = foreach ($tile in 0..39) {
            $number = 1 + (40 * $page + $tile) * 3
            $frame = '{0}-{1:D4}.png' -f $prefix, $number
            if (!(Test-Path -LiteralPath (Join-Path $frames $frame) -PathType Leaf)) {
                throw "Quadro ausente: $frame"
            }
            "file '$frame'"
        }
        $entries | Set-Content -LiteralPath $manifest -Encoding ascii
        $output = Join-Path $assets "presence-$mode-$page.png"
        & ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i $manifest -vf 'tile=8x5' -fps_mode passthrough -frames:v 1 -update 1 $output
        if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $output -PathType Leaf)) {
            throw "Falha ao exportar $mode, página $page."
        }
    }
}
