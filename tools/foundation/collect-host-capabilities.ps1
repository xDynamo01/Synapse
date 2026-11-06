#requires -Version 7.6

[CmdletBinding()]
param([string] $OutputPath)

function Get-SynapseHostCapabilities {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $OutputPath)

    $ErrorActionPreference = 'Stop'
    $provider = $null
    $drive = $null
    $destination = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath(
        $OutputPath, [ref] $provider, [ref] $drive)
    if ($provider.Name -ne 'FileSystem') {
        throw 'OutputPath must be a filesystem path.'
    }

    $family = if ($IsWindows) { 'windows' } elseif ($IsLinux) { 'linux' } elseif ($IsMacOS) { 'macos' } else { 'unknown' }
    $architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
    if ($architecture -notin @('x64', 'x86', 'arm64', 'arm')) {
        $architecture = 'other'
    }

    $document = [ordered]@{
        captured_at = [DateTime]::UtcNow.ToString('O', [Globalization.CultureInfo]::InvariantCulture)
        os = [ordered]@{
            family = $family
            version = [Environment]::OSVersion.Version.ToString()
            architecture = $architecture
        }
        cpu = [ordered]@{ physical_cores = $null; logical_processors = [Environment]::ProcessorCount }
        memory = [ordered]@{ total_bytes = $null; available_bytes = $null }
        gpus = @()
        disks = @()
        audio = [ordered]@{ endpoint_count = $null; ok_endpoint_count = $null }
        tools = [ordered]@{
            powershell_version = $PSVersionTable.PSVersion.ToString().Split('-')[0]
            available = @()
        }
        limitations = @()
    }

    if ($IsWindows) {
        try {
            $processors = @(Get-CimInstance -ClassName Win32_Processor -Property NumberOfCores, NumberOfLogicalProcessors)
            $cores = ($processors | Measure-Object -Property NumberOfCores -Sum).Sum
            $threads = ($processors | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum
            if ($cores -lt 1 -or $threads -lt $cores) {
                throw 'Incomplete CPU inventory.'
            }
            $document.cpu.physical_cores = [int] $cores
            $document.cpu.logical_processors = [int] $threads
        } catch {
            $document.limitations += [ordered]@{ probe = 'cpu'; code = 'probe_failed' }
        }

        try {
            $memory = Get-CimInstance -ClassName Win32_OperatingSystem -Property TotalVisibleMemorySize, FreePhysicalMemory
            if (-not $memory.TotalVisibleMemorySize -or $null -eq $memory.FreePhysicalMemory) {
                throw 'Incomplete memory inventory.'
            }
            $document.memory.total_bytes = [long] $memory.TotalVisibleMemorySize * 1KB
            $document.memory.available_bytes = [long] $memory.FreePhysicalMemory * 1KB
        } catch {
            $document.limitations += [ordered]@{ probe = 'memory'; code = 'probe_failed' }
        }

        try {
            $adapters = @(Get-CimInstance -ClassName Win32_VideoController -Property PNPDeviceID, AdapterRAM)
            $document.gpus = @(foreach ($adapter in $adapters) {
                $vendor = switch -Regex ($adapter.PNPDeviceID) {
                    '^PCI\\VEN_1002&' { 'amd'; break }
                    '^PCI\\VEN_8086&' { 'intel'; break }
                    '^PCI\\VEN_10DE&' { 'nvidia'; break }
                    default { 'other' }
                }
                [ordered]@{
                    vendor = $vendor
                    reported_memory_bytes = if ($adapter.AdapterRAM) { [long] $adapter.AdapterRAM } else { $null }
                }
            })
            $gpuCode = if ($adapters.Count -eq 0) { 'no_devices' } else { 'dedicated_vram_unverified' }
        } catch {
            $gpuCode = 'probe_failed'
        }
        $document.limitations += [ordered]@{ probe = 'gpu'; code = $gpuCode; fallback = 'cpu' }

        try {
            $workspaceVolume = [System.IO.Path]::GetPathRoot($PSScriptRoot).TrimEnd('\')
            $fixedDisks = @(Get-CimInstance -ClassName Win32_LogicalDisk -Filter 'DriveType = 3' -Property DeviceID, Size, FreeSpace)
            $document.disks = @(foreach ($disk in $fixedDisks) {
                [ordered]@{
                    workspace_volume = $disk.DeviceID -eq $workspaceVolume
                    total_bytes = $disk.Size
                    free_bytes = $disk.FreeSpace
                }
            })
            if ($fixedDisks.Count -eq 0) {
                $document.limitations += [ordered]@{ probe = 'disk'; code = 'no_devices' }
            } else {
                if (-not ($document.disks | Where-Object workspace_volume)) {
                    $document.limitations += [ordered]@{ probe = 'disk'; code = 'workspace_volume_unavailable' }
                }
                if ($document.disks | Where-Object { $null -eq $_.total_bytes -or $null -eq $_.free_bytes }) {
                    $document.limitations += [ordered]@{ probe = 'disk'; code = 'measurement_unavailable' }
                }
            }
        } catch {
            $document.limitations += [ordered]@{ probe = 'disk'; code = 'probe_failed' }
        }

        try {
            $endpoints = @(Get-CimInstance -ClassName Win32_PnPEntity -Filter "PNPClass = 'AudioEndpoint'" -Property Status)
            $document.audio.endpoint_count = $endpoints.Count
            $document.audio.ok_endpoint_count = @($endpoints | Where-Object Status -eq 'OK').Count
            if ($endpoints.Count -eq 0) {
                $document.limitations += [ordered]@{ probe = 'audio'; code = 'no_devices' }
            }
        } catch {
            $document.limitations += [ordered]@{ probe = 'audio'; code = 'probe_failed' }
        }
    } else {
        foreach ($probe in 'cpu', 'memory', 'disk', 'audio') {
            $document.limitations += [ordered]@{ probe = $probe; code = 'unsupported_platform' }
        }
        $document.limitations += [ordered]@{ probe = 'gpu'; code = 'unsupported_platform'; fallback = 'cpu' }
    }

    $toolNames = 'cargo', 'dotnet', 'ffmpeg', 'git', 'lms', 'node', 'npm', 'nvidia-smi', 'ollama', 'pnpm', 'python', 'rustc', 'uv'
    $document.tools.available = @(foreach ($tool in $toolNames) {
        if (Get-Command -Name $tool -CommandType Application, ExternalScript -ErrorAction SilentlyContinue) {
            $tool
        }
    })

    $json = ConvertTo-Json -InputObject $document -Depth 8
    [System.IO.File]::WriteAllText($destination, $json + "`n")
}

if ($MyInvocation.InvocationName -ne '.') {
    if (-not $PSBoundParameters.ContainsKey('OutputPath')) {
        throw 'Specify -OutputPath for the host capability JSON.'
    }
    Get-SynapseHostCapabilities -OutputPath $OutputPath
}
