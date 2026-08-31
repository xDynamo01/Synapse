# Perfis de tarefa

Todos os perfis obedecem [AUTONOMY.md](AUTONOMY.md),
[SECURITY.md](SECURITY.md), [WORKSPACE.md](WORKSPACE.md) e
[QUALITY_GATES.md](QUALITY_GATES.md).

## `analysis-only`

- **Objetivo:** leitura, inventário e recomendação.
- **Permitido:** inspeção e comandos read-only.
- **Autorização:** qualquer edição ou efeito externo.
- **Gates:** evidência das fontes consultadas.
- **Parada:** diagnóstico e recomendações entregues.
- **Relatório:** achados, evidências, riscos e próximos passos.

## `workspace-hygiene`

- **Objetivo:** caches, artifacts, ignore rules, limpeza segura e documentação.
- **Permitido:** limpeza allowlisted e scripts operacionais reversíveis.
- **Autorização:** remoção ampla, source, dados persistentes ou configuração sensível.
- **Gates:** estrutural quando houver config/scripts; mínimo para docs apenas.
- **Parada:** raiz organizada e inventário antes/depois validado.
- **Relatório:** removidos/movidos, espaço, gates e status Git.

## `bounded-context-change`

- **Objetivo:** implementação delimitada dentro de um bounded context.
- **Permitido:** código/testes necessários ao comportamento aprovado.
- **Autorização:** próximo módulo, production wiring, contrato congelado ou refactor
  não relacionado.
- **Gates:** local; estrutural se boundaries/imports mudarem.
- **Parada:** condição local satisfeita. Se o bounded context/módulo ainda não
  estiver frozen, o agente pode avançar automaticamente para o próximo slice
  governado do mesmo bounded context quando não houver decisão pendente.
  Pare somente quando o bounded context/módulo atingir o estado final previsto
  e estiver frozen.
- **Relatório:** arquivos, invariantes e resultados.

## `corrective-audit`

- **Objetivo:** auditar blockers específicos e corrigir findings comprovados.
- **Permitido:** evidência e menor correção suficiente.
- **Autorização:** ampliar o finding ou mudar baseline/contrato.
- **Gates:** proporcionais ao finding.
- **Parada:** decisão **APPROVED** ou **NOT APPROVED**.
- **Relatório:** finding, correção, evidência e decisão.

## `structural-refactor`

- **Objetivo:** rename, move e migração de imports.
- **Permitido:** transformação mecânica prevista no mapa de dependências.
- **Autorização:** ownership/authority, contrato público ou remoção ampla não prevista.
- **Gates:** estrutural; crítico se tocar artifact congelado.
- **Parada:** mapa concluído, compatibilidade e grafo validados.
- **Relatório:** inventário, restore/reversibilidade, movimentos e gates.

## `security-review`

- **Objetivo:** revisar somente o repositório autorizado.
- **Permitido:** análise e testes seguros dentro do escopo.
- **Autorização:** exploração externa, credenciais, exfiltração ou mudança destrutiva.
- **Gates:** crítico para qualquer correção funcional.
- **Parada:** findings classificados e evidências redigidas.
- **Relatório:** severidade, impacto, evidência segura e mitigação.

## `dependency-review`

- **Objetivo:** avaliar package ou repositório externo.
- **Permitido:** análise read-only e recomendação.
- **Autorização:** instalação, cópia ou integração, sempre Nível C.
- **Gates:** proveniência, licença, transitivas, hooks, vulnerabilidades e lockfile.
- **Parada:** aceitar/rejeitar/requerer investigação, sem integrar.
- **Relatório:** necessidade, riscos, alternativas e decisão.

## `documentation-only`

- **Objetivo:** criar ou atualizar Markdown/docs sem alterar comportamento.
- **Permitido:** somente documentação no escopo.
- **Autorização:** código, testes, configuração ou claims sem evidência.
- **Gates:** mínimo.
- **Parada:** links, status e terminologia verificados.
- **Relatório:** arquivos, claims e validação Markdown.
