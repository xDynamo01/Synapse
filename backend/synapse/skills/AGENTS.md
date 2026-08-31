# Skills Runtime Phase 2 — safeguards

Status: **IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN**.

Este arquivo complementa as regras do [backend](../AGENTS.md). Qualquer mudança
funcional usa o gate crítico de
[QUALITY_GATES.md](../../../.agent/QUALITY_GATES.md).

## Baselines congelados

- SQLite schema V1 e restore-point format V1;
- contratos públicos atuais;
- manifests, snapshots e identities imutáveis;
- publication e lifecycle append-only;
- recovery verificável;
- Phase 1 coexistente e não substituída.

## Invariantes

- Sem automodificação in-place: evolução cria nova candidata.
- Sem autopromotion e sem escolha implícita de latest/current/first/best.
- Installation não prova custody; activation não prova authorization.
- Resolution não prova availability.
- Binding não interpreta Governance, Intelligence ou Private Evals.
- Handoff não prova executability; execução pertence a boundary externa.
- Sandbox não pertence a Skills.
- Rollback ocorre antes de repair.
- Records persistidos não são editados individualmente.
- Migration congelada não é editada.

## Permitido sem nova autorização

- documentação e testes adicionais;
- correção interna que preserve contratos e baselines;
- hardening que não altere semântica pública.

Essas alterações continuam sendo no mínimo Nível B quando funcionais e devem
produzir evidência proporcional.

## Autorização explícita

Exigem Nível C: mudança de façade, identity, schema, migration, restore format,
lifecycle, replay/completeness, production activation, migração/substituição da
Phase 1, integração com Sandbox/executor e geração/evolução autônoma.

Não replique aqui o histórico dos slices; a autoridade detalhada permanece na
documentação arquitetural e nos contratos congelados.
