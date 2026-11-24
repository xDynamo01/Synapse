# Ledger operacional e compatibilidade do worker

Escopo: validação em Windows em 2026-11-23, com fixtures sintéticas e inferência HTTP somente em loopback. Este recibo não substitui o aceite do pacote final nem avals de qualidade de um modelo real.

## Resultados

| Verificação | Resultado |
| --- | --- |
| Unidades `operational` e `operational_store` | 8 passaram |
| Unidades `worker::compatibility_tests` | 3 passaram |
| CLI operacional, executável atual | 3 passaram |
| Suite Python completa | 46 testes executados, 2 skips preexistentes, nenhuma falha |
| Matriz de compatibilidade executada com inferência sintética | 3 combinações passaram |

A matriz executou Core schema15 com worker atual, Core atual com worker antigo e ambos atuais. Cada combinação concluiu uma inferência e conferiu o resultado exato. O Core antigo veio do fixture de distribuição schema15 preservado, não de uma alegação de release publicada. O relatório privado `.superpowers/readiness-20261122/worker-cross-version.json` vincula o hash de cada executável e worker à combinação testada.

O worker Python inicia com o greeting v4 exato quando lançado sem opção; o Core atual solicita explicitamente `--protocol-version=5`. Um worker antigo continua respondendo v4 e o Core atual aceita essa negociação. Os corpos v4 não recebem campos novos. V5 declara `operational_metrics_v1` e tem validação própria.

## Correções verificadas

- Falha anterior à inicialização do worker agora conserva um envelope de métricas v1 com contadores desconhecidos. Não produz `version: 0` nem inventa uma medição zero.
- Grafos criados diretamente por RFC compartilham orçamento no namespace `graph:<id>`, inclusive quando não possuem missão de Planner como raiz. Grafos de Planner continuam usando `mission:<raiz>`.
- Planos de filhos executados antes de vincular o grafo têm seus recibos adotados pelo ledger compartilhado. A adoção mantém o início mais antigo, os limites mais restritivos, os IDs e os contadores; consultas repetidas não reaplicam o consumo. Uma missão com o mesmo nome de um grafo permanece em namespace separado.
- Retries do mesmo job e tentativas dos filhos compartilham limites; conclusão repetida não duplica consumo. Recuperação marca tentativas interrompidas uma vez. Orçamento de missão iniciada só pode ser reduzido.
- O teste CLI concluiu planejamento real contra fixture e comprovou que o limite agregado de uma chamada impede iniciar geração e reservar outro modelo.
- Canários de prompt e erro não aparecem nos recibos nem nos eventos operacionais. Durações da tentativa são medidas ao finalizar o worker, separadas do tempo total da missão.

## Limites explícitos

Tokens de entrada/saída são contadores reportados pelo provedor quando disponíveis. Um limite estrito total de tokens recusa admissão enquanto não houver limite superior confiável da tokenização de entrada. RAM e VRAM por provedor permanecem desconhecidas quando não há medição atribuível; limites finitos dessas métricas recusam admissão nesse caso. A leitura global de GPU não é apresentada como VRAM de uma missão. Reutilização de instância não é cache de respostas. Inferência remota continua proibida.

## Reprodução

```powershell
cargo test --locked -p synapse-core --lib operational -- --test-threads=1
cargo test --locked -p synapse-core --lib worker::compatibility_tests -- --test-threads=1
cargo test --locked -p synapse-core --test operational_cli -- --test-threads=1
py -3.14 -B -m unittest discover -s backend/python/tests
```

Logs desta execução: `.superpowers/readiness-20261122/metrics-units-final.log`, `worker-units-final.log`, `metrics-cli-final.log`, `python-current.log` e `worker-cross-version.log`. O coordenador ainda deve vincular o gate completo e o pacote final às fontes estabilizadas.
