# Synapse 0.3 — Notas de distribuição

O Synapse 0.3 reúne A.R.T.E.M.I.S. no Presence e no Workspace. O Windows é
a plataforma de aceite inicial. As branches `platform/windows`,
`platform/linux` e `platform/macos` organizam os artefatos e a validação
de cada sistema a partir da lógica compartilhada.

| Capacidade | Windows | Linux e macOS |
| --- | --- | --- |
| Core Rust e protocolo JSON local | Distribuição Windows em validação | Build e testes em execução |
| Desktop e ponte | Canal Windows e executável distribuído | Compilação do desktop prevista. Canal operacional exige validação própria |
| Conversa, voz e tradução | Runtime local e configuração por usuário | Operação em hardware a validar |
| Navegação e sessão | Chromium dedicado, AppContainer e cofre DPAPI | Cofre e isolamento exigem integração da plataforma |
| Missões, QA, Skills, MoM e Swarm | Execução local com ferramentas e modelos configurados | Receitas e operação em hardware a validar |

## Limites do pacote

O navegador usa formulários HTTPS nativos, permissões por missão e
quarentena cifrada para downloads de texto. Logins com JavaScript,
autenticação federada, CAPTCHA ou MFA exigem integração específica.

Cada pacote publica seu SHA-256. O Windows mantém versões lado a lado e
preserva o estado local durante a troca de versão. Consulte o
[guia de instalação, atualização e reversão](guides/windows-release.md).
