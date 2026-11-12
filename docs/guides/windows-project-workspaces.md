# Workspaces por projeto no Windows

Abra o Core e o cliente como no [guia do aplicativo nativo](windows-native-desktop.md).
No Workspace, digite o escopo `project:<id>` e vincule a pasta pelo campo
**Pasta do projeto**. A lista de projetos cadastrados alterna o escopo para
novas missões. Uma missão já criada conserva seu projeto ao trocar a seleção.

Também é possível cadastrar e selecionar pelo modo `--bridge`.

```jsonl
{"action":"register_project","scope":"project:atlas","root":"F:\\Projetos\\Atlas"}
{"action":"select_project","scope":"project:atlas"}
```

O Core verifica a pasta local NTFS ao reabrir o projeto. Uma pasta substituída
no mesmo caminho deixa o vínculo indisponível. A memória continua vinculada
ao escopo exato e só entra na conversa por referência.

## Editar arquivos rastreados no Git

Cadastre a raiz de um repositório Git local. Em **Edição Git local**, informe
os arquivos rastreados, um por linha. Pelo modo `--bridge`, informe a lista em
`git_edit_paths` na ação `plan`. Revise e aprove o contrato gerado. O contrato
fixa os caminhos e os hashes dos arquivos de origem. A publicação ocorre após
os testes isolados e o parecer de QA. O Context Rail mostra os textos antes e
depois em **Alterações Git revisadas**.

A edição exige arquivos planos UTF-8 no mesmo estado do índice, repositório
com histórico SHA-1 e índice comum v2 ou v3, e HEAD destacado ou com referência
local em arquivo. Mudanças em HEAD, índice ou arquivo-alvo suspendem o efeito.
Mudanças de trabalho em outros arquivos ficam intactas. O Core preserva o
índice e as referências. Operações remotas ficam fora deste fluxo local.

## Entregáveis verificados

Registre uma Skill no escopo do projeto e selecione sua versão ao planejar.
A Skill descreve o formato e o critério do domínio. A receita é escolhida
na proposta, fixada no contrato e executada com o runtime dedicado do Core.

| Entregável | Receita | Verificação |
| --- | --- | --- |
| Mapa de jogo em `level.json` | `game_level_validate` | Dimensões inteiras, grade correspondente e IDs de tiles válidos |
| Dados de pesquisa em `measurements.csv` | `csv_validate` | Cabeçalho único e linhas com a mesma largura |
| Documento em `brief.md` | `markdown_validate` | Um título, corpo e delimitação dos blocos de código |
| Ícone em `icon.svg` | `svg_validate` | Geometria vetorial estática com dimensões e sem referências externas |
| Legendas em `captions.vtt` | `webvtt_validate` | Cabeçalho, texto e intervalos ordenados com início anterior ao fim |

Um projeto Python também pode usar `python_compile` para verificar a
compilação e `python_manifest_validate` para verificar um `pyproject.toml`
com dependências fixadas. A receita de manifesto faz verificação local das
declarações. A instalação de dependências é uma operação própria.

Os recibos do Core identificam a receita, o candidato verificado e a limpeza
da área de execução. Os resultados destas receitas se aplicam aos formatos
da tabela. A validação de um jogo executável ou de uma renderização de mídia
requer a receita específica daquele artefato.
