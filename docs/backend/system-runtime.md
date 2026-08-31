# System Runtime

Status: **Implemented / Frozen**.

`SystemRuntime` exposes an immutable `SystemSnapshot` collected exclusively by
the selected platform provider. It includes OS family/version, architecture,
kernel, uptime, boot time, timezone, locale, and Python version. Host and user
fields are present for schema stability but always redacted by production
providers.

Provider selection is a small registry keyed by `platform.system()`:

| Platform | Provider |
| --- | --- |
| Windows | `WindowsInsightProvider` |
| Linux | `LinuxInsightProvider` |
| macOS/Darwin | `MacOSInsightProvider` |
| unknown | bounded `PsutilInsightProvider` fallback |

The runtime does not read environment variables, network identities, MAC
addresses, or private paths. Unsupported values are returned as `None` or an
explicit limitation; they are never synthesized.
