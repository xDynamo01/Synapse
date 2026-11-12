# Workspaces, edição Git e entregáveis por domínio no Windows x64

O Core schema 14 mantém o cadastro de pastas NTFS e fixa a identidade do
projeto ao criar a missão. A seleção do aplicativo se aplica a novas missões.
Missões anteriores mantêm o destino original e consultas de memória continuam
por escopo explícito. O teste `registered_mission_effects_use_only_the_pinned_project`
exercitou dois destinos com arquivos de mesmo nome, troca de seleção, pasta
substituída, execução de ferramentas e recuperação pelo CLI.

## Missão Git real

O cliente Rust executado com `--bridge` registrou um projeto Git existente em
um diretório temporário, planejou a edição explícita de `calc.py` e aprovou o
contrato. O Qwen local no LM Studio foi carregado com contexto de 32.768 tokens
e uma tarefa paralela. A missão integrou a função `multiply` com teste unitário
após pré-teste, revisão e pós-teste. O recibo mostrou `integrated`, um pré-teste,
um pós-teste, o candidato aprovado e o conteúdo antes e depois.

O arquivo publicado correspondeu ao SHA-256 do recibo
`2c8e5e973a0aeaf8d9f0a68d5641be483aba39d2af5c75002a91663865a582a3`.
A alteração concorrente em `notes.txt` ficou intacta. O commit apontado por
HEAD e os bytes do índice ficaram iguais. A pasta padrão do Core ficou sem
`calc.py`, comprovando o uso do projeto registrado.

O [guia de Workspace](../../guides/windows-project-workspaces.md) registra o
recorte de Git local e os formatos aceitos. O Core aplica o efeito por meio do
broker e mantém o registro do diff. A receita executa em uma área isolada com
os artefatos previstos no contrato. A publicação preserva HEAD e o índice.

## Conflitos, recuperação e receitas isoladas

O teste `git_tracked_edit_detects_changes_and_restores_verified_original`
recusou um alvo já alterado, uma proposta com arquivo fora da lista e uma
mudança concorrente no alvo ou no índice. Em outro ponto do teste, o processo
foi interrompido depois do pós-teste. A recuperação recusou reverter o alvo
quando seus bytes já continham uma nova edição do proprietário. Quando os
bytes publicados foram restabelecidos no cenário de teste, a reversão
restaurou o original e preservou a nota concorrente, o HEAD e o índice.

O teste `domain_skills_bind_verified_native_deliverables` confirmou que as
Skills de versão e digest fixos chegavam ao planejador. Cada proposta
aprovada executou sua receita real no runtime dedicado, com recibo LPAC e
limpeza completa. Os casos foram mapa de jogo JSON, tabela de pesquisa CSV,
documento Markdown, ícone SVG, legenda WebVTT, compilação de módulo Python
e validação de manifesto de dependências Python. As respostas do planejador
nesses casos foram controladas para separar a validação da variabilidade do
modelo. O teste Git acima usou o modelo real.

Passaram 76 testes da suíte Rust, quatro testes explícitos com runtime
dedicado e 11 testes Python. Os logs locais da rodada estão em
`.superpowers/workspace-stage12/`. O commit deste registro contém a atualização
do roteiro e do README.
