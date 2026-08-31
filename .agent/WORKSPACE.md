# Organização permanente do workspace

## Estrutura

- source fica em diretórios de source e testes em `tests/`;
- documentação oficial fica em `docs/`;
- scripts operacionais ficam em `scripts/`;
- caches ficam em `.cache/`;
- outputs gerados ficam em `artifacts/`;
- nenhum cache ou temporário deve ficar solto na raiz.

Não crie nomes baseados em tentativa como `final_final`, `corrective2`, `focus3`,
`new`, `old` ou `final2`.

## Caches

```text
.cache/
├── mypy/
│   ├── global/
│   ├── skills/
│   └── audit/
├── pytest/
├── ruff/
└── coverage/
```

Caches são regeneráveis, locais e nunca versionados. Auditorias usam nomes
semânticos e estáveis, não timestamps ou sequência de tentativas.

## Artifacts

```text
artifacts/
├── reports/
├── diagrams/
├── linkedin/
├── restore-points/
└── temporary/
```

Artifacts públicos são redigidos; temporários não são versionados; restore points
não contêm secrets. Documentação oficial permanece em `docs/`.

## Nomes e responsabilidades

Nomes descrevem responsabilidade, não ordem histórica. Python usa `snake_case`.
Não crie diretório sem ownership claro nem misture cleanup, refactor e feature.
Arquivos legados `phaseN_*` não são renomeados oportunisticamente; essa reorganização
é tarefa própria de Nível B.

## Remoção

Toda remoção exige inventário, prova de regenerabilidade/obsolescência, busca por
referências, dry-run quando aplicável, lista explícita, diff e gate posterior.
Nunca use glob destrutivo amplo.

Arquivo desconhecido não é apagado: investigue origem, tracking e referências,
classifique e registre recomendação.

## Encerramento da tarefa

Não deixe temporários, scripts descartáveis, bancos de teste ou cache fora do
padrão. Não deixe documentação stale, código comentado como backup nem cópias
`.bak`, `.old` ou `.copy`.
