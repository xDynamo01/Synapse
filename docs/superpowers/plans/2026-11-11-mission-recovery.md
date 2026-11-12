# Etapa 10 — Recuperação de missões interrompidas

O Core mantém efeitos ambíguos em `recovery_required`. O CLI deve ajudar o
proprietário a identificar o que ocorreu, resolver apenas o que tem evidência
suficiente e preservar os demais alvos.

1. Adicionar inspeção por missão e arquivo no CLI. Comparar as intenções e
   recibos duráveis com o Workspace fixado, usando o broker para leitura
   verificada. Distinguir ausência, identidade comprovada, alteração e bytes
   iguais sem prova de autoria. Testar interrupção antes e depois da escrita.
2. Implementar decisão explícita do proprietário. Confirmar só quando os
   recibos e pós-testes satisfizerem o contrato. Reverter apenas arquivos de
   identidade e bytes comprovados, sob aprovação vigente. Registrar o
   comando de recuperação antes de qualquer efeito e verificar a remoção.
   Preservar reservas quando a evidência permanecer insuficiente.
3. Exercitar repetição, reinício durante a recuperação, revogação e arquivos
   alterados. Registrar testes e configuração de instalação limpa. Atualizar
   roteiro e README conforme os itens atingirem seus critérios de aceite.

## Conformidade com o Documento de Decisões

**Documento:** [Decision Charter](../../specs/2026-11-06-synapse-0.3-decision-charter.md).

| IDs vinculantes | Obrigação | Evidência |
|---|---|---|
| MI-002, MI-003, MI-006 | Escopo fixado, autorização vigente, identidade e reversão verificadas | Testes de recuperação pelo CLI |
| SE-005, SE-006 | Broker mantém o limite de caminhos e autoridade | Testes negativos de substituição e leitura |
| PL-001, PL-006 | Core Rust único e contratos versionados | CLI e armazenamento real |
| QA-001, QA-002, QA-003 | Evidência do artefato executado e regressões | Relatório do marco |

Voz, navegador, Swarm e empacotamento multiplataforma ficam fora desta etapa.
Nenhum desvio do Documento de Decisões é proposto.
