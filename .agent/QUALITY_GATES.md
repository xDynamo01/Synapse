# Quality gates proporcionais

Registre cada gate como **executado agora**, **herdado**, **não executado**,
**skipped**, **failed** ou **unavailable**. Resultado herdado nunca substitui
execução atual quando a tarefa o exige.

## Gate mínimo

Para Markdown ou mudança isolada sem código:

- validar conteúdo, links e paths;
- revisar diff;
- executar `git diff --check`.

## Gate local

Para código dentro de um módulo:

- testes específicos e do bounded context;
- Ruff nos arquivos alterados;
- Mypy no escopo;
- boundary tests relevantes;
- diff check.

## Gate estrutural

Para mudanças multiarquivo, imports, módulos ou configuração:

- testes específicos e bounded context completo;
- architecture tests;
- Ruff;
- Mypy local e global;
- grafo de imports/boundaries;
- diff check.

## Gate crítico

Para contrato, schema, migration, persistence, recovery ou security:

- testes específicos, replay/restart e failure paths;
- corrupção/rollback quando aplicável;
- bounded context e architecture suite;
- regressão global;
- Ruff e Mypy local/global com cache limpo;
- diff check e grafo/SCC;
- documentação correspondente.

## Integridade

Não altere teste para confirmar comportamento incorreto, reduza cobertura,
adicione skip sem finding aprovado, ignore type error, silencie linter ou alegue
gate não executado. Não combine resultado histórico com execução atual.

## Eficiência

Durante edição, rode gates locais. Execute gates amplos uma vez ao final. Não crie
cache por tentativa; use os nomes estáveis definidos em
[WORKSPACE.md](WORKSPACE.md).
