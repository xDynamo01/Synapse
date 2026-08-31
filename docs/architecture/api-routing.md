# API routing architecture

The HTTP layer is split into 13 bounded-context routers under
`backend/synapse/api/routers`. `api/router_registry.py` is the only registration
point. `api/routes.py` is an eight-line compatibility import and contains no
handlers, DTOs, helpers, or runtime composition.

## Bounded contexts

| Router | Responsibility | Operations |
| --- | --- | ---: |
| `agents` | agent directory, provisioning, administration and identity | 42 |
| `automation` | jobs, scheduler, daemon and tasks | 17 |
| `conversations` | conversations, messages and chat transport | 21 |
| `desktop_automation` | governed desktop/application actions | 11 |
| `memory` | memory CRUD/search/import/export and context preview | 13 |
| `missions` | delegation, missions, attempts, workers, swarm and recovery | 103 |
| `models` | model hub, provider facades and settings | 36 |
| `perception` | vision, capture, multimodal and perception | 42 |
| `platform` | policy, approvals, events, retention, migrations and foundation endpoints | 48 |
| `system` | health/readiness and system insight read models | 21 |
| `tools` | tool execution, intents, MCP and execution routing | 31 |
| `voice` | voice, audio and speech | 43 |
| `world_attention_loop` | world state, attention and Agent Loop | 22 |

DTOs specific to HTTP live in the owning router. Domain models remain in their
domain and neutral contracts remain in `synapse.contracts`. `LocalChatRequest`
is owned by Conversations and reused by Agents without duplication.

## Handler rules

A handler may validate a DTO, translate headers to the canonical permission
context, call a container facade, map a known error and serialize the result.
Routers may not import stores, storage, queues, concrete providers, bootstrap,
or feature builders; instantiate runtimes; access `DataDir`; or persist files.
These rules are AST-tested in `tests/architecture/test_api_routing_boundaries.py`.

Shared transport helpers are intentionally small:

- `runtime_from`: fetch the lifespan-owned container;
- `context_from`: translate actor headers;
- `payload_dict`: Pydantic compatibility serialization;
- `require_admin`: preserve the administrative-header contract.

Desktop Automation retains three local DTO-to-domain mappers. No global schema
module or generic service locator was introduced.

## Registration and compatibility

The registry keeps an explicit ordered tuple of all domain routers. Because the
FastAPI version used here defers nested router inclusion and does not recursively
expand a second aggregate level, the compatibility aggregate registers the
already-built route objects from each domain router. It does not construct
runtimes or duplicate endpoints.

The frozen OpenAPI baseline contains no tags. Adding router tags would change
the contract, so Phase 2 preserves the empty tag set. Tags require a separately
approved API contract change.

## Findings retained

- Agent provisioning remains separate from presentation concerns; the removed
  backend presentation runtimes are not part of API routing.
- `api/foundation_adapter.py` isolates the three existing DataDir diagnostics
  and cleanup endpoints. A neutral maintenance facade does not yet exist.
- Some handlers perform response shaping, bounded list comprehensions, base64
  request decoding or `FileResponse` construction. These are transport work,
  not policy or storage ownership.

These findings were not expanded into new subsystems. Commands, Health, Tools,
Providers and Storage were not decomposed or consolidated.
