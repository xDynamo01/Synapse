# Tools + Execution + Approvals + MCP Finalization Report

Date: 2026-07-11

## Inventory

| Component | Initial state | Main debt |
| --- | --- | --- |
| ToolRuntime | newer executor | permissive fallback, weak schema/lifecycle |
| ToolRouter | legacy agent executor | parallel execution path |
| Registry/discovery | definitions/catalog | conflicts and weak schema |
| PermissionBridge | policy/approval | ignored supplied approval ID |
| MCP bridge | projected tools | execution unavailable |
| API | multiple execution surfaces | legacy registry bypass |
| production seeds | builtins | contained `danger.mock` |

Initial focused result: `101 passed, 1 failed`; the failure was an incomplete agent
fixture in `test_tool_intents`.

## Corrections

- Added final descriptor/request/preview/result/status contracts and ToolError.
- Added registry conflict/schema checks and argument validation.
- Added previews, dry-run isolation, hashes, idempotency, history, status, cancel,
  restricted retry and truthful rollback.
- Changed missing PermissionBridge from allow to deny.
- Fixed approved-call validation/consumption and call-ID binding.
- Removed production `danger.mock`; retained it only in explicit test mode.
- Added executable MCP adapters and canonical colon IDs through ToolRuntime.
- Redirected the legacy API execution route to ToolRuntime.
- Corrected fixtures and added schema/idempotency/MCP regressions.

## Validation

- Integrated focused/frozen-domain suite: `168 passed` before global validation.
- Final global: `927 collected`, `825 passed`, `102 failed` in `833.77s`.
- Tools + Execution + Approvals + MCP failures globally: `0`.
- Frozen upstream domains remain green.
- Ruff passed repository-wide; OpenAPI has no duplicates.
- `git diff --check` passed with line-ending warnings only.
- Two regressions were added and the prior `tool_intents` failure was eliminated.
