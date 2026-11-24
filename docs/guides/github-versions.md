# Versões e branches no GitHub

Política aprovada em 24/11/2026: manter somente duas branches.

| Branch | Uso |
| --- | --- |
| `0.2` | Implementação anterior preservada como referência, sem importar seu código para a reconstrução. |
| `0.3` | Branch padrão da reconstrução atual em Rust e Python. |

O workflow `platform-package.yml` recebe pushes da `0.3` e gera jobs
independentes para Windows, Linux e macOS. Os artefatos são separados por
sistema, sem branches de plataforma. Aprovação em CI não substitui aceite
em hardware real.

## Histórico anterior à consolidação

As tags abaixo preservam os históricos que não pertencem à reconstrução:

| Tag | Commit preservado |
| --- | --- |
| `archive/pre-cleanroom-0.3-2026-11-24` | `fa3f50f8a30373077bcc5aee56fb5d4d85f2a604` — antiga `0.3`, `develop/0.3` e `archive/0.3-pre-cleanroom`. |
| `archive/main-before-0.3-2026-11-24` | `3e1f000a4a5ea6bf6fa85377b24699613d0c7ae5` — antiga `main`. |

As antigas branches `platform/*` e a consolidação local de novembro já
pertencem ao histórico da reconstrução. `backend-freeze-cleanup` aponta
para o mesmo commit preservado em `0.2`:
`46177e3973ed06a9c71d3bebd3166d587a559d76`.

As tags de releases existentes permanecem. Tags históricas são referências
de recuperação, não branches ativas nem novas releases.

Estado pessoal, credenciais, backups, executáveis locais e logs privados
continuam excluídos do versionamento. Os resultados e limites da validação
estão no [aceite de prontidão operacional](../evidence/backend/2026-11-24-operational-readiness.md).
