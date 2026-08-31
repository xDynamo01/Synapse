# Tools Runtime

Status: **Implemented / Frozen**.

`RuntimeToolRegistry` is the single public descriptor catalog and
`ToolRuntime.execute_tool_call` is the single execution authority. Active tools require an object input
schema, explicit permission, risk, and truthful preview/dry-run/cancel/rollback
metadata. Registration rejects invalid schemas and conflicting IDs.

The pipeline resolves, validates arguments, evaluates policy, builds preview/config
hash, checks approval, executes only registered handlers, records lifecycle and emits
redacted events. Missing PermissionBridge denies execution. Idempotency returns the
original result, including after restart; retry requires an explicitly idempotent
tool; rollback requires a real handler implementation. Builtin, MCP, and Desktop
technology operations are explicit adapters behind the same boundary. Compatibility
descriptors do not alter the frozen public listing. `danger.mock` is registered only
in explicit test mode.
