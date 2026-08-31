# ADR 0086: Agent Tool Intent Runtime

## Status

Accepted.

## Context

Agents can discover policy-aware tools and users can execute tools explicitly through Tool Runtime. A durable intermediate representation is required before any model/provider function-calling integration so proposed tool use can be inspected without being treated as execution.

## Decision

Add `ToolIntentRuntime` under `backend/synapse/tool_intents/` with YAML persistence in `DATA_DIR/tool_intents/{intent_id}.yaml`.

A `ToolIntent` records the proposed tool, arguments, source, optional agent/conversation/mission linkage, correlation metadata, status, a basic tool-definition snapshot, and a dry-run permission decision snapshot.

Creation validates the tool through Tool Runtime and evaluates Tool Permission Bridge with `dry_run=True`. Review refreshes that decision. Neither operation calls `ToolRuntime.execute()` or creates an `ApprovalRequest`.

Intent approval means only that the proposal was reviewed and accepted. It is not operational tool authorization. Any future execution runtime must revalidate current permissions, capabilities, resource scope, policy, and approval requirements before invoking a handler.

Supported review transitions are deliberately small:

- proposed/reviewed to approved;
- proposed/reviewed to rejected;
- non-terminal, non-executed intents to cancelled.

No execution transition is exposed in this stage.

## Interfaces

Commands:

- `/tool-intents`
- `/tool-intent <intent_id>`
- `/propose-tool <tool_id> [key=value ...]`
- `/approve-tool-intent <intent_id>`
- `/reject-tool-intent <intent_id>`
- `/cancel-tool-intent <intent_id>`

API:

- `GET /tool-intents`
- `GET /tool-intents/{intent_id}`
- `POST /tool-intents`
- `POST /tool-intents/{intent_id}/approve`
- `POST /tool-intents/{intent_id}/reject`
- `POST /tool-intents/{intent_id}/cancel`

Health and readiness expose runtime availability and pending review count.

## Consequences

Synapse has a durable boundary between proposed and executed tool use. Future model adapters may create intents without receiving an execution path.

No automatic execution, function calling, MCP, planner, workflow engine, model integration, or new UI is introduced.
