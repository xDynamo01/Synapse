# Consolidação da pasta de trabalho — 10/11/2026

Estado: concluída localmente, antes de qualquer nova etapa de funcionalidade.

## Local oficial

`F:\Projetos\Synapse`, branch `0.3-cleanroom`, contém o código e a documentação
atuais. A antiga área `F:\Projetos\Synapse\.worktrees\gate-00` não existe mais.
`AGENTS.md` registra que novas etapas devem trabalhar diretamente na pasta oficial,
sem criar outra cópia ou worktree sem pedido explícito do usuário.

| Pasta | Uso |
|---|---|
| `backend/` | Código atual em Rust e Python, contratos e testes |
| `docs/` | Decisões, arquitetura, planos e evidências permanentes |
| `tools/` | Ferramentas de engenharia existentes |
| `experiments/` | Fontes históricas de referência, sem uso no produto |
| `.superpowers/` | Relatórios e evidências locais recentes preservados |
| `target/` | Compilação refeita a partir da pasta oficial |

## Histórico preservado

A pasta principal estava em `15d24d0`; o desenvolvimento revisado estava em
`a93b32f`. A integração foi um avanço direto de `0.3-cleanroom` até `a93b32f`,
sem conflitos, reescrita de commits ou mudanças de funcionalidades.
Antes da integração foi criado e verificado um bundle completo do histórico.
A referência local de desenvolvimento foi renomeada para
`archive/gate-00-consolidated-2026-11-10`.

Arquivo histórico local:
`F:\Projetos\Synapse-Arquivo-Local\consolidacao-2026-11-10`.

- `repository-before-consolidation.bundle`: histórico e referências anteriores,
  com `git bundle verify` aprovado.
- `desenvolvimento-anterior-gate-00`: cópia anterior preservada, em HEAD destacado,
  fora do projeto ativo. O Git mantém seu cadastro para recuperação histórica.
- `validacao-antiga-g00-check-6d9aff8`: reprodução antiga, cujo commit está contido
  no histórico consolidado.
- `historico-local/`: reproduções antigas, dependências e ambientes de
  experimentos, cache de testes e resíduos de instalação preservados.
- `compilacao-anterior/`: cache anterior, preservado depois de identificar seus
  caminhos absolutos desatualizados.

Uma tentativa de remover a área antiga foi recusada pela verificação automática
do ambiente. A alternativa adotada foi movê-la para o arquivo histórico sem
exclusão, preservando os arquivos e seu registro Git. A pasta `.worktrees` vazia
também foi preservada fora da raiz, sem uso como área de desenvolvimento.

Não houve publicação no GitHub nem alteração no disco E.

## Conferência da transferência

O inventário anterior à mudança registrou 68.840 entradas, incluindo links,
totalizando 5.071.940.628 bytes de arquivos regulares. Todos os arquivos regulares
receberam assinatura SHA256 no inventário de origem.

A verificação da primeira transferência não encontrou divergências: 29.956
arquivos conferidos por SHA256; 38.847 entradas de caches conferidas pela
identidade das pastas renomeadas no mesmo volume; os demais links conferidos por
seu destino literal. Depois, 27 itens históricos foram arquivados por movimentação
com identidade preservada. O cache de compilação anterior também manteve a mesma
identidade ao ser arquivado.

Inventários e recibos locais no arquivo histórico: `source-manifest.json`,
`move-plan.json`, `verification.json`, `archive-plan.json`,
`archive-verification.json` e `build-cache-relocation.json`.
Recibos antigos continuam descrevendo os caminhos originais de suas execuções;
não foram reescritos. Ambientes de teste antigos não são instalações ativas.

## Testes na localização definitiva

Antes da transferência: 46 testes Rust e 7 testes Python passaram.
O primeiro teste após mover o cache revelou executáveis que ainda continham o
caminho absoluto antigo: a fixture não iniciava, causando uma falha inicial e
falhas derivadas pelo mutex de testes. O cache foi preservado no arquivo
histórico e a compilação foi refeita do zero na raiz.

Depois da recompilação, já sem o caminho antigo dentro do projeto:

- `cargo test --workspace --all-features --locked`: 46 passaram, nenhum falhou
  (20 testes de IA e 26 do Core/ferramentas).
- `py -3.14 -m unittest discover -s backend/python/tests -p test_worker.py -v`:
  7 passaram.
- `cargo build -p synapse-core --bin synapse-backend --locked`: aprovado,
  com recursos padrão, a partir de `F:\Projetos\Synapse`.

O executável reconstruído também foi testado com um modelo local real existente,
Qwen3.5 4B, CPU, contexto1024, uma execução por vez. Não houve download de pesos.
O cliente usou somente o Core: conversa com identificador aleatório, aprendizado
automático de um fato com origem, referência explícita em outro chat, resposta
exata `RIVA-0D557B` e preservação do resultado/contexto após reiniciar. Nenhum
`memory_put`, provedor simulado ou chamada direta ao modelo substituiu esse fluxo.
O modelo de validação foi descarregado ao fim; nenhum modelo permaneceu carregado.

Artefatos locais em `.superpowers/sdd/2026-11-10-explicit-conversation-context/`:

- `live_context_consolidated.py`: instrumento que executou o Core na nova pasta.
- `synapse-backend-consolidated.exe`, SHA256
  `a6abcd314f1c5d69c1a12b1c7743100bf91bf81460a859027293ea12c090c66b`.
- `live-7bf6b0d0d4004c529ef2e2eda75a05cf/receipt.json`, SHA256
  `c9721f8157cb5352fe63057bcc0ba9c72ec20176bddba2cc5a5787b3a3c70b51`.

O código de execução é o integrado em `a93b32f`; o commit de consolidação altera
somente instruções/documentação. Esta é uma verificação de mudança de localização,
não uma declaração de backend completo, compilação portátil ou validação em
Linux/macOS. As funcionalidades ainda pendentes continuam pendentes.
