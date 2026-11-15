# Aceite da distribuição Synapse 0.3 no Windows

Data local: 2026-11-15. Revisão de produto: `dbe1901`.

| Artefato verificado | SHA-256 |
| --- | --- |
| `synapse-0.3.0-windows-x64.zip` | `13c90512d7245fe38432bf0bcf7a289a6bcc6d505d95bbc2d1d0cbde3c61d274` |
| `synapse-backend.exe` | `ac20839df748b116a549281b9121517afac74818f227ef6277118ab7f0be4792` |
| `synapse-desktop.exe` | `ffa0a0d48c4c546be03d917c35cd243943ea71f204a8cd568d74c3c6f60ea34e` |

- O instalador verificou o SHA-256 do ZIP e cada entrada do manifesto. O
  launcher da versão instalada iniciou o Core e confirmou a conexão da ponte
  em um diretório descartável. A atualização migrou o esquema 14 para o 15
  e preservou um registro. Um ZIP alterado foi recusado. A reversão trocou a versão ativa e reabriu o banco.
- O ensaio de contexto confirmou que a memória entrou na conversa mediante
  referência explícita. Duas respostas sobreviveram ao reinício. O Core
  identificou a terceira inferência interrompida e preservou o histórico.
- A voz local passou na ativação, resposta comum e tradução PT-BR ↔ EN-US.
  O ensaio injetou áudio sintético na ponte, verificou estado após reconectar
  e exercitou os comandos de parada. Microfone e escuta humana foram
  validados na etapa 13. Este ensaio da distribuição usou áudio descartável.
- A pesquisa sem URL inicial consultou a IANA com o modelo local de 32k.
  O Chromium dedicado passou no redirecionamento com aprovação, download
  em quarentena, login, reabertura de sessão e revogação em duas demonstrações
  HTTPS. O broker recusou um destino que resolveu para loopback.
- O Swarm temporário criou `test_math.py` com uma aprovação. O QA isolado,
  a revisão e o pós-teste passaram. O arquivo foi integrado ao Workspace
  descartável. O ensaio de Skills promoveu uma revisão após avaliação.
  O roteamento MoM escolheu o modelo local dentro do orçamento de memória
  e descartou a opção acima do limite.
- O pacote gravou um arquivo autorizado e recusou uma gravação fora do
  contrato. Um banco descartável com intenção de gravação preparada
  bloqueou a repetição até o abandono seguro. A nova gravação autorizada
  passou após essa recuperação.

As provas de migração, contexto e recuperação podem ser repetidas com os
scripts `verify_windows_install.py`, `verify_windows_context.py` e
`verify_windows_recovery.py` em `tools/release/`. Os dois últimos usam
`SYNAPSE_PACKAGE_ACCEPTANCE` para apontar para os binários instalados. Os
ensaios de voz, navegador e Swarm usam os runtimes locais configurados e
gravam seus relatórios locais em `.superpowers/stage16/`.

[Guia de instalação](../../guides/windows-release.md) · [Notas e matriz de capacidades](../../RELEASE-0.3.md)
