# Clipboard Runtime

Status: **Implemented / Frozen**.

`ClipboardRuntime` provides get, set, clear, snapshot, and restore through the
platform provider. Public reads return content type, length, and digest; they do
not reveal content. Plan/API/command writes externalize content to an in-memory
vault before persistence and emit only length/digest telemetry.

Before a clipboard mutation, Desktop execution captures a transient snapshot.
Failure or cancellation restores it when the OS made restoration possible. The
snapshot token and content are removed after restoration or successful plan
completion. Rollback reports `available: false` where no safe compensation
exists.
