# Hardware Runtime

Status: **Implemented / Frozen**.

`HardwareRuntime`, `DiskRuntime`, and `ProcessRuntime` are separate read-only
consumers of a `PlatformInsightProvider`.

- CPU: model, architecture, physical cores, logical threads, current utilization,
  and frequency; temperature/cache only when measurable.
- RAM: total, available, used, swap, and utilization; compression only when a
  provider can measure it.
- GPU: name, vendor, driver, VRAM totals/current use/free space, utilization,
  temperature, clock, provider, and detected capabilities.
- Other hardware: sanitized motherboard manufacturer/model, bounded sensors,
  batteries, and power state when supported.
- Storage: anonymous volume IDs, filesystem, capacity/use, removable indication,
  and aggregate I/O counters.
- Processes: bounded PID/parent/name/CPU/RAM projection with Synapse-process
  classification. Command lines, executable paths, open files, and environment
  are never collected.

Windows uses NVIDIA SMI when available and a CIM VideoController fallback;
Linux supports NVIDIA SMI, ROCm SMI, and partial `lspci`; macOS uses sanitized
`system_profiler` JSON and reports Metal only when evidenced. CUDA, ROCm, Metal,
and OpenCL are declared only when the corresponding probe supports the claim.
Missing GPUs, drivers, sensors, batteries, or dynamic VRAM metrics are honest
limitations and do not make the backend unready.
