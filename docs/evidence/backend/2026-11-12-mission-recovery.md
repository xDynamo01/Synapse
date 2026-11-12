# Recuperação de missões pelo CLI no Windows

A etapa 10 cobre publicação de arquivos novos na raiz de um Workspace Windows
sem Git. A inspeção mostra a intenção de cada arquivo, o estado do diário e a
observação atual, incluindo identidade e SHA-256 quando disponíveis. O Core
compara o diário com o contrato selado, o candidato e o destino do broker.

- `finalize` exige a aprovação vigente, arquivos com identidade registrada e
  conteúdo intacto, e recibos válidos de pré e pós-testes. A leitura final
  mantém os arquivos e a raiz protegidos até registrar a integração.
- `rollback` remove apenas efeitos comprovados e intactos. O Core reconcilia
  a ausência de um destino registrado, preserva arquivos alterados ou de
  autoria inconclusiva e mantém a reserva enquanto houver ambiguidade.
- O Core grava o recibo da solicitação antes de tocar no Workspace. Após uma
  nova interrupção, repetir o identificador retorna o recibo original. Uma
  nova decisão do proprietário requer uma nova solicitação.

## Validação

Windows x64, CLI Rust real, SQLite local e runtime CPython dedicado sob LPAC.
Cada cenário começa com diretórios novos de estado e Workspace. O provedor
controlado prepara o candidato. A resolução usa o diário local.

| Interrupção ou condição | Verificação pelo CLI |
|---|---|
| Após registrar a intenção de publicação, antes da escrita (87) | Inspeção informa ausência. Reversão encerra a missão sem criar arquivos. |
| Após a escrita, antes de confirmar a identidade (88) | Inspeção distingue bytes iguais de identidade comprovada. Confirmação e reversão são recusadas. |
| Após os pós-testes, antes de confirmar a integração (89) | O proprietário confirma a publicação após nova leitura e verificação de recibos. |
| Antes da exclusão na reversão (91) | O arquivo sobrevive ao reinício. Repetir o comando retorna o recibo. Uma nova solicitação verifica e remove o arquivo. |
| Após a exclusão, antes de registrá-la (90) | A repetição retorna o recibo anterior. Uma nova solicitação verifica a ausência e encerra a reversão. |
| Arquivo alterado, aprovação revogada ou operação ausente no diário | O Core recusa a ação correspondente e preserva os arquivos. |

O teste de publicação verifica também o diagnóstico de leitura bloqueada.
O comando `health` do guia foi executado com diretórios novos de estado e
Workspace e retornou sucesso.
A suíte do Core verifica que somente uma instância ativa possui cada diretório
de estado. O [guia do Windows](../../guides/windows-mission-recovery.md) descreve
como preparar uma instalação de desenvolvimento, diagnosticar e recuperar uma
missão. O [contrato v1](../../../backend/contracts/v1/README.md) documenta os
comandos e recibos. A validação do instalador de distribuição pertence à
etapa de release.

A suíte do Core passou com 13 testes unitários e 59 regressões pelo CLI.
Os dois testes de missão que exigem o runtime dedicado passaram em uma
execução explícita. Logs locais em `.superpowers/mission-recovery/`.
O commit que registra este marco inclui o código, os testes e a atualização
do roteiro.

```powershell
cargo test -p synapse-core --all-features -- --test-threads=1
cargo test -p synapse-core --all-features --test project_check_cli mission_ -- --ignored --test-threads=1
```
