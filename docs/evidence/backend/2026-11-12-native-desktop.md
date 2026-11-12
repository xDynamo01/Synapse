# Cliente Rust nativo e ponte local no Windows x64

O executável `synapse-desktop` usa o mesmo controlador de Presence e Workspace
na interface e no modo `--bridge`. A ponte recebe ações por entrada padrão e
retorna as respostas e o estado do cliente por saída padrão. O Core separado
continua sendo o único processo que grava o estado, agenda trabalhos e autoriza
efeitos no Workspace. O canal nomeado do Windows verifica a conta proprietária,
recusa conexões remotas e é liberado ao final de cada solicitação.

## Verificação

- A janela nativa abriu e conectou ao Core. A navegação mudou de Presence para
  Workspace. Ao recolher o Context Rail, o terminal ocupou a largura liberada.
  O processo do Core permaneceu ativo após fechar a janela.
- Pelo modo `--bridge` do mesmo executável, o modelo local no LM Studio com
  contexto de 32.768 tokens respondeu em Presence com o código registrado na
  memória de outro projeto. A pergunta citava o nome do projeto e a conversa
  pertencia a um escopo diferente.
- O teste de reconexão do canal local reabriu o mesmo Core, recuperou o
  histórico e obteve o mesmo recibo ao repetir a solicitação. O histórico
  manteve uma única mensagem. O teste de catálogo cobriu referências ausentes,
  explícitas, ambíguas e versões de memória já resolvidas.

- Uma missão real foi planejada, aprovada e iniciada pelo executável em modo
  ponte. O cliente fechou durante a execução e outro processo abriu a mesma
  missão no Core ainda ativo. A segunda tentativa de execução foi recusada.
  O pré-teste, a revisão, a publicação e o pós-teste terminaram em `integrated`
  em um Workspace temporário sem Git. O registro persistido contém uma única
  execução, e os bytes de `test_desktop_bridge_math.py` correspondem ao
  candidato selado. SHA-256 do arquivo publicado
  `1591e5b51c728a2cc77c301be5a2289f42da9536308e295c0d647c5f21c9528d`.
- Uma tentativa anterior gerou um candidato com import ausente. O pré-teste
  recusou o candidato antes da publicação. O Core também confirmou a recusa
  de publicar em um diretório dentro de um repositório Git.
- A suíte passou com 13 testes unitários do Core, 60 testes de CLI, incluindo
  a reconexão, e um teste do cliente. Testes nativos de execução que exigem
  configuração dedicada ficaram fora da rodada padrão. O fluxo real acima
  executou a receita Python dedicada.

A [configuração e os comandos da ponte](../../guides/windows-native-desktop.md)
permitem repetir a validação sem controlar a tela. O transporte local do
cliente foi implementado e verificado no Windows nesta etapa.
