param(
    [string] $RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
)

$ErrorActionPreference = "Stop"

$appRoot = Join-Path $RepositoryRoot "apps\frontend-v2"
$electronExe = Join-Path $appRoot "node_modules\electron\dist\electron.exe"
$mainScript = Join-Path $appRoot "dist\main\main\main.js"
$iconPath = Join-Path $appRoot "assets\icons\synapse.ico"
$rootExe = Join-Path $RepositoryRoot "Synapse.exe"

if (-not (Test-Path -LiteralPath $electronExe)) {
    throw "Electron runtime not found. Run npm install in apps\frontend-v2 first."
}
if (-not (Test-Path -LiteralPath $mainScript)) {
    throw "Frontend build not found. Run npm run build in apps\frontend-v2 first."
}
if (-not (Test-Path -LiteralPath $iconPath)) {
    throw "Synapse icon not found at apps\frontend-v2\assets\icons\synapse.ico."
}

$source = @"
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class SynapseLauncher
{
    [STAThread]
    private static int Main()
    {
        string repositoryRoot = AppDomain.CurrentDomain.BaseDirectory;
        string appRoot = Path.Combine(repositoryRoot, "apps", "frontend-v2");
        string electronExe = Path.Combine(appRoot, "node_modules", "electron", "dist", "electron.exe");
        string mainScript = Path.Combine(appRoot, "dist", "main", "main", "main.js");

        if (!File.Exists(electronExe) || !File.Exists(mainScript))
        {
            MessageBox.Show(
                "Synapse frontend build is missing. Run apps/frontend-v2 build first.",
                "Synapse",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return 1;
        }

        var process = new ProcessStartInfo
        {
            FileName = electronExe,
            Arguments = "\"" + mainScript + "\"",
            WorkingDirectory = appRoot,
            UseShellExecute = false,
            CreateNoWindow = true
        };
        Process.Start(process);
        return 0;
    }
}
"@

$sourceFile = Join-Path $env:TEMP "SynapseLauncher.cs"
Set-Content -LiteralPath $sourceFile -Value $source -Encoding UTF8
$compiler = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path -LiteralPath $compiler)) {
    throw "C# compiler not found at $compiler."
}
& $compiler /nologo /target:winexe /out:$rootExe /win32icon:$iconPath /reference:System.dll /reference:System.Windows.Forms.dll $sourceFile
if ($LASTEXITCODE -ne 0) {
    throw "Synapse root launcher compilation failed with exit code $LASTEXITCODE."
}
Write-Output "root_launcher=$rootExe"
