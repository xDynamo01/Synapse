param(
    [string]$Blender = 'F:/SteamLibrary/steamapps/common/Blender/blender.exe',
    [ValidateSet('still', 'loop')][string]$Mode = 'still',
    [ValidateSet(360, 540, 720)][int]$Size = 540,
    [int]$Seed = 2420,
    [string]$Artwork,
    [switch]$Circuits,
    [switch]$Relief,
    [switch]$Sphere,
    [switch]$Wrap
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if ($Artwork -and $Circuits) { throw 'Selecione Artwork ou Circuits.' }
if ($Relief -and !$Artwork) { throw 'Relief requer Artwork.' }
if ($Wrap -and (!$Artwork -or $Relief)) { throw 'Wrap requer Artwork e é separado de Relief.' }
if ($Sphere -and ($Artwork -or $Circuits)) { throw 'Sphere é um modo separado.' }
$variant = if ($Wrap) { 'wrap-' } elseif ($Sphere) { 'sphere-' } elseif ($Relief) { 'relief-' } elseif ($Artwork) { 'reference-' } elseif ($Circuits) { 'circuits-' } else { '' }
$output = Join-Path $repo "target/presence-blender/$variant$Mode-$Size-$Seed"
$scene = Join-Path $PSScriptRoot 'presence.py'
$null = New-Item -ItemType Directory -Path $output -Force
[string[]]$artworkArgs = if ($Artwork) { @('--artwork', (Resolve-Path -LiteralPath $Artwork).Path) } elseif ($Circuits) { @('--circuits') } else { @() }
if ($Relief) { $artworkArgs += '--relief' }
if ($Sphere) { $artworkArgs += '--sphere' }
if ($Wrap) { $artworkArgs += '--wrap' }
& $Blender --background --factory-startup --disable-autoexec --python-exit-code 3 --python $scene -- --output $output --size $Size --seed $Seed --mode $Mode @artworkArgs
if ($LASTEXITCODE -ne 0) { throw "Blender exited with code $LASTEXITCODE." }
if ($Mode -eq 'loop') {
    & ffmpeg -hide_banner -loglevel error -y -framerate 24 -start_number 1 -i (Join-Path $output 'frames/presence-%04d.png') -frames:v 144 -c:v libx264 -pix_fmt yuv420p -movflags +faststart (Join-Path $output 'artemis-presence.mp4')
    if ($LASTEXITCODE -ne 0) { throw "FFmpeg exited with code $LASTEXITCODE." }
}
Write-Output $output
