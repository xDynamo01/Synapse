# Synapse 0.3 clean-room

## Pasta oficial de desenvolvimento

O trabalho atual está diretamente em `F:\Projetos\Synapse`, na branch local
`0.3-cleanroom`. Código, decisões e documentação estão nesta mesma árvore.
Não há uma área de desenvolvimento aninhada em `.worktrees`.

As cópias e dependências históricas foram preservadas separadamente em
`F:\Projetos\Synapse-Arquivo-Local\consolidacao-2026-11-10`.
Veja o [registro de consolidação](docs/evidence/backend/2026-11-10-workspace-consolidation.md)
para os destinos, verificações e testes executados após a mudança de pasta.

## Estado do projeto

Synapse0.3 is being rebuilt as one integrated Rust backend with supervised
local Python AI, followed by a native Rust frontend. Product source is under
`backend/`; historical prototypes remain under `experiments/`.

Owner amendment 2026-11-09: **native Rust application/device integration plus
Python AI**. The owner subsequently approved integrated-backend-first delivery.
The [active backend plan](docs/superpowers/plans/2026-11-09-integrated-backend.md)
supersedes the old UI-before-backend gate. Historical Gate00 has not passed;
native UI/device and platform validation remain capability-specific obligations.
Electron Plan01 is superseded. Historical JS/TS experiments remain evidence
only and are not product dependencies.

## Backend development

```powershell
cargo test -p synapse-core --locked
$env:SYNAPSE_PYTHON_EXECUTABLE = py -3.14 -c "import sys; print(sys.executable)"
cargo run -p synapse-core --bin synapse-backend -- --state-dir .local/backend --workspace .
```

The process accepts one versioned JSON request per line on stdin and returns
one JSON response per line. It has no network listener. For example:

```json
{"version":1,"request_id":"health-1","command":{"type":"health"}}
```

See [v1 contracts](backend/contracts/v1/README.md) for available commands,
limits and lifecycle semantics. Capability status is explicit; a registered
model or Skill is not by itself an operational inference/tool capability.

Reviewed Windows journeys with an existing local model cover
[automatic source-backed memory](docs/evidence/backend/2026-11-10-automatic-memory.md),
[pinned Skill guidance](docs/evidence/backend/2026-11-10-skill-guidance.md), and
[explicit cross-chat canonical context](docs/evidence/backend/2026-11-10-contextual-conversation.md).
The last uses the Core reference contract; natural-language project resolution,
planner, routing, Skill evolution, temporary Swarm, voice/browser operation and
native frontend remain subsequent work. Linux/macOS runtime operation and portable
packaging have not been validated by these Windows runs.

- [Architecture design](docs/specs/2026-11-06-synapse-0.3-clean-room-design.md)
- [Binding decision charter](docs/specs/2026-11-06-synapse-0.3-decision-charter.md)
- [Reference proposals](docs/reference/proposals/)
- [Historical pre-clean-room evidence](docs/archive/pre-cleanroom/v0.3/)

The `0.2` branch is historical reference only. No implementation from that
branch may be copied into the 0.3 runtime.
