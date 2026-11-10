# Synapse 0.3 — local de trabalho

- A pasta canônica de desenvolvimento é `F:\Projetos\Synapse`.
- Trabalhe diretamente nesta pasta. Não crie uma cópia do projeto ou um
  worktree dentro dela sem um pedido explícito do usuário para nova separação.
- Código do produto: `backend/`. Documentação e decisões: `docs/`.
  Experimentos históricos em `experiments/` são referência, não dependências
  nem implementações para copiar para o produto.
- O produto utiliza Rust nativo e Python. Siga o documento de decisões em
  `docs/specs/2026-11-06-synapse-0.3-decision-charter.md` e suas alterações
  aprovadas antes de implementar cada etapa.
- Preserve evidências, arquivos locais e histórico. Não apague nem altere
  arquivos no disco E como parte do trabalho neste projeto.
- A consolidação de pastas não significa que todas as funcionalidades do backend
  estejam concluídas. Registre testes e limitações do que realmente foi executado.
