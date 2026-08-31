# Canonical Tool Execution Boundary

Status: **Implemented / Frozen — backend remains NOT READY**.

`RuntimeToolRegistry` is the only public tool catalog. It owns descriptors and
handler references, validates registration schemas, rejects conflicting IDs, and
never executes, authorizes, starts providers, or persists execution history.
`MCPRegistry` and `ExecutionTargetRegistry` remain provider/routing-local technical
indexes; neither is a public source of tool identity.

`ToolRuntime` is the only operational authority. Every call follows the same order:
identity resolution, input-schema validation, Policy/Permission decision, risk and
Approval evaluation, preview/dry-run handling, execution with timeout, canonical
status/idempotency/history, structured verification, events/audit, and a
`ToolExecutionResult`. Missing governance fails closed.

## Identity and registration

Existing public IDs are preserved. Builtins retain their historical IDs, runtime
tools retain dotted IDs, MCP uses `mcp:<server>:<tool>`, and Desktop integration uses
internal `desktop:runtime:<operation>` IDs. Every descriptor declares source,
provider, version, schemas, risk, permissions/capabilities, and truthful
preview/dry-run/cancel/rollback support. Compatibility and internal descriptors are
registered in the same catalog but excluded from the frozen public `/tools` listing.

Bootstrap constructs one registry, registers builtin descriptors, constructs one
executor, explicitly registers runtime, Desktop, and MCP adapters, and injects the
same `ToolExecutionPort` into discovery and consumers. There is no autoimport or
bidirectional catalog synchronization.

## Adapters

- Builtin adapters translate a canonical request to the frozen builtin operation.
- `MCPToolExecutorAdapter` performs only MCP protocol execution after the boundary.
- `DesktopAutomationToolAdapter` performs only Desktop preview/execute/cancel/recover
  after the boundary and returns the domain's real verification evidence.

Adapters do not own Policy, Permission, Approval, global history, or public identity.
Desktop keeps its frozen domain governance and technical plan/result persistence;
those records are referenced details, not a competing global tool history.

## Execution semantics

Preview never invokes a handler. Dry-run returns a canonical decision without side
effects. Unsupported preview/dry-run/cancel/rollback operations return structured
errors. Idempotency keys are restored from the redacted JSONL execution history, so
a completed key is not executed again after restart. Active executions have a
`running` record; cancellation is idempotent and delegates only to adapters that
declare and implement it. Retry creates a related call and still traverses the full
boundary. Timeouts return `timed_out`; worker threads are daemonized, while a future
process adapter must additionally terminate its own process group.

Every terminal attempt records structured verification. Generic verification records
status and output shape; Desktop evidence remains the authoritative domain
verification carried through adapter output. Rollback is exposed only where a real
handler implements it.

## Compatibility and preserved findings

API paths, operation IDs, schemas, Commands, builtin outputs/errors, MCP IDs, and
Desktop behavior remain frozen. `ToolRouter` is now a DTO compatibility facade over
`ToolRuntime`, not an executor. General provider taxonomy, Storage, unrelated SCCs,
Agent Creator, and DataDir maintenance were not changed. The backend remains
**NOT READY** because those architectural blockers remain.
