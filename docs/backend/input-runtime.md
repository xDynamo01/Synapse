# Input Runtime

Status: **Implemented / Frozen**.

`InputRuntime` is fallback-only. Windows uses native pointer input and a
stdin-fed keyboard bridge; Linux uses `xdotool` only when installed; macOS uses
the Accessibility/System Events boundary. Text is sent over stdin rather than a
process command line where the OS adapter supports an external command.

Pointer actions require freshly measured element bounds and use their center.
No plan persists a coordinate and no action relies on a fixed screen position.
Keyboard, hotkey, scroll, and pointer actions are unavailable when the relevant
provider cannot meet these guarantees. Semantic Value/Invoke patterns remain
preferred.
