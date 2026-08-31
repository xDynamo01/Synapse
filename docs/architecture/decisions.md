# Architectural decisions — navigation index

Este arquivo é um índice de navegação, não uma nova autoridade arquitetural.
Decisões formais específicas, `AGENTS.md`, policies e specifications prevalecem
sobre este resumo.

## Global baseline

- [Synapse V3 Architecture](../architecture.md) — arquitetura normativa e modelo
  de status.
- [Dependency Rules](dependency-rules.md) — bounded contexts e direção das
  dependências.
- [Bootstrap](bootstrap.md) — composition root e lifecycle.
- [Evidence and Acceptance](evidence-and-acceptance.md) — evidência e critérios de
  aceitação.
- [Project Governance](project-governance.md), [RFC Gate](rfc-gate.md) e
  [Implementation Plans](implementation-plans.md) — governança RFC → Plan → Mission.
- [Operational roadmap](../roadmap/current.md) — estado atual e próximo slice.

## Durable product decisions

- [ADR 0115 — Synapse V3 Electron ADE](../adr/0115-synapse-v3-electron-ade.md) —
  Superseded by ADR 0119; retained as historical evidence for the removed frontend.
- [ADR 0119 — Retire Electron ADE implementation](../adr/0119-retire-electron-ade.md) —
  Old Electron ADE implementation removed; backend contracts remain reusable.
  cliente desktop aceito e separação frontend/backend.
- [Runtime-first foundation](../decisions/0001-runtime-first-foundation.md) — runtime
  como dono da lógica, clientes como consumidores.
- [Tool Execution Boundary](tool-execution-boundary.md) — execução governada de
  ferramentas.
- [Intelligence Trust Boundary](intelligence-trust-boundary.md) — trust,
  classificação, egress e Evidence.
- [Storage Strategy](storage-strategy.md) — ownership e seleção de persistência.

## Current and frozen bounded contexts

- [Private Evals Runtime](private-evals-runtime.md);
- [Skills Runtime Phase 2](skills-runtime-phase-2.md);
- [Sandbox Execution Boundary](sandbox-execution-boundary.md);
- [Repository Runtime](repository-runtime.md);
- [Coding Sessions](coding-sessions.md);
- [Search Runtime](search-runtime.md);
- [Deployment Runtime](deployment-runtime.md).

Os respectivos audits em `docs/audits/` registram evidência histórica de freeze e
gates. Números ali não são automaticamente resultados atuais.

## Interpretation rules

- aplicação não implica verificação;
- Evidence ou eval pass não implica autorização externa;
- replay não repete efeitos externos;
- fencing, authorization e idempotency são autoridades/fatos distintos;
- conclusão local não implica Backend READY;
- visualização de Voice/Perception pertence ao frontend, não a um bounded context
  Avatar/Embodiment.

Para detalhes e invariantes exatos, use a especificação ou ADR correspondente; não
expanda este índice com cópias das regras específicas.
