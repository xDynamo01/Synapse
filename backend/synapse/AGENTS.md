# Backend Synapse — regras arquiteturais

Este arquivo complementa o [AGENTS.md da raiz](../../AGENTS.md) para todo o
backend Python.

- Preserve bounded contexts e a direção de dependências verificada por
  `tests/architecture`.
- Contracts e ports são fronteiras; adapters concretos entram somente pelo
  Composition Root.
- Domínio não importa persistence, delivery ou composition. Não use service
  locator, singleton global ou importação reversa para facilitar wiring.
- Handlers/adapters não possuem regra de domínio.
- Identities e artifacts governados são imutáveis. Replay, completeness e
  authority permanecem explícitos.
- Mensagens e erros são tipados, seguros e redigidos.
- Nenhuma integração de produção é ativada implicitamente.
- Mudança transversal requer teste arquitetural.
- Não introduza ciclos nem aumente SCC sem finding e autorização.
- Não use `Any`, suppress ou mudança de configuração para contornar contrato/Mypy.
- Policy possui um único owner; não a replique em múltiplos contexts.

Alteração em bounded context congelado é no mínimo Nível B de
[AUTONOMY.md](../../.agent/AUTONOMY.md). Contrato congelado é Nível C. Todo novo
governed edge deve ser declarado e testado. Mudança de ownership ou authority
exige decisão arquitetural explícita.
