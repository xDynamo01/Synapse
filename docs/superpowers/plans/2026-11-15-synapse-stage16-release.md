# Synapse 0.3 — Plano de distribuição e aceite

**Objetivo**
Fechar a etapa 16 com um pacote Windows validado e evidências separadas de Linux e macOS.

**Arquitetura**
A revisão de produto permanece na branch 0.3. Cada branch de plataforma fixa a revisão candidata e contém a configuração específica de build e release. O instalador Windows mantém arquivos de programa e estado local em diretórios separados.

**Tecnologia**
Rust 1.96, Python 3.14 e GitHub Actions. O roteiro da etapa 16 e as decisões PL-001 a PL-006 definem os critérios de aceite.

## Execução

- [x] Inventariar processos, dependências, caminhos e requisitos de runtime. Executar a revisão de higiene antes de publicar alterações.
- [x] Empacotar o desktop, o Core, os analisadores e os workers Python. A verificação deve rejeitar alterações no pacote e confirmar os componentes sem acesso à árvore de desenvolvimento.
- [x] Validar instalação limpa, atualização, migração, rollback e recuperação com estado descartável. Registrar o pacote, o SHA-256 e a revisão exatos.
- [x] Executar a jornada final no artefato Windows, com as validações das etapas anteriores por meio do executável entregue.
- [x] Rodar builds e testes nas branches de plataforma e preservar os resultados do GitHub Actions. Registrar separadamente a validação em hardware.
- [x] Publicar notas de release, guia e matriz de capacidades. Conferir as evidências, atualizar o roteiro e o README e registrar a distribuição.
