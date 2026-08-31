---
name: continue-backend
description: Continua exatamente o próximo slice governado do backend Synapse e persiste evidência atual até o próximo ponto de decisão.
---

# Continue Synapse Backend

## Purpose

Use o repositório como memória operacional. Esta skill define o workflow de
continuidade; `AGENTS.md` e `.agent/` continuam sendo as autoridades para escopo,
profiles, risco, segurança, workspace, Git e quality gates.

## Start

1. Leia todos os `AGENTS.md` aplicáveis.
2. Leia `.agent/TASK_PROFILES.md` e somente as policies especializadas relevantes.
3. Leia [o roadmap operacional](../../../docs/roadmap/current.md).
4. Leia a specification, ADR/Plan/Mission, implementação e testes específicos do
   bounded context apontado pelo roadmap.
5. Confirme que existe exatamente um item `NEXT`, que ele não foi iniciado e que
   seus critérios de conclusão são verificáveis.

Se o roadmap estiver stale, contraditório ou não apontar exatamente um próximo
slice, reconcilie documentação sob um profile real apropriado antes de implementar.

## Execute one governed slice

1. Selecione em `.agent/TASK_PROFILES.md` o profile real que corresponde ao
   impacto do slice; não invente nomes de profile.
2. Declare bounded context, slice, arquivos autorizados, exclusões e condição de
   parada.
3. Implemente somente o menor comportamento exigido pelo slice governado.
4. Preserve frozen contracts e authority boundaries; qualquer unfreeze ou mudança
   pública requer governança explícita.
5. Execute os gates proporcionais definidos em `.agent/QUALITY_GATES.md` e os
   freeze/boundary gates específicos do contexto.
6. Registre cada resultado como executado agora, histórico, não executado, failed
   ou unavailable. Métrica histórica nunca substitui gate atual.
7. Atualize specifications, evidence e `docs/roadmap/current.md` com fatos do slice.
8. Se o slice concluir e congelar o bounded context/módulo inteiro, execute o
   checkpoint editorial de publicação definido abaixo e pare. Caso contrário, pare
   na condição de conclusão do slice ou avance somente para o próximo slice
   governado do mesmo módulo.

## Module publication checkpoint

Este checkpoint é obrigatório somente quando o módulo inteiro atingir seu estado
final e todos os gates/freeze correspondentes tiverem passado. Slices internos não
disparam publicação e continuam conforme a governança normal.

1. Confirme que documentação, evidence e roadmap registram o estado factual final.
2. Crie ou atualize `C:\Users\arthu\OneDrive\Imagens\LinkedIn\<Module Name>` sem
   criar subpastas por slice. Prefira `images/`, `linkedin-post.md`,
   `image-prompts.md` e `publication-notes.md`.
3. Organize os visuais do módulo sem apagar originais, sem sobrescrever arquivos salvo
   quando o usuário pedir substituição explícita, e com verificação SHA-256 após qualquer
   cópia.
4. Produza um post técnico em português, legível e factual, em narrativa contínua: abra
   com a conclusão do módulo, explique o problema operacional que motivou o trabalho,
   descreva as responsabilidades e decisões principais, explicite limites de autoridade,
   trate falhas/recovery quando relevante e encerre com o papel do módulo no Synapse.
   Não use o status interno em fórmula, não alegue readiness global ou produção pronta e
   registre limitações arquiteturalmente relevantes. Use hashtags técnicas pertinentes ao
   final, seguindo o modelo editorial vigente.
5. Produza sempre de três a cinco visuais finais por módulo. No máximo um visual pode ser
   uma capa conceitual; os demais devem ter o código real como assunto principal, com
   aparência de captura legível do VS Code, nome do arquivo e linhas relevantes. Não gere
   código fictício dentro de imagens. Prefira renderização determinística dos snippets para
   preservar texto e sintaxe exatos. Se não houver gerador de imagens configurado e
   autorizado, persista prompts finais completos em `image-prompts.md` sem bloquear o
   restante do checkpoint.
6. Registre em `publication-notes.md` capabilities públicas, limitações, invariantes,
   snippets seguros e os visuais ou prompts disponíveis.
7. Termine o workflow com o status exato:

   `MODULE_COMPLETE — HUMAN_CHECKPOINT_FOR_PUBLICATION`

Não inicie outro bounded context/módulo depois deste checkpoint. O próximo módulo
exige uma nova execução humana, mesmo quando já estiver governado pelo roadmap.

A transição entre slices do mesmo módulo não exige checkpoint humano. Após um slice
concluído e validado, avance automaticamente quando o próximo slice estiver governado
e não houver decisão arquitetural, de produto ou segurança realmente pendente.

Frontend não pertence a esta skill. Mudança frontend ou em contrato compartilhado
exige tarefa própria; não existe exceção ampla de compatibilidade.

## HUMAN_DECISION_REQUIRED

Pare no menor ponto seguro quando houver decisão não resolvida de arquitetura,
produto, segurança, contrato público, autoridade, dados ou ação destrutiva. Registre
no roadmap:

- contexto e evidência;
- decisão necessária;
- opções e trade-offs;
- recomendação técnica, quando houver;
- trabalho independente que ainda pode continuar.

Falha local corrigível dentro do slice ou simples ausência de um novo prompt não é,
por si só, `HUMAN_DECISION_REQUIRED`.

## Backend readiness

Um bounded context completo ou frozen não torna o backend READY. A skill nunca
declara `Backend READY` antes da Final Backend Readiness Campaign definida em
`docs/roadmap/current.md` e de uma decisão independente baseada em gates atuais.
