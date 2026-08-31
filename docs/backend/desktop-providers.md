# Desktop Providers

The platform-selected accessibility and input providers plus the explicit OCR and
Vision fallback providers are projected for discovery after `DesktopRuntime` is
constructed. Execution order, governance and fallback policy remain owned by the
desktop domain; the canonical catalog cannot perform desktop actions.

Status: **Implemented / Frozen**.

| Provider | Discovery and semantic action |
| --- | --- |
| Windows UI Automation | EnumWindows, UIAutomationClient tree/patterns, native window control |
| Linux AT-SPI | AT-SPI accessible tree/actions with `wmctrl` window discovery when installed |
| macOS Accessibility | System Events/JXA accessible tree/actions and generic window lifecycle |
| OCR fallback | authorized transient Vision capture and configured OCR bounding blocks |
| Vision fallback | authorized transient Vision capture and configured object/icon/layout regions |

Providers are independent classes selected by a small platform map. Missing OS
permissions or optional tools produce `ProviderUnavailable`; they never simulate
success. OCR and Vision only locate/confirm candidates. `InputRuntime` performs
the final element-relative fallback, and mandatory verification decides whether
it succeeded.
