# Synapse Backend — operational baseline

Status global: **NOT READY**.

Este documento resume o estado operacional do backend. Ele não substitui
`AGENTS.md`, as políticas em `.agent/`, ADRs, especificações de bounded context
ou audits de freeze. Claims de conclusão abaixo são locais ao respectivo bounded
context; não implicam composição global nem Backend READY.

## Architecture

O Synapse é um ambiente operacional local-first para LLMs, agentes, ferramentas,
memória, execução controlada e workflows. O backend preserva bounded contexts,
contracts/ports, adapters nas bordas, composição explícita, efeitos governados e
replay sem repetição automática de efeitos externos.

Autoridades globais:

- [arquitetura V3](../architecture.md);
- [regras de dependência](../architecture/dependency-rules.md);
- [bootstrap e composition](../architecture/bootstrap.md);
- [governança de projetos](../architecture/project-governance.md);
- [planos de implementação](../architecture/implementation-plans.md).

## Frozen bounded contexts

| Bounded context | Estado local comprovado | Autoridade específica |
| --- | --- | --- |
| Private Evals | `IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN`, Slices 1–18 | [architecture](../architecture/private-evals-runtime.md), [freeze audit](../audits/private-evals-final-freeze-audit.md) |
| Coding Sessions | `IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN`, Slices 1–20 | [architecture](../architecture/coding-sessions.md), [freeze audit](../audits/coding-sessions-final-freeze-audit.md) |
| Skills Runtime Phase 2 | `IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN`, Slices 1–18 | [architecture and freeze record](../architecture/skills-runtime-phase-2.md) |
| Sandbox Execution Boundary | `IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN`, globalmente não ativada | [architecture and freeze record](../architecture/sandbox-execution-boundary.md) |
| Concrete Sandbox Driver Windows V1 | `IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN` | [freeze audit](../audits/concrete-sandbox-driver-final-freeze-audit.md) |
| Repository Runtime | `IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN` | [architecture](../architecture/repository-runtime.md), [freeze audit](../audits/repository-runtime-final-freeze-audit.md) |
| Voice / Audio / Perception | `IMPLEMENTED / ARCHITECTURALLY COMPLETE / FROZEN` | [freeze audit](../audits/voice-audio-perception-final-freeze-audit.md) |
| Search Runtime | `IMPLEMENTED / ARCHITECTURALLY COMPLETE / FROZEN` | [architecture](../architecture/search-runtime.md), [freeze audit](../audits/search-runtime-final-freeze-audit.md) |
| Deployment Runtime | `IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN`, Slices 2–15 | [architecture](../architecture/deployment-runtime.md), [freeze audit](../audits/deployment-runtime-final-freeze-audit.md) |

Limitações configuracionais ou externas permanecem fatos separados da conclusão
arquitetural. Em particular:

- Concrete Sandbox Driver V1 não fornece restricted identity/L2, rede restritiva,
  container/VM nem ativação no bootstrap global;
- Search pode não possuir provider live configurado;
- Voice possui contrato/adapter TTS, mas execução Piper e full-duplex dependem de
  configuração e autoridade externas atualmente indisponíveis;
- visual Perception não verbal permanece intencionalmente indisponível.

## Deployment Runtime

Deployment está **operationally complete e frozen**. A especificação
autoritativa é [Deployment Runtime](../architecture/deployment-runtime.md).

Baseline implementado:

1. discovery;
2. identities, value objects e provider-neutral contracts;
3. Deployment, Rollout, Promotion e Rollback state machines;
4. operational ports;
5. append-only persistence, replay e corruption handling;
6. Governance authorization e Evidence binding;
7. artifact eligibility, custody e provenance;
8. environment, target, slot e revision operational contracts;
9. Deployment-owned generation, fencing e idempotency;
10. local preparation adapter;
11. local apply e factual receipts;
12. independent observation e verification;
13. local rollback preparation, apply, observation e verification;
14. E2E readiness audit;
15. final audit and freeze.

O ciclo local V1 implementado é:

`prepare → apply → observe → verify`

Rollback local também alcança verificação independente. Receipts, observações e
verificações permanecem fatos distintos. Deployment fencing não substitui
authorization, Coding Sessions fencing ou Sandbox fencing. Repository Runtime
continua sendo a autoridade para mutações Repository/Git.

O freeze original não adicionou Global Composition Root. Essa integração foi realizada
posteriormente pelos Slices 2–5 do módulo global, com construção inerte e ativação
exclusiva pelo lifecycle governado.

## Global Composition Root

O módulo está **COMPLETE / FROZEN**. O inventário tipado distingue requirement,
availability, binding mode, activation authority e activation state. Private Evals,
Coding Sessions, Skills Runtime Phase 2, Repository Runtime e Deployment Runtime são
globais e lifecycle-owned, com Health factual. Voice permanece opcional legacy-global;
Search e Concrete Sandbox Driver permanecem opcionais locais. Sandbox Execution Boundary
é requerido, mas continua local/inert por ausência de política operacional canônica e
permanece blocker explícito de Backend Readiness. Evidência:
[Global Composition Root Slice 1 audit](../audits/global-composition-root-slice-1-audit.md)
e [Slice 2 audit](../audits/global-composition-root-slice-2-audit.md),
[Slice 3 audit](../audits/global-composition-root-slice-3-audit.md),
[Slice 4 audit](../audits/global-composition-root-slice-4-audit.md) e
[Slice 5 audit](../audits/global-composition-root-slice-5-audit.md), além do
[final freeze audit](../audits/global-composition-root-final-freeze-audit.md).

## Backend readiness

Bounded contexts frozen individualmente não tornam o backend READY. A decisão
global exige Deployment frozen, composição/bootstrap auditados, journeys E2E,
failure/restart/replay/reconciliation, gates atuais, segurança e uma decisão de
readiness independente. Os critérios completos vivem no
[roadmap operacional](../roadmap/current.md).
