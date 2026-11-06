# Foundation host capabilities

Gate 00 Task 1 records a Windows host inventory to support later decisions
about the runtime and resource budget. The binding decisions are `CR-001`,
`CR-004`, `QA-001`, `QA-002` and `QA-003` from the
[Synapse 0.3 Decision Charter](../../specs/2026-11-06-synapse-0.3-decision-charter.md).

## Reproduce the snapshot

From the repository root with PowerShell 7.6 or later, run the collector and
check the resulting fixture.

```powershell
pwsh -NoProfile -File tools/foundation/collect-host-capabilities.ps1 -OutputPath docs/evidence/foundation/host-capabilities.windows.json
pwsh -NoProfile -File tools/foundation/test-host-capabilities.ps1
```

The output directory must already exist. To choose a separate output file from
PowerShell, dot-source the collector and call its function.

```powershell
. ./tools/foundation/collect-host-capabilities.ps1
Get-SynapseHostCapabilities -OutputPath ./host-capabilities.local
```

[The Windows snapshot](host-capabilities.windows.json) records its UTC capture
time. [The schema](host-capabilities.schema.json) limits keys and value types.
The check also verifies the GPU fallback and rejects fixture values that match
current secret-like environment values. The check exercises six negative cases.

## Interpret the measurements

- CPU counts come from Windows CIM. The logical count falls back to the
  PowerShell process's processor count if the Windows probe fails.
- Memory reports OS-visible bytes and the free physical memory at capture.
  Disks report fixed logical volume capacity and free bytes. The
  `workspace_volume` flag identifies the volume holding the collector without
  exposing its drive letter.
- Windows provides `AdapterRAM` as a 32-bit value. The snapshot keeps this as
  `reported_memory_bytes` and records the `dedicated_vram_unverified` limitation
  with a CPU fallback. A failed GPU query or an empty GPU inventory also carries
  an explicit CPU fallback. Establish a GPU budget through a separate validated
  probe before relying on dedicated VRAM.
- Audio counts installed Windows PnP audio endpoints and those reporting
  `OK`. Microphone and playback operation require separate validation.
- Tools list allowlisted commands discoverable on PATH and the running
  PowerShell version. Installed versions, shims, and runtime compatibility
  require the separate toolchain gate.
- Probes use local OS queries and command discovery. The collector writes the
  selected JSON file. It emits aggregate quantities and fixed labels, and
  omits paths, usernames, serial numbers, raw device identifiers, environment
  values and underlying exception messages.
- On other platforms, the collector records OS metadata and discoverable
  tools, and marks the Windows-specific probes unsupported. Only the Windows
  snapshot was captured on hardware for this task.

The inventory is measured evidence for later Gate 00 decisions. Operational
validation, integration regression and any platform support claims belong to
their corresponding gates.
