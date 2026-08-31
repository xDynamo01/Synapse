# Skills Runtime Phase 2 — reconhecimento, authority map e baseline

Data da auditoria: **2026-07-26**

Status: **IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN**

Decisão atual: **Skills Runtime Phase 2 — IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN**

Este documento preserva o reconhecimento arquitetural do Slice 1, a auditoria
corretiva do Slice 2 e os typed store contracts do Slice 3. O módulo completo
permanece não implementado; concrete stores, runtime Phase 2, adapters, bootstrap,
execution, Sandbox, Private Evals e o Slice 4 continuam fora do escopo.

## 1. Resumo executivo

O nome oficial atual é **Skills Runtime**, implementado pelo bounded context Python
`synapse.skills`. Phase 1 define Skill como um **workflow reutilizável, versionado e
empacotado**, distinto de SOUL, ROLE, Capability, Permission e Tool. A unidade
instalável atual é um diretório com `manifest.yaml` e `SKILL.md`; uma
`SkillPackage` referencia esse conteúdo e leva um checksum do diretório inteiro.

Phase 1 tem uma base útil: IDs sintáticos, SemVer explícita, dataclasses congeladas,
manifest validation, checksum, paths confinados, instalação local, catálogo em
memória, resolução de dependências, carregamento progressivo, assignments, leases,
stores locais e ports para consumidores.

Ela não satisfaz ainda a arquitetura requerida para Phase 2:

- não existe `SkillId` nem `SkillVersion` como value objects semânticos;
- status é gravado dentro do manifest publicado, mudando bytes e checksum in-place;
- `resolve_version("*")` escolhe silenciosamente a maior versão elegível;
- ativar uma versão desabilita e regrava outras versões;
- uninstall apaga pacote e installation record, sem tombstone ou histórico;
- não há revocation, provenance forte, signature, lineage ou publication record;
- installation, package presence, lifecycle e discovery competem por autoridade;
- `SkillsRuntime.execute_script()` ainda oferece uma operação de execução, embora o
  adapter delegue ao Tool boundary;
- nenhum binding concreto com Private Evals existe;
- o port de Project Governance é importado diretamente pelo runtime concreto, mas não
  é ligado no builder atual;
- cinco documentos antigos de Skills contêm apenas bytes NUL e não são autoridade.

Phase 2 deve consolidar lifecycle e catálogo de artefatos imutáveis, preservar
histórico e produzir apenas referências verificáveis para Governance, Intelligence,
Private Evals e o futuro Sandbox Execution Boundary. Ela não deve executar código.

## 2. Método e limites

Foram inspecionados `backend/synapse`, `tests`, `docs`, `data`, migrations,
`pyproject.toml`, bootstrap, architecture tests e o histórico Git disponível. A busca
incluiu skill, skills, capability, plugin, extension, registry, manifest, package,
loader, executor, installer, lifecycle, version, policy, permission, evaluation,
promotion e revocation, além dos termos de segurança pedidos.

O repositório não possui diretório `scripts/`. Não foram encontradas migrations
específicas de Skills. Os arquivos de Phase 1 e a maioria dos seus testes/docs estão
**untracked** no worktree; por isso `git log -- backend/synapse/skills` não contém
histórico. O histórico rastreado anterior mostra apenas a origem do modelo legado de
agente (`f0afe19`, `45f06d9`, `0dc6b23`, `5d49851`). Esta limitação impede usar Git
como prova de evolução interna da Phase 1.

## 3. Inventário

### 3.1 Autoridade e suporte direto

| File | Context | Responsibility | Git state | Consumers | Current relevance | Classification |
| --- | --- | --- | --- | --- | ---: | --- |
| `backend/synapse/skills/__init__.py` | skills | facade/export parcial | untracked | importadores públicos | alta | CONTRACT |
| `backend/synapse/skills/models.py` | skills | manifest, package, requests, results, assignment e lease | untracked | runtime, API, Commands, bootstrap, testes | alta | CURRENT AUTHORITY |
| `backend/synapse/skills/contracts.py` | skills | resolution, script execution, policy, record store e lease ports | untracked | context, ephemeral agents, runtime, bootstrap adapters | alta | CONTRACT |
| `backend/synapse/skills/package.py` | skills | parse/validate manifest, package checksum, paths e constraints | untracked | SkillsRuntime | alta | CURRENT AUTHORITY |
| `backend/synapse/skills/runtime.py` | skills | registry, discovery, loader, resolver, lifecycle e facade | untracked | bootstrap, API, Commands, testes | alta | CURRENT AUTHORITY |
| `backend/synapse/skills/errors.py` | skills | erros estruturados | untracked | package, runtime, API | alta | CURRENT SUPPORT |
| `backend/synapse/bootstrap/features/skills.py` | bootstrap | stores, runtime, seed assignments, health e port publication | untracked | application composition | alta | CURRENT SUPPORT |
| `backend/synapse/bootstrap/adapters/skills.py` | bootstrap | FileCollection e ToolExecution adapters | untracked | Skills feature | alta | CURRENT SUPPORT |
| `backend/synapse/bootstrap/application.py` | bootstrap | bindings para primary, missions e ephemeral agents | untracked | production composition | alta | CURRENT SUPPORT |
| `backend/synapse/api/routers/skills.py` | api | 17 paths HTTP de consulta/mutação | untracked | API clients | média | CURRENT SUPPORT |
| `backend/synapse/commands/handlers/skills.py` | commands | 16 comandos de Skills | untracked | command runtime | média | CURRENT SUPPORT |
| `backend/synapse/health/contributors/skills.py` | health | health/metrics | untracked | health runtime | baixa | CURRENT SUPPORT |
| `backend/synapse/context/loader.py` | context | consome `SkillResolutionPort`; ainda lê `SKILLS.md` | modified | prompts/context | alta | COMPATIBILITY |
| `backend/synapse/ephemeral_agents/runtime.py` | ephemeral_agents | consome `SkillLeasePort` | untracked | missions | alta | CURRENT SUPPORT |
| `backend/synapse/primary_agent/runtime.py` | primary_agent | consome assignment summaries via port estrutural | untracked | primary bootstrap | média | CURRENT SUPPORT |
| `backend/synapse/project_governance/contracts.py` | project_governance | `ProjectContextReadPort` | untracked | SkillsRuntime | média | CONTRACT |
| `backend/synapse/storage/collection.py` | storage | persistence filesystem genérica | untracked | SkillRecordStoreAdapter | alta | CURRENT SUPPORT |
| `backend/synapse/tools/contracts.py`, `models.py`, `runtime.py` | tools | execução governada de Tool | untracked | script adapter | alta | CURRENT AUTHORITY |
| `data/skills/packages/research-synthesis/1.0.0/*` | skills data | pacote piloto | ignored/generated runtime data | runtime/teste manual | baixa | GENERATED |
| `data/agents/researcher/CONFIG.yaml` | agents data | assignment piloto + labels legados | modified | bootstrap/agents | média | COMPATIBILITY |
| `data/agents/*/SKILLS.md` | agents data | instrução descritiva por agente | modified | identity/context | média | LEGACY |
| `data/agents/*/CONFIG.yaml` | agents data | labels/capabilities/permissions legados | modified | agents/policies | média | COMPATIBILITY |

`data/skills/**` é ignorado por `.gitignore`; o seed observado não é um artefato
versionado confiável e não deve ser tratado como catálogo de distribuição.

### 3.2 Testes

| File | Responsibility | Git state | Classification |
| --- | --- | --- | --- |
| `tests/test_skills_runtime.py` | package, install, restart, resolution, assignment, lease, redaction, governance context | untracked | TEST |
| `tests/architecture/test_skills_boundaries.py` | imports, ports, ausência de shell/autoevolution e SCC | untracked | TEST |
| `tests/acceptance/skills_support.py` | factory de runtime/package | untracked | TEST |
| `tests/acceptance/test_skill_package_installation_e2e.py` | instalação | untracked | TEST |
| `tests/acceptance/test_skill_restart_e2e.py` | restart | untracked | TEST |
| `tests/acceptance/test_skill_dependency_conflict_e2e.py` | conflitos | untracked | TEST |
| `tests/acceptance/test_skill_tool_boundary_e2e.py` | Tool boundary | untracked | TEST |
| `tests/acceptance/test_primary_agent_skill_resolution_e2e.py` | primary | untracked | TEST |
| `tests/acceptance/test_persistent_agent_project_skills_e2e.py` | assignment/project | untracked | TEST |
| `tests/acceptance/test_ephemeral_agent_skill_lease_e2e.py` | lease | untracked | TEST |

### 3.3 Documentação, ADRs e planos

| File/group | Responsibility | Git state | Classification |
| --- | --- | --- | --- |
| `docs/validation/skills-runtime-phase-1-inventory.md` | inventário anterior | untracked | DOCUMENTATION |
| `docs/validation/skills-runtime-phase-1-finalization.md` | claim de freeze Phase 1 | untracked | DOCUMENTATION |
| `docs/architecture/skills-runtime.md` | resumo da autoridade Phase 1 | untracked | DOCUMENTATION |
| `docs/architecture/skill-resolution.md` | resolução/load progressivo | untracked | DOCUMENTATION |
| `docs/architecture/rfc-skill-integration.md` | integração Governance | untracked | DOCUMENTATION |
| `docs/architecture/skill-packages.md` | arquivo composto só por NUL | untracked | UNKNOWN |
| `docs/architecture/skill-scopes.md` | arquivo composto só por NUL | untracked | UNKNOWN |
| `docs/architecture/skill-assignments-leases.md` | arquivo composto só por NUL | untracked | UNKNOWN |
| `docs/architecture/skill-script-boundary.md` | arquivo composto só por NUL | untracked | UNKNOWN |
| `docs/architecture/skill-interoperability.md` | arquivo composto só por NUL | untracked | UNKNOWN |
| `docs/architecture/private-evals-runtime.md` | referências versionadas/fingerprints; Phase 2 futura | untracked | FUTURE RESERVED |
| `docs/architecture/project-governance.md` | projetos/RFC/evidence/skills permitidas | untracked | CURRENT SUPPORT |
| `docs/architecture/intelligence-trust-boundary.md` | trust/classification | untracked | CURRENT SUPPORT |
| `docs/architecture/tool-execution-boundary.md` | execução atual por Tool | untracked | CURRENT AUTHORITY |
| `docs/adr/0006-autonomy-skill-permission-separation.md` | separa skill, permission e autonomy | tracked | CONTRACT |
| `docs/adr/0028-capability-runtime.md` | capability independente | untracked | CONTRACT |
| `docs/adr/0066-external-capability-strategy.md` | capability externa | untracked | DOCUMENTATION |
| `docs/adr/0078-provider-plugin-runtime.md` | plugin de provider, não Skill | untracked | DOCUMENTATION |
| `docs/agents.md` | SKILLS.md legado e assignments | untracked | COMPATIBILITY |
| `docs/templates/RFC-template.md`, `docs/architecture/implementation-plans.md` | processo futuro | untracked | FUTURE RESERVED |

Referências incidentais a “skill”, “capability” ou “plugin” em modelos, providers,
audio/vision, maintenance, system insight e documentação geral não implementam o
bounded context Skills. `capabilities/` e `provider_plugins/` são autoridades
independentes, não implementações concorrentes de Skill.

## 4. Estado atual do bounded context

| Concern | Current implementation | Authority clear? | Production use? | Phase 2 disposition |
| --- | --- | ---: | ---: | --- |
| identity | `manifest.skill_id`, regex | parcial | sim | criar value object semântico |
| version | string SemVer + `version_matches` | parcial | sim | `SkillVersionId` imutável |
| manifest | frozen dataclass + YAML | sim | sim | separar declaração publicada de estado |
| metadata | dict redigido por chaves | parcial | sim | schema explícito/provenance |
| dependencies | SkillDependency | sim | sim | declarar; resolver sem silêncio |
| permissions | strings declarativas | não | só metadata | referência; Intelligence/Policy decide |
| installation | copytree + installation record | parcial | sim | record imutável e verificável |
| activation | `set_status("active")` | não | sim | record separado, nunca editar manifest |
| deactivation | `set_status("disabled")` | não | sim | record separado |
| revocation | ausente | não | não | implementar preservando histórico |
| compatibility | dict livre | não | parcial | facts tipados, decisão externa |
| execution | `preview_script`/`execute_script` → Tool | conflita | sim | remover da autoridade; handoff apenas |
| evaluation | ausente | sim | não | binding referencial a Private Evals |
| promotion | ausente | sim | não | Governance é autoridade |
| storage | package filesystem + 3 FileCollections | parcial | sim | stores explícitos, restart/recovery |
| discovery | registry em memória + texto | parcial | sim | query determinística sobre catálogo |
| configuration | manifest + agent CONFIG | não | sim | separar assignment de config legado |
| Composition Root | SkillsFeatureBuilder + application bindings | sim | sim | último slice, após ports/adapters |

Exports públicos atuais: `SkillAssignment`, `SkillLease`, `SkillLoadRequest`,
`SkillManifest`, `SkillPackage`, `SkillResolutionPort`, `SkillResolutionRequest`,
`SkillScope`, `SkillResourceRuntime`, `SkillValidationRuntime`,
`SkillVersionStore`, `SkillScriptExecutionPort` e `SkillsRuntime`. O facade não exporta
vários modelos/results/contracts, portanto a superfície pública não é totalmente
coerente.

## 5. Definição atual de Skill

| Symbol | File | Meaning | Immutable? | Authority | Phase 2 decision |
| --- | --- | --- | ---: | --- | --- |
| `SkillScope` | models.py | system→task scope | enum | skills | manter/revalidar |
| `SKILL_STATUSES` | models.py | draft/active/deprecated/disabled | set mutável | skills | substituir por lifecycle tipado |
| `SkillDependency` | models.py | dependência de outra Skill | sim, superficial | skills | manter como declaração |
| `SkillConflict` | models.py | conflito declarado | sim, superficial | skills | tipar severidade |
| `SkillScriptDescriptor` | models.py | referência a script/tool | sim, superficial | skills | virar execution handoff descriptor |
| `SkillManifest` | models.py | identidade+conteúdo+policy+lifecycle | sim, superficial | skills | decompor authorities |
| `SkillPackage` | models.py | manifest+root+checksum+installed | sim | skills | separar content reference/install state |
| `SkillDescriptor` | models.py | projeção de discovery | sim | skills | query DTO |
| `SkillResolutionRequest/Result` | models.py | seleção e explicação | sim, superficial | skills | manter, proibir implicit latest |
| `SkillLoadRequest/Result` | models.py | load progressivo | sim, superficial | skills | retornar refs/snapshots |
| `SkillAssignment` | models.py | vínculo persistente a agente/scope | sim, superficial | skills | record lifecycle versionado |
| `SkillLease` | models.py | vínculo efêmero | sim, superficial | skills | preservar, auditável |
| `VersionedComponentRef` | private_evals/runs.py | kind/id/version/fingerprint | sim | Private Evals | consumir via adapter, não duplicar |

“Frozen” é superficial onde os campos são `dict` ou onde o arquivo YAML é regravado.
Não há `SkillId`, `SkillVersion`, `SkillManifestFingerprint`, publication ID,
installation ID tipado, revocation record ou execution request de Sandbox.

Respostas factuais:

1. Skill é hoje um workflow empacotado; não é apenas código, manifest ou capability.
2. Uma Skill declara várias capabilities requeridas, mas não as contém nem concede.
3. Capability e Skill são conceitos diferentes e têm bounded contexts distintos.
4. Skills se associam a agentes por `SkillAssignment`.
5. Skills se associam a projetos por scope/metadata e request/context de resolução.
6. Versões são strings SemVer explícitas.
7. O ID é sintaticamente determinístico, mas não há identidade semântica canônica.
8. Há SHA-256 do package e checksum por script; não há fingerprint tipado/assinado.
9. Não há lineage.
10. Há status simples no manifest, sem máquina de lifecycle.
11. Há instalação local.
12. Há ativação/desativação por mutação do manifest.
13. Não há revogação.
14. Não há trust de Skill; há apenas requisitos declarativos.
15. Há `compatibility: dict` e checagens parciais de agent/tools/capabilities/providers.

## 6. Authority map atual

| Concern | Current authority | Competing implementations | Consumers | Risk |
| --- | --- | --- | --- | --- |
| Skill identity | manifest + registry key | agent labels/SKILLS.md | runtime/API | alto |
| Skill version | manifest string | assignment constraint, folder name | resolver/store | médio |
| manifest | YAML/package.py | dataclass projection | todos | médio |
| package contents | filesystem directory | manifest file lists | loader | médio |
| installation | package presence + installation record | registry `installed` bool | runtime/health | alto |
| lifecycle | mutable manifest status | API enable/disable | resolver/API | crítico |
| activation | exactly one active fallback | set_status side effects | get/resolve | crítico |
| permissions | Policy/Tools/Intelligence | manifest.permission strings | resolver/execution | alto |
| execution | Tools runtime | Skills facade methods | API interna/tests | crítico |
| trust | Intelligence Boundary | manifest trust fields | futuro | médio |
| evaluation | Private Evals | nenhum adapter | futuro | médio |
| promotion | Project Governance | `set_status(active)` parece promoção | API/admin | crítico |
| revocation | inexistente | disable/uninstall | runtime | crítico |
| discovery | mutable in-memory registry | filesystem restart scan | resolver | alto |
| dependency resolution | SkillResolver | version store | resolver | médio |
| persistence | filesystem + FileCollection | agent CONFIG seed | bootstrap/runtime | alto |

Autoridades duplicadas principais: lifecycle no manifest e no operation surface;
installation no filesystem, record e registry; assignments no store e no
`CONFIG.yaml`; Skill description em package `SKILL.md`, agent `SKILLS.md` e labels;
execution em Skills e Tools; promoção confundível com `active`.

## 7. Dependências entre contexts

| Source context | Target context | Imported symbol | Direction justified? | Phase 2 status |
| --- | --- | --- | ---: | --- |
| skills | core | serialization, SynapseError | sim, neutral support | manter mínimo |
| skills | project_governance | ProjectContextReadPort | parcial | trocar por port owned by Skills/adaptado |
| context | skills | SkillResolutionPort | sim | manter port |
| ephemeral_agents | skills | SkillLeasePort | sim | manter port |
| api | skills | model DTOs | delivery aceitável | manter fino |
| commands | skills | model DTOs | application aceitável | separar commands/queries |
| bootstrap | skills | concrete runtime/models | sim | Composition Root |
| bootstrap | storage/tools | FileCollection/ToolExecutionPort | sim | adapters estreitos |
| primary_agent | skills | nenhum import direto; objeto injetado | sim | formalizar port |
| missions/swarm | skills | nenhum import direto; bootstrap binding | sim | manter |
| private_evals | skills | nenhum | sim | futuro adapter de snapshot |
| intelligence_boundary | skills | nenhum; enum `skill_execution` | sim | futuro decision reference |
| tools | skills | nenhum | sim | execução não retorna |
| models/providers/repository/deployment/sandbox | skills | nenhum | sim | continuar sem edge |

Inbound oficial de Skills: `api`, `commands`, `context`, `ephemeral_agents`.
Outbound oficial: `core`, `project_governance`. Não há edges diretas de Agents,
Missions, Workers, Swarm, Models, Policies, Private Evals ou Intelligence para o
runtime concreto.

## 8. Grafo arquitetural

Método oficial: `_runtime_context_graph()` exclui `TYPE_CHECKING`, bootstrap e os
três adapters de compatibilidade em core. O grafo exato usa imports runtime absolutos
sem colapsar módulos.

| Measure | Expected | Observed | Result |
| --- | ---: | ---: | --- |
| official contexts (nodes governed) | 70 | 70 | match |
| directories contendo Python | não é baseline | 73 | três não participam do grafo |
| governed edges | 263 | 263 | match |
| official SCC | 13 contexts/35 edges | 13/35 | match |
| Skills in SCC | no | no | match |
| exact modules | 518 | 518 | match |
| exact edges | 1,584 | 1,584 | match |
| exact parse errors | 0 | 0 | match |
| exact non-trivial SCC | 0 | 0 | match |

SCC oficial: `agents`, `approvals`, `avatar`, `context`, `conversations`,
`decisions`, `delegation`, `embodiment`, `missions`, `models`, `policies`, `tools`,
`voice`. Private Evals e Skills permanecem fora.

## 9. Contracts existentes

| Contract | Owner | Methods | Consumers | Implementations | Phase 2 relevance |
| --- | --- | ---: | --- | --- | --- |
| `SkillResolutionPort` | skills | 4 | context, primary | SkillsRuntime | alta; hoje mistura query/load/assignment |
| `SkillScriptExecutionPort` | skills | 2 | SkillsRuntime | bootstrap Tool adapter | substituir por handoff; execução futura |
| `SkillPolicyPort` | skills | 1 | nenhum | nenhuma | conceito válido, abstrato/órfão |
| `SkillRecordStore` | skills | 3 | SkillsRuntime | FileCollection adapter | alta; genérico demais e permite delete |
| `SkillLeasePort` | skills | 2 | ephemeral_agents | SkillsRuntime | alta; cleanup destrói histórico |
| `ProjectContextReadPort` | governance | 1 | SkillsRuntime | governance runtime/adapter | relevante via adapter |
| `ToolExecutionPort` | tools | preview/execute | Skills adapter | ToolsRuntime | fora da autoridade Phase 2 |

Todos possuem type coverage indireta; `SkillPolicyPort` não tem implementação nem uso.
`SkillRecordStore` mistura assignment, lease e installation records e não expressa
append-only, revisions, revocation ou recovery. `SkillResolutionPort` expõe payload de
instruções para múltiplos consumidores. `SkillScriptExecutionPort` é o principal
contrato a ser sucedido, não alterado neste slice.

## 10. Runtime atual

| Operation | Current runtime/service | Inputs | Outputs | Side effects | Correct owner? |
| --- | --- | --- | --- | --- | ---: |
| inspect | validation/package | local path | SkillPackage | lê diretório inteiro | sim |
| validate | SkillsRuntime | local path | validity/checksum | evento | sim |
| install | SkillsRuntime | path/actor | installed package | copytree, record, event | parcial |
| register | SkillRegistry | package | none | dict global ao runtime | projeção apenas |
| list/search | SkillDiscovery | query/filters | descriptors | none | sim |
| get/versions | Registry/VersionStore | id/version | package/versions | none | sim |
| resolve | SkillResolver | request | resolution result | event, Governance read | sim/parcial |
| load | SkillLoader | request | content payload | filesystem read/event | parcial |
| assign/unassign | SkillsRuntime | assignment/id | record/none | create/delete/event | sim, delete errado |
| grant/cleanup lease | SkillsRuntime | lease | records/count | create/delete/event | sim, delete errado |
| enable/disable/deprecate | SkillsRuntime | id/version/status | package | regrava manifest(s) | não |
| preview/execute script | SkillsRuntime + Tool adapter | descriptor/inputs | Any | Tool side effects/events | não |
| uninstall | SkillsRuntime | id/version | none | `rmtree`, delete record | não para histórico |
| publish/create/revoke/promote/rollback/update | nenhum | — | — | — | documentação/futuro |

## 11. Stores e persistence

| Store/repository | Records | Backend | Create-only? | Mutable? | Consumers | Authority |
| --- | --- | --- | ---: | ---: | --- | --- |
| package tree | bytes de versão | filesystem | install sim | sim via status | registry/loader | content atual |
| `skill_installations` | install metadata | FileCollection YAML | sim | delete | runtime | instalação parcial |
| `skill_assignments` | assignments | FileCollection YAML | sim | delete | runtime | assignment |
| `skill_leases` | leases | FileCollection YAML | sim | delete | runtime | lease |
| SkillRegistry | SkillPackage projection | process dict | não | sim | runtime | cache, não durável |
| agent CONFIG assignments | bootstrap seed | JSON/YAML file | não | sim | bootstrap | compatibility |

Não há SQLite, database compartilhado ou migration de Skills. FileCollection oferece
locking, atomic write, backups e recovery, mas o adapter usa `skip_with_warning` e não
expõe recovery. `delete()` remove record e backup fisicamente. O restart reconstrói o
registry por `packages/*/*`, enquanto installation records não são reconciliados.

## 12. Registry e discovery

| Mechanism | Input authority | Deterministic? | Secure? | Hidden side effects? | Phase 2 decision |
| --- | --- | ---: | ---: | ---: | --- |
| SkillRegistry dict | packages carregados | sim | process-local | não | projeção read model |
| startup `glob("*/*")` | package filesystem | sim por sort | paths limitados | registra/ignora inválidos | catálogo/store authority |
| textual discovery | manifest metadata | sim | não executa | none | manter como query simples |
| package `rglob("*")` | candidate dir | sim por sort | size/path checks | lê payload inteiro | verificar sem executar |
| agent CONFIG scan | `agents/*/CONFIG.yaml` | sim | confia em local config | cria assignments no boot | migrar/remover como authority |
| provider plugin registry | provider_plugins | sim | outro domain | nenhum Skill import | fora de Phase 2 |

Não há entrypoint scan, `importlib`, dynamic import, arbitrary callable, module scan,
auto-download ou auto-update em Skills. Há lookup por string, mutable registry e
fallback silencioso para a maior versão compatível, que são riscos.

## 13. Execution boundary

| Execution mechanism | Owner atual | Isolation | Security authority | Phase 2 disposition |
| --- | --- | --- | --- | --- |
| `SkillLoader.load` | Skills | nenhuma necessária; lê texto | package validation | manter como materialização limitada |
| `preview_script` | Skills facade→Tools | Tool preview | Tools/Policy/Approval | substituir por handoff |
| `execute_script` | Skills facade→Tools | sem sandbox próprio | Tools/Policy/Approval | fora de Skills |
| `SkillScriptExecutionAdapter` | bootstrap | nenhuma própria | ToolExecutionPort | compatibility até Sandbox |
| shell/subprocess/eval/exec/importlib | inexistente em Skills | — | — | continuar proibido |
| Sandbox Execution Boundary | inexistente | inexistente | futuro módulo | fora da Phase 2 |

O adapter exige exatamente um registered Tool e não usa shell. Ainda assim, a
operação de execução pertence à facade de Skills, aceita `Any`, e
`sandbox_required=True` é apenas metadata; não prova isolamento. A regra Phase 2 é:
resolver e emitir `SkillExecutionReference`; nunca chamar execute.

## 14. Manifest e package format

| Field/group | Exists? | Current meaning | Authority | Required in Phase 2? |
| --- | ---: | --- | --- | ---: |
| skill_id/name/version | sim | identity/display/SemVer | manifest | sim |
| description/summary/authorship | sim | documentação | manifest | sim |
| status | sim | lifecycle mutável | manifest | não no manifest publicado |
| scopes/agent kinds/activation | sim | applicability/discovery | manifest | sim |
| requirements | sim | dict livre | manifest | sim, tipado |
| dependencies/conflicts | sim | Skill DAG/incompatibility | manifest | sim |
| tools/capabilities/providers | sim | requisitos, não grants | manifest | sim como refs |
| resources/references/examples | sim | paths do package | manifest | sim |
| scripts | sim | descriptors/checksums | manifest | sim como handoff declaration |
| context_policy/output_contract | sim | load/output hints | manifest | sim, schema |
| permissions/security fields | sim | restrições declarativas | manifest | refs/facts apenas |
| compatibility | sim | dict livre | manifest | sim, tipado |
| RFC/evidence/quality gates | sim | governance declarations | manifest | bindings tipados |
| package checksum | sim | SHA-256 de paths+bytes | package inspector | sim |
| per-file checksums | só scripts | integrity parcial | manifest | sim para todos os assets |
| signature/provenance/owner | não/parcial authorship | — | — | sim conforme policy |
| lineage/supersession/revocation | não | — | — | sim em records separados |
| configuration schema | não | dicts livres | — | declarar, sem secrets |

Layout atual obrigatório: `manifest.yaml`, `SKILL.md` e arquivos relativos declarados.
Arquivos têm limite de 1 MB individual; não há limite total explícito, symlink policy
documentada, signature ou canonical manifest serialization.

## 15. Versioning e immutability

| Concern | Current behavior | Risk | Phase 2 target |
| --- | --- | --- | --- |
| format | SemVer básica, prerelease aceita | não implementa ordenação prerelease | value object validado |
| comparison | tuple major/minor/patch; `^` ou exact | SemVer incompleta | constraints explícitos |
| duplicate | mesmo id/version+checksum idempotente no registry; install bloqueia sempre | authorities divergentes | content-addressed idempotency |
| latest | maior eligible em `resolve_version` | implicit latest | versão/binding obrigatório |
| mutation | status regrava manifest | quebra imutabilidade/checksum | lifecycle separado |
| overwrite | copytree bloqueia target | bom parcialmente | create-only publish |
| lineage | ausente | sem provenance/supersession | lineage record |
| deprecation | status no manifest | altera publicação | append-only event |
| revocation | ausente | versão insegura continua resolvível | revocation record |
| deletion | uninstall/rmtree/delete | apaga histórico | tombstone + retain bytes/policy |

## 16. Dependency model

| Dependency kind | Represented how? | Resolved by whom? | Current risk | Future owner |
| --- | --- | --- | --- | --- |
| other Skills | SkillDependency | SkillResolver | implicit highest version | Skills catalog/resolution |
| tools | tuple IDs | caller availability + Tools | string lookup | Tools authority |
| capabilities | tuple IDs | caller availability | self-asserted input | Capabilities/Policy |
| providers/models | provider IDs | caller availability | conflates compatibility/trust | Providers/Intelligence |
| datasets/resources | paths only | loader | payload/materialization | Skills refs/Repository |
| runtimes | script.runtime string | não resolvido | arbitrary label | Sandbox |
| Python/system packages | não modelado | ninguém | execução futura incerta | Sandbox/Deployment |
| external services | não modelado | ninguém | egress/secrets | Intelligence/Egress |

Phase 2 declara dependencies e valida facts recebidos; não instala nem resolve
silenciosamente dependências externas.

## 17. Permissions e security

| Permission/security concern | Current implementation | Correct authority | Phase 2 role |
| --- | --- | --- | --- |
| tool access | requirements + intersection em lease | Tools/Policy | transportar refs/facts |
| capability grants | request tuples; manifest requirements | Capabilities/Policy | nunca conceder |
| filesystem/network/egress | permission strings apenas | Intelligence/Policy/Sandbox | restrições declarativas |
| classification/trust | manifest restriction fields | Intelligence Boundary | decision reference |
| model/provider access | provider requirement strings | Models/Providers/Intelligence | compatibility fact |
| secrets | metadata redaction por chave | Secrets/Intelligence | proibir payload |
| resource limits | context budget/script timeout | Sandbox/Context | declarar requirement |
| approval | API `require_admin`, Tool approval_id | Governance/Approvals | approval reference |
| integrity | package/script SHA-256 | Skills | verificar antes de activation |

Redaction por nome de chave não cobre estruturas aninhadas nem prova ausência de
segredos. `external_processing_allowed` e trust requirements são declarações, não
decisões. Installation não confere trust e nunca deve fazê-lo.

## 18. Governance lifecycle

| Lifecycle event | Current owner | Required Evidence | Human approval? | Phase 2 responsibility |
| --- | --- | --- | ---: | --- |
| draft/create | nenhum formal | manifest validation | proposta: sim p/ publish | record candidate |
| publish | nenhum | checksum/provenance | sim por padrão | registrar immutable version |
| install | Skills + admin API | checksum local | admin header | installation record |
| evaluate | Private Evals | immutable refs/results | conforme suite | binding only |
| approve/promote | Project Governance | eval Evidence + RFC/Plan | sim | consume decision ref |
| activate/deactivate | Skills atual | admin only | parcial | lifecycle record após decisão |
| deprecate | Skills atual | nenhum | admin | append-only status |
| revoke | inexistente | security/governance evidence | sim/urgency policy | preserve history, block resolve |
| rollback | inexistente | prior approved binding | sim | activate prior immutable version |
| uninstall | Skills atual | in-use check | admin | detach local availability, retain history |

Skills não aprova RFC, Plan, Mission, Evidence, promotion ou trust.

## 19. Private Evals integration

| Skills artifact | Private Evals reference | Direction | Required now? |
| --- | --- | --- | ---: |
| immutable SkillVersion | `VersionedComponentRef(kind=SKILL)` | Skills→adapter→Evals request | sim na Phase 2 |
| manifest/package fingerprint | `Fingerprint`/component fingerprint | snapshot projection | sim na Phase 2 |
| resolved Skill set | `skill_references` | execution manifest/request | sim na Phase 2 |
| compatibility binding | `skill_fingerprint` | Evals computes/compares | sim na Phase 2 |
| evaluation suite/baseline/result | IDs/fingerprints owned by Evals | Evals→Skills binding ref | sim na Phase 2 |
| regression/evidence | immutable result/evidence refs | Evals→Governance | não armazenar payload em Skills |
| promotion candidate | Skill version + evaluation refs | Skills→Governance | sim na Phase 2 |

Private Evals já aceita referências de Skill versionadas e compara
`skill_fingerprint`, mas não importa `synapse.skills` nem possui adapter de snapshot.
A integração futura deve implementar um adapter fora do módulo congelado. Qualquer
mudança em Private Evals exige RFC/Plan/Mission.

## 20. Compatibilidade e legado

| Legacy element | Current consumers | Replacement candidate | Migration needed? | Removal readiness |
| --- | --- | --- | ---: | ---: |
| agent `SKILLS.md` | identity/context | agent-local instructions + assignments | sim | não |
| `AgentConfig.skills` labels | API/agents | assignment summaries | sim | não |
| researcher CONFIG seed | bootstrap | durable catalog command/migration | sim | não |
| context eager `SKILLS.md` | prompts | resolved budgeted snapshots | sim | não |
| mutable status in manifest | runtime/API | lifecycle records | sim | não |
| script execution port/facade | Tool adapter/tests | execution handoff/Sandbox | sim | não |
| generic SkillRecordStore | runtime | typed stores | sim | não |
| five NUL-only docs | ninguém confiável | este documento/future docs | sim | não; investigar |
| error types sem uso | nenhum | future typed operations ou removal RFC | sim | não |
| provider plugin catalog | providers | nenhuma; outro domain | não | n/a |

Não há V1/V2 Python paralelo localizado. A principal arquitetura antiga é o modelo de
agent skill como texto/label; a principal tentativa Phase 1 a suceder é lifecycle
mutável + script execution na facade.

## 21. Arquitetura proposta para Phase 2

| Concern | Proposed authority | Inputs | Outputs | External dependency |
| --- | --- | --- | --- | --- |
| identity | `SkillId` | canonical semantic name | validated ID | none |
| immutable version | `SkillVersion`/`PublishedSkillVersion` | id, SemVer, fingerprints | immutable ref | none |
| manifest | `SkillManifest` schema | declarations | canonical manifest fingerprint | none |
| package/reference | `SkillContentRef` | URI/local ref + checksums | verified snapshot | Repository port |
| lifecycle | `SkillLifecycleRecord` append-only | version + event + decision refs | state projection | Governance |
| installation | `SkillInstallationRecord` | verified version/content | local availability | local content store |
| activation | `SkillActivationRecord` | exact version + approval | active binding | Governance/Intelligence |
| compatibility | `CompatibilityFact` | subject/environment fingerprints | facts/reasons | Intelligence/Deployment |
| dependencies | typed declarations | exact/constraint refs | graph/plan | external resolvers via facts |
| revocation | `SkillRevocationRecord` | exact version + evidence | block decision/tombstone | Governance/Intelligence |
| resolution | `SkillResolutionService` | exact constraints + context facts | ordered immutable refs | query stores |
| execution handoff | `SkillExecutionReference` | resolved version + entrypoint ref | non-executable descriptor | future Sandbox |
| evaluation binding | `SkillEvaluationBinding` | version/eval refs/fingerprints | eligibility fact | Private Evals port |
| governance binding | `SkillGovernanceBinding` | approval/RFC/Plan/Evidence refs | allowed transition fact | Governance port |
| persistence | typed catalog/lifecycle/install stores | domain records | restartable projections | storage adapters |
| commands | application handlers | explicit actor/idempotency | results/events | ports |
| queries | read service | filters/exact refs | DTOs | projections |
| Composition Root | bootstrap builder | configured adapters | runtime facade/ports | all adapters |

O domínio não recebe package payload quando uma referência suficiente existe. Stores
de versão, lifecycle, installation, activation, revocation e bindings têm semântica
própria; não compartilham um CRUD genérico destrutivo.

## 22. Escopo oficial da Phase 2

### Dentro

- contracts owned by Skills e immutable domain value objects/records;
- schema e canonical validation de manifest;
- fingerprint/checksum/provenance e referências de conteúdo;
- catálogo local, lifecycle e publicação create-only;
- installation/activation/deactivation/revocation records sem apagar histórico;
- resolução determinística com versão explícita;
- dependency declarations e compatibility facts, sem side effects;
- assignments/leases migráveis e auditáveis;
- commands, queries, typed stores e persistence local;
- ports estreitos para Governance, Intelligence, Private Evals e Repository;
- execution handoff descriptor sem execução;
- adapters estreitos, Composition Root, restart/recovery, E2E e freeze audit;
- migration/compatibility projections para Phase 1 e agent `SKILLS.md`.

### Fora

- executar Python, shell, Tool ou qualquer código de Skill;
- criar o Sandbox Execution Boundary;
- download, clone, package manager, dependency installer ou marketplace;
- auto-update, implicit latest, auto-install ou background discovery;
- confiança, classificação, egress, secrets ou permission grants;
- aprovação, promoção autônoma, RFC/Plan/Mission ownership;
- model/provider execution, deployment ou repository cloning;
- modificar Private Evals internals;
- frontend/SDK/global registry/service locator.

Esses itens pertencem a Sandbox, Repository, Deployment, Intelligence, Tools,
Providers, Project Governance ou módulos futuros.

## 23. Invariantes propostas, ainda não congeladas

1. **NO IN-PLACE VERSION MUTATION**: bytes e manifest de versão publicada não mudam.
2. **NO IMPLICIT LATEST**: toda resolução governada fixa versão/fingerprint.
3. **NO INSTALLATION WITHOUT VERIFIED MANIFEST**.
4. **INSTALLATION IS NOT TRUST**.
5. **TRUST IS NOT EXECUTION AUTHORIZATION**.
6. **NO EXECUTION INSIDE SKILLS RUNTIME**.
7. **NO SILENT DEPENDENCY RESOLUTION**.
8. **NO AUTO-PROMOTION**.
9. **NO SELF-MODIFICATION**.
10. **NO SELF-PROMOTION**.
11. **REVOCATION PRESERVES HISTORY**.
12. **REFERENCES BEFORE PAYLOADS**.
13. **CHECKSUMS BEFORE ACTIVATION**.
14. **EXPLICIT HUMAN APPROVAL BY DEFAULT**.
15. Package identity is `(SkillId, SemVer, manifest fingerprint, content fingerprint)`.
16. Installation, trust, evaluation, approval, activation and execution are facts
    distintos e nenhum implica o seguinte.
17. Revoked content is not newly resolved or activated, but remains auditable.
18. All lifecycle commands are actor-attributed, idempotent and append-only.
19. Assignments/leases never widen tools, permissions, trust or scope.
20. Discovery never imports or executes package content.
21. Private Evals and Governance artifacts are referenced by immutable IDs/fingerprints.
22. A cache/registry is never authoritative.

## 24. Slice plan proposto

| Slice | Objetivo único | Authorities/contracts | Invariantes/testes | Fora do escopo | Done |
| ---: | --- | --- | --- | --- | --- |
| 2 | value objects e immutable version/manifest schema | identity/version/manifest | property/unit; no mutation | stores/runtime | **implemented** |
| 3 | typed store contracts append-only | catalog/lifecycle/install/revoke | contract tests, no delete | adapters | ports estáveis |
| 4 | package verification/content references | package/ref/checksums | traversal, symlink, canonical hash | install/download | verified snapshot |
| 5 | publication e catalog queries | version catalog | duplicates/idempotency/no latest | activation | restartable catalog |
| 6 | lifecycle e revocation | lifecycle records | legal transitions/history | governance decisions | projection determinística |
| 7 | installation e activation | install/activation records | verified-before-install/activate | trust | recovery/restart |
| 8 | dependencies/compatibility facts | declarations/facts | explicit resolution/cycles | external install | explainable graph |
| 9 | deterministic resolution boundary | resolver/queries | exact refs/no revoked/latest | execution | stable snapshots |
| 10 | Governance/Intelligence ports | decision references | no grants/self-promotion | implement authorities | fake adapters pass |
| 11 | Private Evals binding | snapshot/evaluation binding | fingerprint consistency | change Evals | frozen module unchanged |
| 12 | execution handoff contract | execution reference | no execute/import/shell | Sandbox | descriptor-only tests |
| 13 | commands/queries | application layer | auth/idempotency/audit | API redesign | complete use cases |
| 14 | concrete local persistence/migration | typed adapters | restart/recovery/corruption | remote stores | durable lifecycle |
| 15 | compatibility adapters | Phase 1/agent migration | no content copy/no authority leak | removals | old consumers preserved |
| 16 | Composition Root e delivery adapters | bootstrap/API/Commands | one construction point | sandbox | production bindings |
| 17 | E2E e failure recovery | integrated runtime | restart/revoke/rollback refs | real execution | acceptance green |
| 18 | final audit/freeze | whole context | full gates/docs/hash baseline | new features | freeze decision |

Cada slice exige um RFC/Plan/Mission quando tocar módulo congelado ou mudar contract
cross-context. Nenhum slice seguinte foi iniciado por esta auditoria.

## 25. Critérios de conclusão do módulo

### Slice implemented

Objetivo único entregue, contracts e invariantes do slice testados, migrations
explicitadas, architecture tests verdes, documentação atualizada e nenhum item fora
do escopo introduzido.

### Functionally complete

Todos os commands/queries, lifecycle, catálogo, install/activate/revoke, resolution,
bindings e migration paths funcionam com referências imutáveis; nenhuma operação de
execução existe no contexto.

### Operationally complete

Persistence sobrevive restart; recovery/corruption/idempotency/concurrency são
testados; audit e observability preservam provenance; security/Governance/Intelligence
decisions são fail-closed; backup/restore e revocation mantêm histórico.

### Frozen

Contracts/exports/schemas/migrations/documentação estão versionados; suites unit,
contract, E2E, architecture, Ruff e Mypy autoritativo estão no baseline aprovado;
grafo e SCC não pioram; compatibility tem plano; nenhum hidden execution/dynamic
import/silent network/implicit latest existe; auditoria final declara escopo completo
e o freeze é aprovado por Governance.

## 26. Quality gates e evidência do Slice 1

| Gate | Command/method | Result |
| --- | --- | --- |
| Skills tests | focused runtime + 7 acceptance files | **PASS: 15 passed** |
| architecture complete | `pytest tests/architecture -q` | **PASS: 137 passed** |
| Ruff touched/relevant Python | `ruff check ...skills...` | **PASS** |
| Mypy Skills | `mypy backend/synapse/skills --cache-dir external` | **PASS: 6 files** |
| authoritative Mypy | `mypy backend/synapse --cache-dir external` | **BASELINE RED: 215 errors/58 files; 518 checked** |
| graph | `_runtime_context_graph()` | **70 contexts / 263 edges** |
| official SCC | Tarjan/cyclic_components | **one 13-context/35-edge SCC** |
| exact graph | runtime absolute imports | **518 modules / 1,584 edges** |
| exact parse/SCC | AST/Tarjan | **0 errors / 0 non-trivial SCCs** |
| security search | requested terms in Skills/support | findings below |
| `git diff --check` | tracked diff + new document | **PASS; somente warnings LF→CRLF preexistentes** |

O Mypy global vermelho é o baseline documentado do worktree e não foi corrigido. O
erro não é causado por este documento; o Mypy isolado de Skills está verde.

Busca de segurança:

- nenhum `eval`, `exec`, `subprocess`, `os.system`, `importlib`, dynamic import,
  arbitrary callable, auto-update, auto-install ou auto-promotion em Skills;
- `replace` encontrado é `dataclasses.replace`, não overwrite de conteúdo;
- `token`/`secret` aparecem no filtro de metadata e em testes de redaction;
- `latest` não aparece literalmente, mas `resolve_version` implementa equivalente
  implícito ao ordenar matches descendentemente;
- delete histórico ocorre semanticamente em `uninstall`, `unassign`,
  `cleanup_leases` e `FileCollection.delete`;
- execução arbitrária não está implementada diretamente, mas a facade encaminha
  script declarado ao Tool boundary sem Sandbox material;
- nenhum credential payload conhecido é persistido pelo contexto.

## 27. Riscos principais e decisões

| Priority | Risk | Decision Phase 2 |
| ---: | --- | --- |
| P0 | manifest publicado mutado por lifecycle | separar records antes de novas features |
| P0 | uninstall/delete destrói histórico | append-only/tombstone |
| P0 | execução exposta pela facade | execution handoff only |
| P0 | implicit highest compatible version | exact resolution/binding |
| P1 | installation authority tripla | typed store + reconciliation |
| P1 | no revocation/promotion/eval binding | implementar refs/lifecycle |
| P1 | manifest security/compatibility como dicts | schemas/facts externos |
| P1 | assignment bootstrap a partir de CONFIG | migration, uma authority |
| P1 | untracked/ignored Phase 1 artifacts | governance/reproducibility closure |
| P2 | NUL-only Skills docs | investigar em slice documental/migration |
| P2 | SemVer prerelease/constraint incompleto | value object/library policy |
| P2 | generic stores and `Any` ports | typed contracts |

## 28. Declarações de encerramento do Slice 1

- Arquivo criado neste Slice: `docs/architecture/skills-runtime-phase-2.md`.
- Arquivos funcionais criados: nenhum.
- Arquivos preexistentes alterados por este Slice: nenhum.
- Nenhum código funcional foi alterado.
- Private Evals Runtime não foi alterado.
- Sandbox Execution Boundary não começou.
- Nenhum adapter, store, Composition Root ou contract foi criado/alterado.
- Nenhum próximo slice foi iniciado.
- Nenhum arquivo foi removido.
- Não houve stage, commit, push ou PR.
- O backend permanece **NOT READY**.

**Skills Runtime Phase 2 — Slice 1 discovery complete, NOT IMPLEMENTED**

## 29. Slice 2 — domain value objects e manifest imutável

Data: **2026-07-26**

Status do slice: **IMPLEMENTED**

Status do módulo: **NOT IMPLEMENTED**

### Auditoria e coexistência da Phase 1

| Existing symbol | Current responsibility | Problem | Reuse? | Phase 2 replacement |
| --- | --- | --- | ---: | --- |
| `SkillScope` | scope operacional/assignment | aplicabilidade e operação misturadas | compatibility only | `SkillPublicationScope` |
| `SKILL_STATUSES` | draft/active/disabled/deprecated | lifecycle dentro do manifest | não | records futuros |
| `SkillDependency` | dependência string/`*` | implicit constraint e reason livre | não | `SkillDependencyDeclaration` |
| `SkillConflict` | conflito string | severity/reason livres | não | `SkillConflictDeclaration` |
| `SkillScriptDescriptor` | script e parâmetros de execução | facade pode executar | não | `SkillExecutionDeclaration` |
| `SkillManifest` | declaração+lifecycle+dicts | mutável em profundidade | compatibility only | `PublishedSkillManifest` |
| `SkillPackage` | conteúdo/path/install state | authorities acopladas | não | content refs + publication ID |
| `SkillDescriptor` | discovery projection | status e strings | sim, Phase 1 | query DTO futuro |
| resolution requests/results | resolver Phase 1 | implicit version selection/dicts | sim, Phase 1 | reservado |
| load requests/results | materialização Phase 1 | carrega payload | sim, Phase 1 | reservado |
| `SkillAssignment` | vínculo persistente | dict/status operacional | sim, Phase 1 | Slice futuro |
| `SkillLease` | vínculo efêmero | lifecycle operacional | sim, Phase 1 | Slice futuro |

Nenhum símbolo Phase 1 foi removido ou convertido automaticamente. Não existe
conversor Phase 1→Phase 2 neste slice: status, dicts livres e package paths não têm
uma conversão segura que preserve as novas invariantes.

### Organização e public surface

A base foi separada por autoridade real em:

- `skills/phase2_values.py`: identidade, SemVer, constraints, fingerprints e
  referências escalares;
- `skills/phase2_models.py`: declarations e aggregate de manifest;
- `skills/phase2_serialization.py`: projeção canônica unidirecional;
- `skills/phase2_errors.py`: erros fixos e seguros;
- `skills/__init__.py`: export mínimo temporário.

Exports Phase 2 no facade: `SkillId`, `SkillVersion`, `SkillVersionConstraint`,
`SkillManifestFingerprint`, `SkillContentFingerprint`,
`SkillManifestFormatVersion`, `PublishedSkillManifest` e
`PublishedSkillVersionId`. Declarations auxiliares permanecem acessíveis apenas pelo
módulo explícito, não foram promovidas automaticamente no facade.

Nenhum contract existente foi alterado.

### Identidade, versão e fingerprints

- `SkillId`: ASCII lowercase kebab-case, 3–64 caracteres, sem Unicode, whitespace,
  separators, traversal ou normalização implícita.
- `SkillVersion`: SemVer 2.0.0 explícita, com prerelease/build, parsing estrito e
  ordering por precedência SemVer; build metadata é preservado na identidade e
  ignorado na precedência, sem tie-break artificial.
- `SkillVersionConstraint`: tipo distinto; aceita caret exato ou comparadores
  explícitos; não aceita `*`, `latest` nem versão concreta nua.
- fingerprints: wrappers semânticos locais para manifest, content e package;
  somente SHA-256 hexadecimal lowercase de 64 caracteres.
- o `Fingerprint` genérico de Private Evals não foi reutilizado porque é internal de
  um módulo congelado e criaria uma edge cross-context indevida.
- `PublishedSkillVersionId`: `(SkillId, SkillVersion, manifest fingerprint, content
  fingerprint)`, serializado canonicamente sem path, timestamp ou estado operacional.

`SkillContentFingerprint` representa um digest já produzido por futura autoridade de
verificação. O cálculo sobre bytes de package continua reservado ao Slice 4.

### Manifest, provenance e content references

`PublishedSkillManifest` é uma frozen dataclass composta somente por nested frozen
dataclasses, enums, value objects e tuples. Não possui arbitrary metadata/extensions.
Campos textuais são limitados e declarações set-like rejeitam duplicatas e são
ordenadas canonicamente. Não há deduplicação silenciosa.

`SkillManifestFormatVersion(1)` é o único formato aceito. Versões desconhecidas
falham; não há migration silenciosa.

`SkillProvenance` usa somente referências namespaced validadas para publisher,
repository, publication, revision, build, signature e lineage. Não aceita URL, path,
credential, token, signature payload ou secret.

`SkillContentRef` contém logical path relativo, SHA-256, kind, media type, size e role
opcional. Não contém bytes e não abre filesystem. Paths absolutos, drive/UNC,
backslash, `..`, segmento vazio e URI são rejeitados.

### Declarations tipadas

- Skill dependencies distinguem exact `SkillVersion` de
  `SkillVersionConstraint`, required/optional e reason code.
- Tool, Capability, Provider/Model e external runtime requirements possuem tipos
  distintos; nenhum é resolvido neste slice.
- compatibility declara operating profiles, platforms, Python/runtime, providers e
  schema versions; não contém decisão `compatible`.
- security usa nomes explícitos de requirement para network, external processing,
  filesystem, egress, Sandbox profile e secret references. Não concede permission,
  trust, secret, egress ou approval.
- `SkillPublicationScope` descreve aplicabilidade e é distinto de `SkillScope`
  operacional; scope nunca concede autoridade.
- `SkillExecutionDeclaration` referencia entrypoint/schema content refs, runtime enum,
  Sandbox profile, resource requirements, Tools e Capabilities. Não possui callable,
  import path, shell command, subprocess args, environment, local executable path,
  payload ou método de execução.

### Canonical serialization e manifest fingerprint

Algoritmo:

```text
deeply immutable domain representation
  -> recursively typed canonical representation
  -> UTF-8 JSON (sort_keys, compact separators, ensure_ascii=false, allow_nan=false)
  -> SHA-256
  -> SkillManifestFingerprint
```

Collections semanticamente set-like são ordenadas antes da serialização. Comentários,
ordem textual de YAML, input ordering, paths locais, timestamps, lifecycle,
installation e trust não participam. O domínio não fornece parser YAML/JSON neste
slice; portanto duplicate-key detection permanece responsabilidade do parser futuro.
Constructors Python rejeitam campos missing/unknown sem coercion.

### Lifecycle separation provada

O manifest publicado não possui `status`, `active`, `disabled`, `deprecated`,
`installed`, `trusted`, `approved`, `evaluated`, `promoted`, `revoked`, `local_path`,
`metadata` ou `payload`. Content refs não possuem active flag; SkillId e
SkillVersion desconhecem lifecycle/trust; publication identity desconhece path e
estado local.

### Errors

Foram adicionados erros tipados para ID, version, constraint, manifest format,
fingerprint, semantic/content reference, dependency, compatibility, security,
manifest canônico e identity mismatch. Mensagens são fixas e não carregam manifest,
path, payload ou stack trace.

### Arquivos do Slice 2

Criados:

- `backend/synapse/skills/phase2_values.py`;
- `backend/synapse/skills/phase2_serialization.py`;
- `backend/synapse/skills/phase2_models.py`;
- `backend/synapse/skills/phase2_errors.py`;
- `tests/test_skills_phase2_models.py`.

Alterados:

- `backend/synapse/skills/__init__.py`;
- `tests/architecture/test_skills_boundaries.py`;
- `docs/architecture/skills-runtime-phase-2.md`.

Contracts, runtime, package parser, stores, adapters, bootstrap, API, Commands e
outros bounded contexts: **não alterados**.

### Testes e gates

Os testes novos cobrem SkillId, SemVer/prerelease/build, constraints, fingerprints,
format version, safe content refs, provenance, dependency/compatibility/security,
non-executable handoff, deep immutability, canonical ordering/fingerprint, lifecycle
absence, immutable publication identity, errors seguros, invalid boundaries e
coexistência Phase 1.

| Gate | Resultado Slice 2 |
| --- | --- |
| novos testes de domínio | **88 passed** |
| Phase 1 runtime + acceptance | **15 passed** |
| execução combinada domínio/coexistência | **103 passed** |
| architecture Skills + completa | **PASS; 139 passed no total** |
| Ruff nos arquivos tocados | **PASS** |
| Mypy Skills | **PASS; 10 source files** |
| Mypy autoritativo | **baseline conhecido: 215 errors/58 files; 522 checked** |
| `git diff --check` | **PASS** |
| context graph | **70 contexts / 263 governed edges** |
| official SCC | **uma SCC herdada de 13 contexts/35 edges; Skills fora** |
| exact-module graph | **522 modules / 1,590 edges / 0 parse errors / 0 SCCs** |

As quatro edges exatas adicionais são internas ao contexto Skills; as edges entre
contexts permanecem 263. O Mypy
autoritativo mantém exatamente os 215 erros preexistentes em 58 arquivos e não
reporta erro em Skills.

Busca de risco nos novos modelos:

- zero `Any`, mutable collection field, callable, importlib, subprocess, shell,
  eval/exec, filesystem/network import ou path local;
- ocorrências de `any(...)` são o builtin de validação, não `typing.Any`;
- backslash aparece somente na rejeição explícita de paths Windows/UNC;
- `secret_reference_requirements` transporta nomes de referências validadas, nunca
  secret/token/credential/payload;
- zero lifecycle state, moving `latest` ou wildcard concrete version.

As 135 ocorrências encontradas nos arquivos Phase 1 para termos amplos como dict,
list, Any, status, active, installed, payload e token são compatibility preexistente
e não foram modificadas.

### Reservado ao Slice 3

- typed append-only store contracts;
- catalog/lifecycle/installation/revocation store semantics;
- idempotency/revision/recovery contracts;
- nenhuma implementação concreta ou persistence.

Também permanecem fora do Slice 3 e deste slice: runtime Phase 2, publicação,
resolução, instalação, ativação, revogação operacional, adapters, Composition Root,
execution, Sandbox e mudanças em Private Evals.

**Skills Runtime Phase 2 — Slice 2 APPROVED, module NOT IMPLEMENTED**

## 30. Auditoria corretiva do Slice 2

Data: **2026-07-26**

Veredito: **SLICE 2 APPROVED**

O veredito aprova apenas os domain models e a representação canônica deste slice.
Não aprova o módulo completo nem autoriza iniciar o Slice 3.

### Matriz arquitetura versus implementação

| Symbol/group | Responsibility | Correct authority? | Deeply immutable? | Public? | Action |
| --- | --- | ---: | ---: | ---: | --- |
| `SkillId` | identidade canônica | sim | sim | sim | KEEP |
| `SkillVersion` | identidade SemVer e precedência | sim | sim | sim | FIX SEMANTICS concluído |
| `SkillVersionConstraint` | range explícito sem seleção | sim | sim | sim | FIX SEMANTICS concluído |
| `PublishedSkillVersionId` | identidade publicada completa | sim | sim | sim | KEEP |
| fingerprint types | digests SHA-256 semanticamente distintos | sim | sim | content/manifest | KEEP |
| manifest format | discriminador estrito v1 | sim | sim | sim | KEEP |
| `PublishedSkillManifest` | aggregate declarativo publicado | sim | sim | sim | KEEP |
| provenance | referências declarativas de origem | sim | sim | não | KEEP INTERNAL |
| content references | identidade lógica de conteúdo, sem I/O | sim | sim | não | KEEP INTERNAL |
| execution declaration | handoff declarativo, não executável | sim | sim | não | KEEP INTERNAL |
| dependencies | requirements/conflitos tipados | sim | sim | não | KEEP INTERNAL |
| compatibility | requirements, não decisões | sim | sim | não | KEEP INTERNAL |
| security | requirements/restrições, não grants | sim | sim | não | FIX SEMANTICS concluído |
| publication scope | aplicabilidade, não autorização | sim | sim | não | KEEP INTERNAL |
| canonical serializer | projeção canônica unidirecional | sim | stateless | não | SPLIT FOR COHESION concluído |
| errors | falhas fixas e seguras | sim | sim | não no facade | KEEP INTERNAL |

### Organização final

| Section/file | Approximate lines | Authority | Coupling | Should remain together? |
| --- | ---: | --- | --- | ---: |
| `phase2_values.py` | 334 | escalares, SemVer e fingerprints | errors | sim |
| `phase2_models.py` | 583 | declarations e manifest aggregate | values, serializer, errors | sim |
| `phase2_serialization.py` | 65 | domain-to-canonical JSON | value types | sim |
| `phase2_errors.py` | 59 | taxonomia de erro | nenhuma | sim |

SemVer deixou de conhecer manifest e o serializer deixou de estar embutido no
aggregate. As declarations permanecem juntas porque formam o vocabulário fechado do
manifest e compartilham as mesmas invariantes de tuple/uniqueness. Dividi-las mais
agora criaria arquivos por tamanho, não novas authorities.

### SkillId

| Input class | Expected | Actual | Test |
| --- | --- | --- | --- |
| `abc`, `research-synthesis`, limites 3/64 | aceitar sem normalizar | match | positivo/boundary |
| uppercase, Unicode, whitespace, control | rejeitar | match | parametrizado |
| hyphen inicial/final/repetido | rejeitar | match | parametrizado |
| `con`, `nul`, `com1`, `lpt9` | rejeitar | match | parametrizado |
| slash, backslash, traversal, `_`, `$` | rejeitar | match | parametrizado |

Regex efetiva: lowercase ASCII alfanumérico com hyphens internos, 3–64 caracteres.
Equality/hash/repr/serialization preservam exatamente o valor aceito. Não existe
lowercasing, trimming, Unicode normalization ou outra canonicalização silenciosa.

### SemVer, equality e precedência

| Version A | Version B | Expected relation | Actual |
| --- | --- | --- | --- |
| `1.0.0-alpha` | `1.0.0-alpha.1` | A < B | match |
| `1.0.0-alpha.1` | `1.0.0-alpha.beta` | A < B | match |
| `1.0.0-beta.2` | `1.0.0-beta.11` | A < B numérico | match |
| `1.0.0-rc.1` | `1.0.0` | A < B | match |
| `1.0.0+build.1` | `1.0.0+build.2` | mesma precedência | match |

Major/minor/patch não aceitam zero à esquerda; prerelease numérico também não.
Identifiers são ASCII `[0-9A-Za-z-]+`, não vazios, sem dots consecutivos. Os vetores
oficiais SemVer 2.0.0 passam.

Equality/hash são estruturais e incluem build metadata, porque uma versão publicada
concreta preserva sua identidade. `compare_precedence()` e
`has_same_precedence()` ignoram build. `<` expressa somente precedência: versões com
builds diferentes podem ser desiguais e incomparáveis por `<`. Não há
`total_ordering`, `<=` sintético nem tie-break lexical. Essa strict weak ordering é
deliberada e não deve ser usada como canonical ordering de identidade; o serializer
inclui o build.

### Constraints

| Constraint | Valid? | Meaning | Deterministic? |
| --- | ---: | --- | ---: |
| `^1.2.3` | sim | caret SemVer ancorado em versão completa | sim |
| `>=1.2.3,<2.0.0` | sim | intervalo bounded lower-inclusive/upper-exclusive | sim |
| `>1.2.3,<=2.0.0` | sim | intervalo bounded lower-exclusive/upper-inclusive | sim |
| `1.2.3`, `~1.2.3` | não | exact usa `SkillVersion`; tilde não suportado | sim |
| `*`, `latest`, vazio | não | moving/implicit selection proibida | sim |
| `>=1.0.0` ou `<2.0.0` | não | range sem um dos limites | sim |
| whitespace/coercion/reversed bounds | não | forma não canônica/ambígua | sim |

O slice representa e valida a linguagem, mas não testa membership, seleciona versão,
resolve dependência ou fornece fallback.

### Publication identity, fingerprints e format

`PublishedSkillVersionId` exige, em ordem fixa, `SkillId`, `SkillVersion`,
`SkillManifestFingerprint` e `SkillContentFingerprint`. O texto canônico é:

```text
<skill>@<version>#manifest-sha256:<64hex>;content-sha256:<64hex>
```

Há round-trip estrito e divergência testada para cada componente. Build metadata faz
parte da versão concreta. Path, timestamp, lifecycle e estado local não entram.
Checks de runtime impedem a troca dos fingerprint types.

Todos os fingerprints usam exclusivamente SHA-256 lowercase com 64 hex chars, sem
prefixo armazenado, algoritmo arbitrário, truncamento ou normalização uppercase.
Dataclass equality/hash preservam o tipo semântico. `SkillPackageFingerprint`
permanece internal; o cálculo de content/package bytes não pertence a este slice.

`SkillManifestFormatVersion` aceita somente o inteiro `1`; rejeita string, bool,
zero, negativos e futuros. Sua projeção JSON canônica também é o número `1`. Não há
migration ou interpretação permissiva.

### PublishedSkillManifest

| Field | Type | Required? | Ordered? | Lifecycle-free? | Authority |
| --- | --- | ---: | ---: | ---: | --- |
| format_version | format VO | sim | n/a | sim | schema |
| skill_id/version | identity VOs | sim | n/a | sim | publication |
| display_name/summary/description | bounded strings | sim | n/a | sim | declaration |
| provenance | frozen record | sim | field order only | sim | declaration |
| scopes | tuple enum | sim/nonempty | não, set-like | sim | applicability |
| content | tuple content refs | sim/nonempty | não, set-like | sim | content declaration |
| dependencies/conflicts | typed tuples | não | não, set-like | sim | requirements |
| tools/capabilities/providers | typed tuples | não | não, set-like | sim | requirements |
| compatibility/security | frozen records | não/default | nested set-like | sim | requirements |
| execution | declaration tuple | não | não, set-like | sim | handoff |
| governance/evaluation requirements | typed tuples | não | não, set-like | sim | requirements |
| configuration_schema_ref | content ref | não | n/a | sim | declaration |

Não há status, active, disabled, operational deprecation, installed, trusted,
approved, promoted, revoked, local path, last-used, arbitrary metadata, dict, list,
`Any`, callable ou raw payload. Não existe deprecation declarativa neste formato.

### Deep immutability e canonical ordering

Todos os records são frozen; toda collection aceita é tuple; nested values também
são frozen. Lists não são convertidas: são rejeitadas para impedir coercion e alias
com input mutável. Não existem dict inputs. Mutation de atributo, tuple e item
aninhado falha; hash e fingerprint permanecem estáveis após tentativas de mutação.

| Collection | Semantic order? | Canonical rule | Duplicate policy |
| --- | ---: | --- | --- |
| scopes/content | não | sort por canonical JSON | reject |
| dependencies/conflicts | não | sort por canonical JSON | reject |
| tools/capabilities/providers | não | sort por canonical JSON | reject |
| compatibility nested tuples | não | sort por canonical JSON | reject |
| execution/governance/evaluation | não | sort por canonical JSON | reject |
| execution required tools/capabilities | não | sort por canonical JSON | reject |
| SemVer prerelease/build identifiers | sim | preserve | preserve |
| provenance fields | record, não collection | schema field names | n/a |

Content também rejeita paths lógicos duplicados mesmo se outros atributos diferirem.
Self-dependency é rejeitada no aggregate.

### Canonical serialization, parser boundary e fingerprint

O serializer é interno e unidirecional: frozen domain record → primitives → JSON
UTF-8, `sort_keys=True`, separators `(",", ":")`, `ensure_ascii=False` e
`allow_nan=False`. StrEnums viram seus values, tuples viram arrays, `None` vira
`null`, nested dataclasses viram objetos. Não há Decimal no domínio; tipo
desconhecido falha. Não há type import reconstruction, pickle, parser ou
deserializer.

O golden manifest tem fingerprint:

```text
d7b299d31602dfbdc2b67664e33cb67b4985ab09b8a0ccea5b585740728d8534
```

Ele é estável com construction order invertida e em execuções separadas do teste.
Mudanças em display text e build metadata mudam o fingerprint por serem semânticas
no manifest. Ordem incidental não muda. Lifecycle externo, local path, comentário e
ordem YAML não podem entrar porque não existem na representação tipada. Duplicatas
falham.

Este slice recebe somente records tipados. Não há função pública para raw mappings,
JSON ou YAML, e o serializer não deserializa. Um parser futuro poderia colapsar
duplicate keys antes do domínio; essa proteção ainda não existe. Precondição:

**RAW MANIFEST PARSING MUST REJECT DUPLICATE KEYS BEFORE DOMAIN CONSTRUCTION**

### Provenance, content e execution

Provenance aceita referências namespaced validadas, nunca URL arbitrária, path,
credential, token, raw signature, mutable metadata, trusted ou approval. Ela declara
publisher/repository/publication/revision/build/signature/lineage references; não
carrega prova e não toma decisão de confiança.

Logical paths aceitam `file.txt` e `dir/file.txt`; rejeitam `../file`,
`dir/../file`, absoluto, drive, UNC, segmento vazio, slash repetido, backslash, dot
segment, control, trailing slash, Unicode e mais de 512 caracteres. Size aceita zero
e rejeita negativo/bool. Media type e checksum type são validados. Nenhum filesystem
é aberto.

Execution usa apenas `SkillContentRef` já declarado, enum fechado Python/WASM,
reference de Sandbox profile e limits numéricos. Não contém callable, command, argv,
shell, import path, module/executable path, environment values, secrets, subprocess
ou método executor. `runtime` e `entrypoint` são identifiers declarativos; nenhuma
execução foi implementada.

### Dependencies, compatibility, security e scope

| Type | Identity | Version semantics | Optional? | Reason | Duplicates |
| --- | --- | --- | ---: | --- | --- |
| skill dependency | SkillId | exact XOR bounded constraint | sim, explícito | enum obrigatório | reject |
| conflict | SkillId | constraint opcional | n/a | semantic ref | reject |
| tool | requirement ID | constraint opcional | não | n/a | reject |
| capability | requirement ID | constraint opcional | não | n/a | reject |
| provider/model | IDs tipados | constraint opcional | não | n/a | reject |
| external runtime | requirement ID | constraint obrigatório | não | n/a | reject |

Ordering é determinístico; não existe implicit latest, resolution, instalação ou side
effect. Self-dependency detectável é rejeitada.

Compatibility contém apenas requirements de profiles, platforms, Python, runtimes,
providers e schemas. Não aceita `compatible`, `trusted`, `approved` ou
`supported_by_system`; um manifest não declara a decisão externa.

Security diferencia requirement/restriction de autorização por nomes:
`network_requirement`, `external_processing_requirement`,
`filesystem_requirement`, `egress_requirement`,
`sandbox_profile_requirement` e `secret_reference_requirements`. Ela não contém
network allowed, external processing authorized, secret provided, permission,
credential ou approval. Egress declarado exige network requirement diferente de
none, mas continua sendo requirement, nunca grant.

`SkillPublicationScope` descreve aplicabilidade system/user/workspace/project/agent/
mission/task. Não concede permission, assignment, actor/project authorization ou
trust e não substitui o `SkillScope` operacional de Phase 1.

### Errors e public surface

| Error | Trigger | Fixed safe message? | Public facade? | Leaks input? |
| --- | --- | ---: | ---: | ---: |
| `SkillPhase2DomainError` | base de domínio | sim | não | não |
| `InvalidSkillId` | ID inválido | sim | não | não |
| `InvalidSkillVersion` | SemVer/comparison inválida | sim | não | não |
| `InvalidSkillVersionConstraint` | constraint inválida | sim | não | não |
| `UnsupportedSkillManifestFormat` | format diferente de 1 | sim | não | não |
| `InvalidSkillFingerprint` | digest inválido | sim | não | não |
| `InvalidSkillReference` | semantic/provenance ref inválida | sim | não | não |
| `InvalidSkillContentReference` | path/media/size/type inválido | sim | não | não |
| `InvalidSkillDependencyDeclaration` | requirement inválido | sim | não | não |
| `InvalidSkillCompatibilityDeclaration` | compatibility inválida | sim | não | não |
| `InvalidSkillSecurityDeclaration` | security inválida | sim | não | não |
| `InvalidPublishedSkillManifest` | aggregate inválido | sim | não | não |
| `NonCanonicalSkillManifest` | canonical input futuro | sim | não | não |
| `ImmutableSkillIdentityMismatch` | publication identity divergente | sim | não | não |

Mensagens, repr e cause chain testados não contêm raw input. O parser de publication
identity encadeia somente uma exceção interna de mensagem fixa.

| Export | Needed by Slice 3? | Stable enough? | Internal detail? | Decision |
| --- | ---: | ---: | ---: | --- |
| SkillId | sim | sim | não | export |
| SkillVersion | sim | sim | não | export |
| SkillVersionConstraint | sim | sim | não | export |
| SkillManifestFingerprint | sim | sim | não | export |
| SkillContentFingerprint | sim | sim | não | export |
| SkillManifestFormatVersion | sim | sim | não | export |
| PublishedSkillManifest | sim | sim | não | export |
| PublishedSkillVersionId | sim | sim | não | export |

Serializer, helpers, enums, declarations auxiliares, concrete collection details e
package fingerprint não são exportados pelo facade.

### Coexistência, boundaries e coverage

Phase 1 não teve imports redirecionados, alias semântico alterado ou converter
automático. Runtime/API/Commands Phase 1 seguem nos modelos antigos e os 15 testes
passam. O status Phase 1 não entra no manifest Phase 2.

Os três módulos de domínio importam apenas stdlib, seus próprios values/errors e o
serializer interno. Não importam runtime, stores, adapters, bootstrap, API, Tools
runtime, Sandbox, Governance runtime, Private Evals, filesystem, network, importlib
ou subprocess. O teste AST também proíbe `eval`, `exec`, `compile`, `open`,
`os.system` e `Popen`.

| Concern | Positive | Boundary | Invalid | Immutability | Canonicalization |
| --- | ---: | ---: | ---: | ---: | ---: |
| SkillId | sim | sim | sim | sim | sim |
| SemVer | sim | sim | sim | sim | sim |
| constraints | sim | sim | sim | sim | sim |
| fingerprints | sim | sim | sim | sim | sim |
| publication ID | sim | sim | sim | sim | sim |
| manifest | sim | sim | sim | sim | sim |
| provenance | sim | sim | sim | sim | sim |
| content refs | sim | sim | sim | sim | sim |
| execution | sim | sim | sim | sim | sim |
| dependencies | sim | sim | sim | sim | sim |
| compatibility | sim | sim | sim | sim | sim |
| security | sim | sim | sim | sim | sim |
| scope | sim | sim | sim | sim | sim |
| errors | sim | sim | sim | n/a | n/a |
| exports | sim | sim | sim | n/a | n/a |

### Correções, gates e riscos residuais

Correções realizadas:

1. removido tie-break lexical de build metadata na precedência SemVer;
2. separada equality estrutural de equivalência de precedência;
3. constraints comparator passaram a exigir lower e upper bounds;
4. IDs passaram a rejeitar repeated hyphen e nomes Windows reservados;
5. value objects e serializer foram separados do aggregate monolítico;
6. serializer deixou de chamar protocol/método arbitrário;
7. `format_version` passou a ser número no JSON canônico;
8. security fields receberam nomes inequívocos de requirement;
9. duplicatas e self-dependency passaram a falhar explicitamente;
10. regex numéricas passaram a usar somente dígitos ASCII;
11. coverage ganhou vetores oficiais, type confusion, deep immutability,
    publication divergence, safe cause chain e golden hash.

| Gate | Corrective result |
| --- | --- |
| Phase 2 domain | **PASS: 88 passed** |
| Phase 2 + Skills boundary | **PASS: 95 passed** |
| Phase 1 | **PASS: 15 passed** |
| coexistence combined | **PASS: 103 passed** |
| architecture complete | **PASS: 139 passed** |
| Ruff touched | **PASS** |
| Mypy Skills | **PASS: 10 source files** |
| authoritative Mypy | **baseline: 215 errors/58 files; 522 checked; zero Phase 2** |
| `git diff --check` | **PASS; line-ending warnings only** |
| official graph | **70 contexts / 263 governed edges** |
| official SCC | **one inherited 13-context/35-edge SCC; Skills outside** |
| exact graph | **522 modules / 1,590 edges / 0 parse errors** |
| exact SCC | **0 non-trivial SCCs** |

Riscos residuais deliberadamente fora do slice: duplicate-key rejection no parser
futuro; cálculo/verificação de package/content fingerprint; proof/signature/trust;
persistência append-only; lifecycle; publication/install/resolve runtime; policy
authorization; Sandbox execution. Nenhum deles é falsamente declarado como pronto.

Arquivos criados pelo Slice 2: `phase2_values.py`, `phase2_serialization.py`,
`phase2_models.py`, `phase2_errors.py` e `test_skills_phase2_models.py`. Arquivos
alterados: facade `skills/__init__.py`, boundary test e este documento. Arquivos
removidos: nenhum. Não houve store, persistence, runtime Phase 2, lifecycle,
publication, installation, resolution, adapter, Command/Query, Composition Root,
execution, Sandbox, Private Evals ou Slice 3. Não houve stage, commit, push ou PR.
O backend permanece **NOT READY**.

## 31. Slice 3 — implementação inicial, substituída pela auditoria corretiva

Data: **2026-07-26**

Status histórico: **SUPERSEDED BY SECTION 32**

O Slice 3 define somente records e ports de persistência. Não existe concrete store,
SQLite, filesystem adapter, serialization de persistence, runtime Phase 2 ou
Composition Root.

### Auditoria dos mecanismos Phase 1

| Current mechanism | Records | Mutations | Deletes | Problems | Phase 2 disposition |
| --- | --- | --- | --- | --- | --- |
| `SkillRecordStore` | `dict[str, Any]` | `put`, overwrite possível | `delete` | authority genérica, sem tipos/replay | manter Phase 1; não reutilizar |
| `SkillRecordStoreAdapter` | mappings em `FileCollection` | put/create-only | delete físico | vaza backend contract | manter Phase 1 |
| package filesystem | manifest/SKILL.md/resources | copy/status rewrite | `rmtree` | conteúdo, instalação e lifecycle juntos | adapter futuro separado |
| `SkillRegistry` | packages em memória | replace/register | remove | status no manifest, latest implícito | compatibility Phase 1 |
| installation records | mapping schema v1 | create-only inicial | delete no uninstall | histórico destruído | installation facts + termination |
| assignment records | mapping com metadata | create | delete no unassign | constraint, mutable dict, sem histórico | exact assignment + termination |
| lease records | mapping | create | cleanup destrutivo | background cleanup apaga fatos | lease + termination/expiration |
| researcher CONFIG seed | assignment declarativo | config edit | n/a | string constraint sem publication identity | migration futura explícita |

Phase 1 não foi alterada. Seus deletes e tipos genéricos continuam apenas como
compatibility congelada.

### Records criados

| Family | Records | Semantic parent |
| --- | --- | --- |
| catalog | `PublishedSkillVersionRecord`, `SkillPublicationRecord` | manifest/identity |
| lifecycle | `SkillLifecycleRecord`, `SkillActivationRecord`, `SkillRevocationRecord` | published version; activation também installation |
| installation | `SkillInstallationRecord`, `SkillInstallationTerminationRecord` | published version / installation |
| assignment | `SkillAssignmentRecord`, `SkillAssignmentTerminationRecord` | exact version / assignment |
| lease | `SkillLeaseRecord`, `SkillLeaseTerminationRecord` | assignment + exact version + task |
| external bindings | `SkillGovernanceBindingRecord`, `SkillEvaluationBindingRecord` | exact version |
| verification | `SkillContentVerificationRecord` | exact version/content fingerprint |

Não foram criados publication payload, trust decision, compatibility decision,
projection record ou generic repository.

### Separation of concerns

| Concern | Record owner | Store owner | Mutable? | CAS? | Append-only? |
| --- | --- | --- | ---: | ---: | ---: |
| publication/version catalog | catalog records | Catalog | não | não | create-only |
| lifecycle/activation/revocation | lifecycle facts | Lifecycle | não | não | sim |
| installation/detachment | installation facts | Installation | não | não | sim |
| assignment/termination | assignment facts | Assignment | não | não | sim |
| lease/expiration | lease facts | Lease | não | não | sim |
| Governance/Eval bindings | reference-only bindings | Binding | não | não | create-only |
| content verification | verifier fact | ContentVerification | não | não | create-only |

Stores persistem records já validados; transitions, policy, verification, projection
e decisões pertencem a services futuros.

### Protocols

| Protocol | Records owned | Methods | Why separate? |
| --- | --- | ---: | --- |
| `SkillCatalogStore` | version/publication | 6 | identidade publicada create-only |
| `SkillLifecycleStore` | lifecycle/activation/revocation | 4 | histórico operacional sem manifest mutation |
| `SkillInstallationStore` | install/termination | 3 | disponibilidade local não é publicação |
| `SkillAssignmentStore` | assignment/termination | 3 | binding a subject não é lifecycle |
| `SkillLeaseStore` | lease/termination | 5 | fatos temporais e queries agent/task/version |
| `SkillBindingStore` | Governance/Eval refs | 3 | correspondência externa sem imports |
| `SkillContentVerificationStore` | verification facts | 2 | corrupção/verificação separada de trust |

Não há protocol por record e não há repository genérico.

### Semântica por store

`SkillCatalogStore` salva exact published versions e publication records em
create-only, faz lookup apenas por `PublishedSkillVersionId`, existência tipada e
listagem bounded por `SkillId`. Não possui latest, wildcard, lifecycle, installation,
delete, payload ou package bytes.

`SkillLifecycleStore` aceita fatos já construídos de lifecycle, activation e
revocation e retorna histórico por exact version. Não valida transitions, calcula
latest ou sobrescreve estado.

`SkillInstallationStore` diferencia instalação local de termination/detachment. Não
copia arquivo, verifica checksum, concede trust ou apaga histórico.

`SkillAssignmentStore` registra assignment exato e termination/replacement. Records
não contêm permissions, tools, capabilities ou trust; current projection será
derivada futuramente.

`SkillLeaseStore` registra grant e termination/expiration/supersession e oferece
histórico explícito por agent, task e exact version. Não executa cleanup.

`SkillBindingStore` compartilha Governance/Eval porque ambas são correspondências
create-only reference+fingerprint para a mesma exact version. Os records são
distintos. O store não lê Governance, importa Private Evals, transporta Evidence/
approval payload ou recalcula decisions.

`SkillContentVerificationStore` foi mantido separado: verificação será necessária
para restart/corruption detection, mas o record carrega somente exact content
fingerprint, verifier ID/version, outcome, reason refs, timestamp e provenance ref.
O store não lê filesystem, calcula digest ou prova trust.

### CAS, idempotency e outcomes

CAS foi explicitamente adiado. Não existe mutable projection pointer ou aggregate
revision legítima neste slice; history append-only e projections derivadas evitam
introduzir revision artificial. `SkillStoreStaleRevision` reserva a taxonomia sem
criar método CAS.

Cada write usa `SkillStoreRecordId`, uma identidade namespaced:

- ausência da identidade: `CREATED`;
- mesmo ID e record estruturalmente idêntico: `IDEMPOTENT_REPLAY`;
- mesmo ID com conteúdo diferente: `SkillStoreDivergentDuplicate`;
- catalog version também impõe unicidade de `PublishedSkillVersionId`.

Não existe idempotency table ou generic idempotency key.

Outcomes de write são `SkillStoreWriteOutcome.CREATED` e
`IDEMPOTENT_REPLAY`. Existência usa `SkillStoreExistence.PRESENT/ABSENT`, nunca bool.
Not-found, conflict, integrity e availability são erros tipados.

### Errors

| Error | Contract meaning | Safe fixed message |
| --- | --- | ---: |
| `InvalidSkillStoreRecord` | record/query inválido | sim |
| `SkillStoreNotFound` | exact lookup ausente | sim |
| `SkillStoreSemanticConflict` | conflito semântico | sim |
| `SkillStoreDivergentDuplicate` | identidade igual/conteúdo diferente | sim |
| `SkillStoreStaleRevision` | CAS futuro, se justificado | sim |
| `SkillStoreIntegrityMismatch` | fingerprint/integrity divergente | sim |
| `SkillStoreInvalidParentReference` | parent ausente/mismatched | sim |
| `SkillStoreRecordFormatUnsupported` | format diferente de v1 | sim |
| `SkillStoreReadOnlyViolation` | write proibido | sim |
| `SkillStoreUnavailable` | backend indisponível | sim |

Os tipos ignoram texto fornecido pelo adapter e sempre expõem sua mensagem fixa;
path, database, SQL, raw record, payload, token e stack não entram.

### Queries e pagination

Queries permitem somente exact identity, `SkillId`, history por exact version e
filtros explícitos por subject/agent/task. Não há free search, arbitrary predicate,
query language, SQL ou list-all irrestrito.

`SkillStorePageRequest` limita páginas a 1–200 e usa
`after_record_id` como keyset; `SkillStorePage` retorna tuple e próximo record ID.
Ordering contratual é ascendente por semantic record ID, sem offset ou sort
arbitrário. A implementação concreta do cursor foi adiada.

### Parent correspondence

| Child | Required correspondence |
| --- | --- |
| publication/lifecycle/revocation | exact published version |
| installation | exact published version |
| activation | exact version + matching installation |
| installation termination | matching installation/version |
| assignment | exact published version |
| assignment termination | matching assignment/version |
| lease | matching assignment/version + agent/task refs |
| lease termination | matching lease/version |
| Governance/Eval binding | exact published version |
| verification | exact version and identical content fingerprint |

Fakes de conformance rejeitam parent local ausente ou mismatched. Correspondências
cross-store não pressupõem foreign key ou transaction concreta; a futura authority
de aplicação coordenará atomicidade.

### Record format, immutability e serialization boundary

`SkillStoreRecordFormatVersion(1)` é distinto de manifest format e SkillVersion.
Unknown, bool, zero e futuros falham; não há migration. Todos os records usam frozen
dataclasses, tuples, enums/value objects e timestamps UTC-aware. Não há dict, list,
`Any`, callable ou payload.

Records não implementam serialization de persistence. Determinismo deriva de
schema fechado, field types e canonical tuple ordering. Published identities já
carregam manifest/content fingerprints; bindings carregam typed external record
fingerprints; verification carrega o exact content fingerprint. Record-level
canonical bytes/checksum foram adiados ao adapter concreto e não reutilizam
automaticamente o serializer do Slice 2.

### Phase 1 mappings

| Phase 1 record | Phase 2 candidate | Migration concern |
| --- | --- | --- |
| installed `SkillPackage` + mapping | published + installation records | validar content identity antes |
| manifest status rewrite | lifecycle/activation/revocation facts | reconstruir history impossível sem audit |
| `SkillAssignment` | exact assignment record | resolver constraint explicitamente |
| assignment delete | termination record | deletes antigos não têm reason/timestamp confiável |
| `SkillLease` | exact lease record | ligar a assignment/version/task |
| cleanup/delete | lease termination/expiration | preservar fatos antigos |
| researcher CONFIG assignment | assignment candidate | não converter implicitamente `^1.0.0` |

Nenhum mapping foi executado e `SkillRecordStore` não foi alterado.

### Public surface e test doubles

O facade exporta somente os sete protocols, quatorze records, enums/reasons necessários,
page request/result, record identity/format/fingerprint, outcomes e errors. Helpers
de timestamp, validators e qualquer fake permanecem internos.

Os fakes estão somente em `tests/test_skills_phase3_store_contracts.py`. Eles
implementam conformance create-only/append-only em memória para provar replay,
divergent conflict, no delete, exact lookup, deterministic history, keyset
pagination, parent correspondence, deep immutability e safe errors. Não existe fake
ou concrete implementation em production.

### Arquivos e gates

Criados:

- `backend/synapse/skills/phase3_values.py`;
- `backend/synapse/skills/phase3_records.py`;
- `backend/synapse/skills/phase3_contracts.py`;
- `backend/synapse/skills/phase3_errors.py`;
- `tests/test_skills_phase3_store_contracts.py`.

Alterados:

- `backend/synapse/skills/__init__.py`;
- `tests/architecture/test_skills_boundaries.py`;
- `docs/architecture/skills-runtime-phase-2.md`.

Contracts/runtime/models/adapters Phase 1 e Private Evals: não alterados.

| Gate | Slice 3 result |
| --- | --- |
| new record/contract conformance | **PASS: 8 passed** |
| Slice 2 + Slice 3 + Skills boundary | **PASS: 106 passed** |
| Phase 1 | **PASS: 15 passed** |
| combined Phase 1/2/3 | **PASS: 111 passed** |
| architecture complete | **PASS: 142 passed** |
| Ruff touched | **PASS** |
| Mypy Skills | **PASS: 14 source files** |
| authoritative Mypy | **baseline: 215 errors/58 files; 526 checked; zero Phase 3** |
| `git diff --check` | **PASS; line-ending warnings only; no-index PASS** |
| official graph | **70 contexts / 263 governed edges** |
| official SCC | **one inherited 13-context/35-edge SCC; Skills outside** |
| exact graph | **526 modules / 1,602 edges / 0 parse errors** |
| exact SCC | **0 non-trivial SCCs** |

Busca nos quatro arquivos Phase 3: zero delete/remove/overwrite/upsert, mutable
dict/list, `Any`, callable, filesystem, SQLite/SQL, path, payload, latest, wildcard,
execute, subprocess, importlib, approval, trust grant ou egress grant. As 13
ocorrências textuais de `replace` são exclusivamente os reason values `REPLACED`,
não operações. Ocorrências Phase 1 foram classificadas separadamente e não mudaram.

### Riscos residuais e reserva do Slice 4

Riscos deliberados: nenhum adapter concreto prova ainda restart, durability,
atomicidade cross-store, corruption recovery ou record canonical checksum; page
cursor concreto e projections atuais também não existem.

Reservado ao Slice 4: concrete persistence/adapters somente se a especificação futura
os autorizar, serialization determinística de records, integrity verification,
restart/recovery e wiring correspondente. Este slice não iniciou nenhuma dessas
atividades.

Nenhum concrete store, SQLite, filesystem adapter, runtime Phase 2, publication,
installation, activation, revocation, resolution, Command/Query, external adapter,
Composition Root, execution ou Sandbox foi implementado. Private Evals não foi
alterado. Não houve stage, commit, push ou PR. O backend permanece **NOT READY**.

**Initial Slice 3 implementation — superseded by the corrective audit below**

## 32. Auditoria corretiva do Slice 3

Data: **2026-07-26**

Veredito: **SLICE 3 APPROVED**

Esta seção é a authority atual para o Slice 3. A implementação inicial da seção 31
permanece apenas como histórico e não descreve mais a superfície vigente.

### Inventário exato

| Symbol | File | Category | Responsibility | Public? | Consumer |
| --- | --- | --- | --- | ---: | --- |
| `SkillStoreRecordId` | phase3_values | ID | event identity namespaced | não | stores internos futuros |
| `SkillStoreRecordFingerprint` | phase3_values | fingerprint | external binding digest | não | binding service futuro |
| `SkillStoreQueryLimit` | phase3_values | query value | bounded result size 1–200 | sim | todos os query consumers |
| `SkillLifecycleKind` | phase3_records | enum | lifecycle fact kind | não | lifecycle service futuro |
| `SkillLifecycleReason` | phase3_records | reason enum | closed lifecycle reason | não | lifecycle service futuro |
| `SkillInstallationTerminationReason` | phase3_records | reason enum | detach/uninstall/replace/corruption | não | installation service futuro |
| `SkillAssignmentTerminationReason` | phase3_records | reason enum | revoke/replace/expire | não | assignment service futuro |
| `SkillLeaseTerminationReason` | phase3_records | reason enum | expire/terminate/supersede | não | lease service futuro |
| `PublishedSkillVersionRecord` | phase3_records | record | única authority de catalog existence/publication | sim | Slice 4/5 |
| `SkillLifecycleRecord` | phase3_records | record | generic non-activation/revocation fact | não | lifecycle service |
| `SkillActivationRecord` | phase3_records | record | activation referencing installation | não | activation service |
| `SkillRevocationRecord` | phase3_records | record | revocation with decision ref | não | revocation service |
| `SkillInstallationRecord` | phase3_records | record | local availability fact | não | installation service |
| `SkillInstallationTerminationRecord` | phase3_records | record | installation terminal fact | não | installation service |
| `SkillAssignmentRecord` | phase3_records | record | exact-version assignment | não | assignment service |
| `SkillAssignmentTerminationRecord` | phase3_records | record | assignment terminal fact | não | assignment service |
| `SkillLeaseRecord` | phase3_records | record | exact assignment/version/task lease | não | lease service |
| `SkillLeaseTerminationRecord` | phase3_records | record | lease terminal fact | não | lease service |
| `SkillGovernanceBindingRecord` | phase3_records | record | local Governance reference/fingerprint | não | binding service |
| `SkillEvaluationBindingRecord` | phase3_records | record | local Eval reference/fingerprint | não | binding service |
| `SkillStoreWriteOutcome` | phase3_contracts | outcome | created versus replay | sim | all writers |
| `SkillStoreError` | phase3_errors | error | safe persistence base | sim | adapters/services |
| `InvalidSkillStoreRecord` | phase3_errors | error | structural invalidity | sim | constructors |
| `SkillStoreNotFound` | phase3_errors | error | exact lookup absence | sim | catalog reads |
| `SkillStoreSemanticConflict` | phase3_errors | error | conflict base | sim | write adapters |
| `SkillStoreDivergentDuplicate` | phase3_errors | error | same identity/different fact | sim | all writers |
| `SkillStoreInvalidParentReference` | phase3_errors | error | same-store parent missing/mismatch | sim | termination writes |
| `SkillStoreUnavailable` | phase3_errors | error | persistence unavailable | sim | any adapter method |
| `SkillCatalogStore` | phase3_contracts | protocol | published version catalog | sim | Slice 4/5 |
| `SkillLifecycleStore` | phase3_contracts | protocol | lifecycle fact history | sim | later lifecycle runtime |
| `SkillInstallationStore` | phase3_contracts | protocol | availability history | sim | later installation runtime |
| `SkillAssignmentStore` | phase3_contracts | protocol | assignment history | sim | later assignment runtime |
| `SkillLeaseStore` | phase3_contracts | protocol | lease history | sim | later lease runtime |
| `SkillBindingStore` | phase3_contracts | protocol | typed external bindings | sim | later binding runtime |

Methods, sem agrupamento:

| Protocol.method | Responsibility | Classification |
| --- | --- | --- |
| Catalog.`save_version` | create/replay exact published version | REQUIRED BY SLICE 5 |
| Catalog.`get_version` | exact identity lookup | REQUIRED BY SLICE 5 |
| Catalog.`list_versions` | bounded SemVer-ordered versions for SkillId | REQUIRED BY LATER RUNTIME |
| Lifecycle.`append_lifecycle` | append generic lifecycle fact | REQUIRED BY LATER RUNTIME |
| Lifecycle.`append_activation` | append typed activation fact | REQUIRED BY LATER RUNTIME |
| Lifecycle.`append_revocation` | append typed revocation fact | REQUIRED BY LATER RUNTIME |
| Lifecycle.`history` | bounded exact-version temporal history | REQUIRED BY LATER RUNTIME |
| Installation.`append_installation` | append availability fact | REQUIRED BY LATER RUNTIME |
| Installation.`append_termination` | append local terminal fact | REQUIRED BY LATER RUNTIME |
| Installation.`history` | bounded exact-version temporal history | REQUIRED BY LATER RUNTIME |
| Assignment.`append_assignment` | append exact assignment | REQUIRED BY LATER RUNTIME |
| Assignment.`append_termination` | append local terminal fact | REQUIRED BY LATER RUNTIME |
| Assignment.`history_for_subject` | bounded subject history | REQUIRED BY LATER RUNTIME |
| Lease.`append_lease` | append exact lease | REQUIRED BY LATER RUNTIME |
| Lease.`append_termination` | append local terminal fact | REQUIRED BY LATER RUNTIME |
| Lease.`history_for_agent` | bounded agent history | REQUIRED BY LATER RUNTIME |
| Lease.`history_for_task` | bounded task history | REQUIRED BY LATER RUNTIME |
| Lease.`history_for_version` | bounded exact-version history | REQUIRED BY LATER RUNTIME |
| Binding.`append_governance` | append Governance ref | REQUIRED BY LATER RUNTIME |
| Binding.`append_evaluation` | append Eval ref | REQUIRED BY LATER RUNTIME |
| Binding.`list_governance_for_version` | typed bounded Governance refs | REQUIRED BY LATER RUNTIME |
| Binding.`list_evaluations_for_version` | typed bounded Eval refs | REQUIRED BY LATER RUNTIME |

Não restou método de generic convenience, cursor, version existence, publication
duplicada, generic binding union, latest ou implementation leak.

### Necessidade objetiva dos records

| Record | Future producer | Owner | Classification | Deferred? |
| --- | --- | --- | --- | ---: |
| PublishedSkillVersionRecord | publication authority após verified snapshot | Catalog | REQUIRED FOR CONTRACT | não |
| SkillLifecycleRecord | lifecycle service | Lifecycle | REQUIRED FOR CONTRACT | não |
| SkillActivationRecord | activation service | Lifecycle | REQUIRED FOR CONTRACT | não |
| SkillRevocationRecord | revocation service | Lifecycle | REQUIRED FOR CONTRACT | não |
| SkillInstallationRecord | installation service | Installation | REQUIRED FOR CONTRACT | não |
| SkillInstallationTerminationRecord | detach/uninstall service | Installation | REQUIRED FOR CONTRACT | não |
| SkillAssignmentRecord | assignment service | Assignment | REQUIRED FOR CONTRACT | não |
| SkillAssignmentTerminationRecord | assignment service | Assignment | REQUIRED FOR CONTRACT | não |
| SkillLeaseRecord | lease service | Lease | REQUIRED FOR CONTRACT | não |
| SkillLeaseTerminationRecord | lease service | Lease | REQUIRED FOR CONTRACT | não |
| SkillGovernanceBindingRecord | local binding service | Binding | REQUIRED FOR CONTRACT | não |
| SkillEvaluationBindingRecord | local binding service | Binding | REQUIRED FOR CONTRACT | não |
| SkillPublicationRecord | nenhum após catalog correction | — | DUPLICATED SEMANTICS | removido |
| SkillContentVerificationRecord | package verifier do Slice 4 | — | FUTURE SLICE | removido |

`PublishedSkillVersionRecord` agora é a única prova de catalog membership e o único
record recuperado por exact identity. Seu `recorded_at` e actor registram o fato de
publicação; um segundo publication record criava duas authorities para existência.

Activation permanece separado porque exige uma installation reference. Revocation
permanece separado porque exige external decision reference e possui semântica de
segurança distinta. O generic lifecycle record cobre somente
deprecated/disabled/reenabled/superseded/rollback.

Termination permanece por família porque parent type e reason vocabulary diferem:
installation usa detached/uninstalled/replaced/corrupted; assignment usa
revoked/replaced/expired; lease usa expired/terminated/superseded. Um terminal record
genérico apagaria essas distinctions.

Governance/Eval records são bindings locais estreitos, não cópias das authorities
externas. Content verification foi removida porque inventory, symlink policy,
fingerprint e outcome ainda pertencem ao Slice 4.

### Semantic identity e replay

| Record | Semantic identity | Equivalent replay | Divergent duplicate |
| --- | --- | --- | --- |
| Published version | `PublishedSkillVersionId` | mesmo record profundo | mesmo exact identity, outro fact |
| Lifecycle | `lifecycle:<semantic-id>` | mesmo record profundo | mesmo ID, kind/reason/fact diferente |
| Activation | `activation:<semantic-id>` | mesmo record profundo | mesmo ID, installation/fact diferente |
| Revocation | `revocation:<semantic-id>` | mesmo record profundo | mesmo ID, decision/fact diferente |
| Installation | `installation:<semantic-id>` | mesmo record profundo | mesmo ID, source/fact diferente |
| Installation termination | `installation-end:<semantic-id>` | mesmo record profundo | mesmo ID, parent/reason/fact diferente |
| Assignment | `assignment:<semantic-id>` | mesmo record profundo | mesmo ID, subject/scope/fact diferente |
| Assignment termination | `assignment-end:<semantic-id>` | mesmo record profundo | mesmo ID, parent/reason/fact diferente |
| Lease | `lease:<semantic-id>` | mesmo record profundo | mesmo ID, assignment/task/fact diferente |
| Lease termination | `lease-end:<semantic-id>` | mesmo record profundo | mesmo ID, parent/reason/fact diferente |
| Governance binding | `governance-binding:<semantic-id>` | mesmo record profundo | mesmo ID, reference/fingerprint diferente |
| Evaluation binding | `evaluation-binding:<semantic-id>` | mesmo record profundo | mesmo ID, reference/fingerprint diferente |

Namespaces são validados pelo record. IDs iguais em maps de famílias distintas não
competem; prefixes incorretos falham antes do store. Não há database ID, UUID
aleatório, insertion order, cursor, path ou process-local identity.

Timestamps não são identidade. Eles são parte factual do record e, portanto, um
caller que alterar timestamp sob o mesmo semantic ID produz conflito legítimo. Um
replay deve reutilizar o fato temporal original; backend/adapters não geram
timestamps.

### Timestamp audit

| Field | Record | Meaning | Required | Identity? |
| --- | --- | --- | ---: | ---: |
| recorded_at | Published version | catalog/publication fact | sim | não |
| occurred_at | Lifecycle | lifecycle fact time | sim | não |
| activated_at | Activation | activation fact time | sim | não |
| revoked_at | Revocation | revocation fact time | sim | não |
| installed_at | Installation | local availability time | sim | não |
| terminated_at | Installation termination | terminal fact time | sim | não |
| assigned_at | Assignment | assignment fact time | sim | não |
| terminated_at | Assignment termination | terminal fact time | sim | não |
| granted_at | Lease | grant fact time | sim | não |
| expires_at | Lease | factual expiry boundary | sim | não |
| terminated_at | Lease termination | terminal fact time | sim | não |
| bound_at | Governance binding | correspondence fact time | sim | não |
| bound_at | Evaluation binding | correspondence fact time | sim | não |

Todos são caller-supplied, UTC-aware `datetime`, com precisão Python até
microseconds e representação futura possível em ISO-8601 UTC. Phase 3 não chama
`datetime.now()` e não serializa timestamps.

### Catalog, lifecycle e termination

Catalog membership e publication são uma authority única:
`PublishedSkillVersionRecord`. Manifest e content fingerprints permanecem dentro da
`PublishedSkillVersionId`; catalog lookup usa somente essa exact identity.

| Event | Record | Store | External decision ref? |
| --- | --- | --- | ---: |
| deprecated/disabled/reenabled | LifecycleRecord | Lifecycle | não |
| superseded/rollback | LifecycleRecord + related version | Lifecycle | não |
| activation | ActivationRecord | Lifecycle | não; installation ref estrutural |
| revocation | RevocationRecord | Lifecycle | sim |

Stores não validam transition, permission, promotion ou current state. Installation,
assignment e lease terminations apontam para parent exato, não alteram o original,
preservam history e aplicam replay/conflict por terminal semantic ID.

### Governance/Eval bindings

| Family | External authority | Local purpose | Shared methods? | Shared protocol? |
| --- | --- | --- | ---: | ---: |
| Governance | Governance | exact reference + fingerprint | não | sim |
| Evaluation | Private Evals/public boundary futuro | exact reference + fingerprint | não | sim |

O protocol compartilhado é justificado apenas pela mesma local correspondence
authority. Cada família possui append e list method próprios; nenhum método aceita
union, binding kind genérico ou payload externo.

### Content verification decision

O record e o protocol foram removidos, não apenas escondidos. O modelo anterior
pressupunha outcome, verifier semantics e content fingerprint antes de o Slice 4
definir package inventory, symlink policy, checksum e verified snapshot. Não existe
fingerprint de reference set congelado. Integrity outcome será fato técnico, nunca
trust, mas só poderá ser modelado após o Slice 4.

### Parent correspondence e atomicidade

| Child | Parent | Type structural? | Protocol precondition? | Fake only? |
| --- | --- | ---: | ---: | ---: |
| Lifecycle/revocation | exact version | sim | existence: future service | não |
| Installation | exact version | sim | existence: future service | não |
| Activation | exact version + installation ID namespace | sim | existence: future service/UoW | não |
| Installation termination | installation/version | sim | same-store parent required | não |
| Assignment | exact version | sim | existence: future service | não |
| Assignment termination | assignment/version | sim | same-store parent required | não |
| Lease | assignment/version/task | sim | assignment existence: future service | não |
| Lease termination | lease/version | sim | same-store parent required | não |
| Governance/Eval | exact version | sim | external/version existence: future service | não |

Records validam types, namespaces e embedded correspondence. Stores individuais só
validam referential existence quando possuem parent e child na mesma família
(terminations). Catalog/version, activation/installation, assignment/lease e
external binding correspondences são responsabilidade futura de application
service/adapter; nenhuma foreign key ou atomicidade global é prometida.

Não existe atomicidade cross-store. Publish+catalog, install+future verification,
activate+installation, assign+lease e coordinated external bindings poderão exigir
UnitOfWork no Slice 14. Facts independentes continuam append-only; intermediate
inconsistency deverá ser detectável/replayable. Nenhum UnitOfWork foi criado.

### Idempotency e outcomes

Todos os seis append/save families usam namespace próprio e equality estrutural
profunda. Equivalent replay retorna `IDEMPOTENT_REPLAY`, não grava outro record.
Divergent duplicate lança `SkillStoreDivergentDuplicate`, sem overwrite.

| Write method family | Identity | Equivalent | Divergent |
| --- | --- | --- | --- |
| save_version | exact PublishedSkillVersionId | replay | error |
| lifecycle/activation/revocation | family-prefixed record ID | replay | error |
| installation/termination | family-prefixed record ID | replay | error |
| assignment/termination | family-prefixed record ID | replay | error |
| lease/termination | family-prefixed record ID | replay | error |
| Governance/Eval append | distinct family-prefixed IDs | replay | error |

`SkillStoreWriteOutcome` possui somente `CREATED` e `IDEMPOTENT_REPLAY`, ambos
produzidos por todo writer. Not-found é exception somente para exact lookup.
Conflict é exception somente para divergent writes. `SkillStoreExistence` foi
removido com o convenience method que o produzia.

`SkillStoreStaleRevision` foi removido completamente: nenhum método CAS poderia
produzi-lo. CAS continua adiado.

### Query bounds e ordering

Cursor/page token foram removidos. `after_record_id` não era monotônico, não
representava SemVer nem ordem temporal e criava semântica de adapter prematura.
Queries retornam bounded tuples usando `SkillStoreQueryLimit(1..200)`.

| Query | Cardinality | Pagination now? | Primary order | Tie-breaker | Restart-stable? |
| --- | ---: | ---: | --- | --- | ---: |
| catalog versions | bounded | não | SemVer precedence | concrete version + publication identity | sim |
| lifecycle history | bounded | não | factual timestamp | semantic record ID | sim |
| installation history | bounded | não | factual timestamp | semantic record ID | sim |
| assignment subject history | bounded | não | factual timestamp | semantic record ID | sim |
| lease agent/task/version | bounded | não | factual timestamp | semantic record ID | sim |
| Governance bindings | bounded | não | bound_at | semantic record ID | sim |
| Eval bindings | bounded | não | bound_at | semantic record ID | sim |

Continuation/pagination pertence ao futuro query/adapter layer quando cardinalidade e
concurrency forem conhecidas.

### Record format e errors

`SkillStoreRecordFormatVersion` foi removido. Ele versionava um storage envelope que
não existe e antecipava serialization/migration do Slice 14. Domain records possuem
seu schema Python fechado; persistence envelope versioning será definido com o
adapter concreto.

| Error | Producer atual | Public | Needed |
| --- | --- | ---: | ---: |
| SkillStoreError | base para todos os methods | sim | sim |
| InvalidSkillStoreRecord | constructors/query limit | sim | sim |
| SkillStoreNotFound | Catalog.get_version | sim | sim |
| SkillStoreSemanticConflict | base de divergent duplicate | sim | sim |
| SkillStoreDivergentDuplicate | todos os writers | sim | sim |
| SkillStoreInvalidParentReference | same-family termination writers | sim | sim |
| SkillStoreUnavailable | qualquer future adapter method | sim | sim |
| StaleRevision | nenhum | removido | não |
| IntegrityMismatch | nenhum após adiar verification | removido | não |
| UnsupportedRecordFormat | nenhum após adiar envelope | removido | não |
| ReadOnlyViolation | nenhum protocol read-only | removido | não |

Erros preservados ignoram unsafe context e expõem mensagens fixas. Cause chains de
not-found contêm somente erros seguros.

### Public surface

O facade deixou de espelhar os módulos Phase 3. Permanecem públicos:

- seis store protocols;
- `PublishedSkillVersionRecord`;
- `SkillStoreQueryLimit`;
- `SkillStoreWriteOutcome`;
- sete errors necessários.

Lifecycle/termination/binding records, reason enums, record IDs/fingerprints e
helpers permanecem internos ao bounded context. Foram removidos todos os exports de
verification, format, page/cursor, existence e stale/integrity/read-only errors.

### Fake fidelity e organização dos testes

| Fake behavior | Required? | Extra rule? | Risk after correction |
| --- | ---: | ---: | --- |
| structural replay/conflict | sim | não | baixo |
| bounded semantic ordering | sim | não | baixo |
| local termination parent lookup | sim | não | baixo |
| cross-store parent lookup | não | removido | nenhum |
| lifecycle/current projection | não | ausente | nenhum |
| transaction/UoW | não | ausente | nenhum |
| auto-increment/cursor | não | removido | nenhum |

Fakes não consultam catalog para lifecycle/install/assignment/binding, não simulam
foreign keys globais e não são importados por production. O arquivo caiu de cerca de
855 para cerca de 680 linhas. Permanece único porque factories, six protocol fakes e
assertions formam uma conformance fixture coesa; separar agora duplicaria setup sem
criar uma authority de teste distinta.

Os oito testes cobrem: protocol shapes; catalog authority/SemVer/bounds;
lifecycle separation; three termination families; typed bindings; namespaces e
idempotency; timestamp/ordering/immutability; safe errors/removed contracts/public
surface.

### Phase 1 e boundaries

`SkillRecordStore`, runtime, models, `FileCollection` adapter, API e Commands Phase 1
continuam intocados e não importam Phase 3. Nenhum consumer produtivo foi migrado e
nenhum delete Phase 1 foi alterado.

Phase 3 importa apenas stdlib e domínio Skills. Não importa runtime, concrete
persistence, filesystem, SQLite, bootstrap, API, Tools, Sandbox, Governance runtime
ou Private Evals internals. Production não importa test fakes. Governed graph e SCC
permanecem estáveis.

### Slice boundaries corrigidos

Slice 4 é exclusivamente: raw package parsing boundary, duplicate YAML-key
rejection, package inspection, logical content inventory, path confinement, symlink
policy, per-asset checksum, content fingerprint calculation e verified content
snapshot/reference.

Não pertencem ao Slice 4: concrete store adapters, SQLite, filesystem record
persistence, migration, restart, recovery, atomicidade cross-store ou UnitOfWork.
Esses itens permanecem reservados ao Slice 14, salvo revisão formal futura.

### Correções e gates

Correções realizadas:

1. removido `SkillPublicationRecord` e seus três convenience methods;
2. removidos content verification record/protocol/outcome;
3. removidos page/cursor/existence contracts e adotados bounded tuples;
4. definido ordering distinto por query;
5. removido storage record format prematuro;
6. removidos stale/integrity/unsupported/read-only errors sem producer;
7. reduzida a facade a contracts estáveis;
8. separados os list methods Governance/Eval sem union;
9. adicionados namespaces de identidade por família;
10. removida falsa cross-store parent enforcement dos fakes;
11. preservada apenas same-store termination correspondence;
12. corrigido o plano: persistence concreta e UnitOfWork pertencem ao Slice 14.

| Gate | Corrective result |
| --- | --- |
| Phase 3 records/contracts | **PASS: 8 passed** |
| Phase 3 + Skills boundary | **PASS: 18 passed** |
| Slice 2 + Slice 3 + boundary | **PASS: 106 passed** |
| Phase 1 | **PASS: 15 passed** |
| combined Phase 1/2/3 | **PASS: 111 passed** |
| architecture complete | **PASS: 142 passed** |
| Ruff touched | **PASS** |
| Mypy Skills | **PASS: 14 source files** |
| authoritative Mypy | **baseline: 215 errors/58 files; 526 checked; zero Phase 3** |
| `git diff --check` | **PASS; line-ending warnings only; no-index PASS** |
| official graph | **70 contexts / 263 governed edges** |
| official SCC | **one inherited 13-context/35-edge SCC; Skills outside** |
| exact graph | **526 modules / 1,601 edges / 0 parse errors** |
| exact SCC | **0 non-trivial SCCs** |

Riscos residuais: bounded tuple não oferece continuation para cardinalidade alta;
record IDs precisam ser gerados por futuras application authorities; cross-store
inconsistencies não têm recovery/UoW; persistence envelope, durability e restart
permanecem indefinidos. Todos estão explicitamente fora deste slice.

Arquivos novos nesta auditoria: nenhum. Removidos: nenhum arquivo; apenas símbolos
prematuros. Alterados: quatro módulos Phase 3, facade Skills, conformance tests,
boundary tests e este documento. Concrete stores, runtime Phase 2, package
verification, execution, Sandbox, Private Evals e Slice 4 não foram iniciados. Não
houve stage, commit, push ou PR. O backend permanece **NOT READY**.

## 33. Slice 4 - parsing e verificacao local (implemented)

### Auditoria da Phase 1

| Existing mechanism | Responsibility | Reusable? | Risk | Phase 2 disposition |
| --- | --- | ---: | --- | --- |
| `load_structured_file` | YAML/JSON parsing | nao | duplicate last-write e schema permissivo | parser isolado |
| `SkillPackageManifest.from_mapping` | manifest validation | nao | coercao e estado Phase 1 | constroi `PublishedSkillManifest` |
| `Path.rglob` | directory walking | nao | links/reparse implicitos | `os.scandir`, sem seguir links |
| package checksum | digest de paths/bytes | conceito | sem inventario semantico | content fingerprint |
| script checksum | SHA-256 de script | conceito | digest sem tipo | `SkillAssetChecksum` |
| limite de 1 MB | tamanho por arquivo | conceito | incompleto e fixo | policy multidimensional |
| `_safe_child` | path relativo | parcial | nao cobre reserved names/case | policy cross-platform |
| symlink behavior | implicito | nao | pode seguir link | rejeicao explicita |
| `manifest.yaml` + `SKILL.md` | layout minimo | parcial | extras nao declarados | ambos exigidos |
| errors Phase 1 | falhas legadas | nao | detalhes locais | errors fixos e seguros |

Phase 1 permanece intacta e coexistente; runtime, install e validate nao foram
redirecionados.

### Parser e schema boundary

O input e somente `bytes`, limitado por default a 262144 bytes e decodificado como
UTF-8 estrito. Nao ha path implicito, environment, include, template expansion ou
conversao reversa. O subset YAML seguro usa `SafeLoader` e exige
`format_version: 1`.

Duplicate keys falham em qualquer mapping. Case variants permanecem distintas e
depois falham como unknown field. Keys devem ser strings. Anchors, aliases, merge
key, arbitrary/Python tags, multiplos documentos, floats e timestamps sao
proibidos. Nesting, scalar e collection possuem limites. Unknown/missing fields
falham e nao ha coercao. O schema constroi os value objects do Slice 2 e nao aceita
lifecycle, local path, trust, approval, install ou evaluation state.

### Layout, paths e arquivos

| Element | Required? | Must be declared? | Included in fingerprint? |
| --- | ---: | ---: | ---: |
| `manifest.yaml` | sim | nao, control file | nao |
| `SKILL.md` | sim | sim, `instructions` | sim |
| entrypoint/schema/docs/resource | quando usado | sim | sim |
| extra ou hidden file | proibido | n/a | n/a |

O root explicito existe, e diretorio e e resolvido uma vez. O walker e ordenado,
aceita apenas regular files e rejeita symlink, broken link, loop, directory link,
junction/reparse detectavel e hardlink quando `st_nlink > 1` e confiavel. Nenhum
arquivo e executado. Paths sao ASCII portavel com `/`, sem drive, UNC, backslash,
control/NUL, reserved Windows name, trailing dot/space ou case-fold collision.
Isso elimina tambem collisions de normalizacao Unicode.

Policy default imutavel: manifest 256 KiB; 256 files; 16 MiB/file; 64 MiB total;
depth 16; path 512 chars; 512 declarations; scalar 16 KiB; YAML depth 32; 4096
collection items; chunks 64 KiB.

### Integridade, TOCTOU e snapshot

Cada asset e aberto read-only com `O_NOFOLLOW` quando disponivel, revalidado como
regular, lido em chunks e comparado antes/depois. Seu SHA-256 lowercase usa os
bytes realmente lidos. A mitigacao nao promete seguranca kernel-level universal:
no Windows `O_NOFOLLOW` nao e equivalente ao POSIX, e reparse/hardlink detection
depende dos metadados expostos pelo host.

Content fingerprint:

`assets ordered by logical_path -> compact canonical JSON UTF-8 -> SHA-256`

A projecao inclui path, kind, role, media type, size e asset checksum; exclui root,
timestamps, inode, owner, permissions, filesystem order, machine e OS. Golden para
`SKILL.md` contendo `x`:
`cadd1f0330417567b50c79b1ebeed77c921b2a9bf18c34da66ed58c7e5758ea1`.

O snapshot frozen carrega manifest, dois fingerprints, tuple ordenada de assets,
policy version e verification metadata separada. Sua `technical_identity` usa
somente manifest/content fingerprints. Nao contem bytes, absolute path, machine
metadata, installation, trust, approval, active status ou evaluation result.

Sucesso retorna o snapshot; falha usa errors tipados e nunca partial success. O
verifier checa missing/extra asset, checksum/size, `SKILL.md`, case collisions e
expected aggregate fingerprint opcional. Nao grava stores nem muda Phase 3.

Exports minimos: `SkillVerificationPolicy`, `SkillPackageVerifier`,
`VerifiedSkillContentSnapshot`, `SkillVerificationError` e parser entrypoint.
Loader, walker e helpers permanecem internos.

Stores, SQLite, migrations, restart/recovery, UnitOfWork, publication,
installation, lifecycle, activation, revocation, resolution, Commands/Queries,
adapters, composition, execution, Sandbox e Private Evals continuam ausentes.

**Skills Runtime Phase 2 - Slice 4 implemented, module NOT IMPLEMENTED**

Corrective gate result:

| Gate | Result |
| --- | --- |
| Slice 4 | 65 passed / 1 platform skip |
| Slice 3 | 8 passed |
| Slice 2 | 88 passed |
| Phase 1 | 8 unit + 7 acceptance passed |
| integrated affected suite | 187 passed / 1 skip |
| architecture complete | 143 passed |
| Ruff | PASS |
| Mypy Skills | PASS, 18 files |
| authoritative Mypy | inherited baseline: 215 errors/58 files; 530 checked; zero Slice 4 |
| scoped git diff check | PASS |
| context graph | 70 contexts / 263 governed edges |
| official SCC | inherited 13-context/35-edge SCC; Skills outside |
| exact module graph | 530 modules / 1617 runtime edges / zero SCCs |

No stage, commit, push or PR was performed. Backend remains NOT READY.

**Skills Runtime Phase 2 - Slice 4 APPROVED, module NOT IMPLEMENTED**

## 35. Slice 5 - publication service e version catalog runtime

Status: implemented. O backend permanece NOT READY.

### Auditoria e authority map

| Existing symbol | Responsibility | Slice 5 use | Risk/disposition |
| --- | --- | ---: | --- |
| PublishedSkillVersionId | identidade exata composta | sim | derivada somente do snapshot |
| PublishedSkillManifest | declaracao imutavel | sim | nunca reconstruida de raw input |
| VerifiedSkillContentSnapshot | prova tecnica Slice 4 | sim | invariantes validadas, sem filesystem |
| PublishedSkillVersionRecord | membership + publication fact | sim | ampliado com publication/idempotency refs |
| SkillCatalogStore | create-only catalog port | sim | unica fronteira de write/query |
| SkillStoreWriteOutcome | store-level result | interno | traduzido para result application-level |
| SkillStoreQueryLimit | bound 1..200 | sim | preservado |
| errors Phase 2/3/4 | domain/store/verification failures | sim, por boundary | store errors traduzidos |

| Concern | Authority | Input | Output |
| --- | --- | --- | --- |
| request validation | PublishVerifiedSkillVersionRequest | snapshot + refs + UTC time | frozen request |
| publication identity | SkillPublicationService | snapshot | PublishedSkillVersionId |
| correspondence | service private validator | snapshot invariants | valid identity/error |
| record construction | service | request + identity | PublishedSkillVersionRecord |
| catalog write | SkillCatalogStore | record | store outcome |
| publication result | service | persisted record/outcome | SkillPublicationResult |
| exact lookup/list | service + port | exact ID/SkillId+limit | typed record tuple |
| idempotency/conflict | record equality + store | same exact ID | replay or conflict |

### Request, record e identidade

`PublishVerifiedSkillVersionRequest` contem somente frozen snapshot, actor ref,
publication ref, idempotency ref e caller-supplied UTC publication timestamp.
Governance decision ref foi reservado: ainda nao existe binding/decision authority
neste slice. Nao ha path, YAML, bytes, metadata dict, status, trust ou approval.

O caller nao fornece PublishedSkillVersionId. O service deriva:

`manifest.skill_id + manifest.version + manifest fingerprint + content fingerprint`

e confirma manifest fingerprint, aggregate asset fingerprint, technical identity,
policy version e verification metadata. Nao reabre package, nao recalcula asset
checksums e nao aplica TTL. Verification age e observation factual; freshness
pertence a policy futura.

| PublishedSkillVersionRecord field | Source | Required | Mutable | Identity |
| --- | --- | ---: | ---: | ---: |
| identity | snapshot | sim | nao | sim |
| manifest | snapshot | sim | nao | coberto por identity |
| recorded_at | request/caller | sim | nao | publication fact |
| actor_ref | request | sim | nao | publication fact |
| publication_ref | request | sim | nao | publication fact |
| idempotency_ref | request | sim | nao | replay fact |

O exact PublishedSkillVersionId e tambem o semantic catalog key; nenhum UUID,
timestamp-derived ID ou segundo publication record foi criado. Provenance e
validada apenas estruturalmente pelo manifest e refs; nao ha signature, publisher
identity proof, approval ou trust grant.

### Service, idempotencia e queries

`SkillPublicationService.publish` valida request/snapshot, constroi o unico record,
chama `save_version`, traduz outcome e, no replay, recupera e retorna o record
existente. First write retorna CREATED. Mesmo record retorna IDEMPOTENT_REPLAY.
Mesmo exact ID com timestamp, actor, publication ref ou idempotency ref divergente
retorna `SkillPublicationConflict`; nada e sobrescrito. O service nunca chama
`datetime.now`, portanto retry nao inventa novo fato temporal.

Foi escolhida a opcao A: nenhum InMemorySkillCatalogStore produtivo. Testes possuem
um fake estrito com apenas save_version/get_version/list_versions.

Catalog membership existe somente quando ha PublishedSkillVersionRecord no store.
Snapshot, manifest, package Phase 1 ou installation isolados nao conferem membership.
`get_exact` exige PublishedSkillVersionId completo. `list_versions` exige SkillId e
SkillStoreQueryLimit, retorna tuple ascending por SemVer precedence, concrete
version text e exact publication identity. Prerelease precede release; build
metadata nao altera precedence, apenas desempata estruturalmente. Nao existem
latest, highest, wildcard, compatible, preferred, fallback, fuzzy ou free-text.

Store divergent duplicate vira application publication conflict; unavailable e
not-found possuem errors application-level fixos. Nenhum path, manifest, asset ou
payload entra nas mensagens.

### Separacao e superficie

Public exports: request, result, outcome, service e errors application-level
estaveis. Store outcomes, ordering helper, validators e fake nao sao exportados.
Commands globais, handlers, API, Composition Root e events foram reservados. Nao
ha event consumer aprovado, portanto publication nao publica evento nem inicia
pipeline.

Publication termina no catalogo. Nao instala, ativa, revoga, avalia, cria binding,
aprova, concede trust/lease, resolve dependency ou executa Skill. Phase 1 permanece
intacta. Persistence, SQLite, migration, restart, recovery e UnitOfWork continuam
ausentes.

**Skills Runtime Phase 2 - Slice 5 implemented, module NOT IMPLEMENTED**

Slice 5 gates: 21 publication tests passed; Slice 4 65 passed/1 platform skip;
Slice 3 8 passed; Slice 2 88 passed; Phase 1 15 passed; architecture 144 passed;
Ruff PASS; Mypy Skills PASS for 21 source files; authoritative Mypy preserves the
inherited 215 errors/58 files baseline across 533 checked files, with zero Slice 5
errors; diff check PASS with pre-existing line-ending warnings; governed graph
70 contexts/263 edges; inherited official SCC 13 contexts/35 internal edges with
Skills outside; exact graph 533 modules/1633 runtime edges/zero non-trivial SCCs.

Search review found no latest/highest/wildcard/fallback, progression method,
filesystem/YAML, datetime.now, UUID, subprocess/importlib, delete/overwrite/upsert
or event publication in Phase 5. Matches for `path` are local variable names for
logical content correspondence, not filesystem paths.

No stage, commit, push or PR was performed. Backend remains NOT READY.

**Skills Runtime Phase 2 - Slice 5 implemented, module NOT IMPLEMENTED**

## 34. Auditoria corretiva de seguranca do Slice 4

Veredito desta secao: a implementacao inicial exigia correcao. O token stream era
materializado integralmente e os limites estruturais eram aplicados somente depois
de `compose_all`; nao havia reinventario final; a facade exportava o parser de
baixo nivel; e a cobertura portavel de case collision dependia do host. Esses
pontos foram corrigidos antes da aprovacao.

### Inventario de authorities

| Symbol | File | Responsibility | Public? | Security-critical? |
| --- | --- | --- | ---: | ---: |
| `SkillVerificationPolicyVersion` | phase4_models | versao fechada da policy | nao | sim |
| `SkillVerificationPolicy` | phase4_models | bounds imutaveis | sim | sim |
| `parse_published_skill_manifest` | phase4_parser | bytes para dominio | modulo somente | sim |
| `_preflight_yaml`, `_node_value` | phase4_parser | tokens/nodes seguros | nao | sim |
| `_fields`, `_content`, `_provenance` | phase4_parser | raw schema; nenhum DTO retido | nao | sim |
| `SkillPackageVerifier` | phase4_verification | verificacao local read-only | sim | sim |
| `_FileFact`, `_inventory` | phase4_verification | inventario factual transiente | nao | sim |
| `_validate_portable_path`, `_add_unique_portable_path` | phase4_verification | path/collision | nao | sim |
| `_read`, `_hash_file` | phase4_verification | FD, size e SHA-256 | nao | sim |
| `_is_reparse` | phase4_verification | classifier Windows | nao | sim |
| `SkillAssetChecksum` | phase4_models | digest individual | nao | sim |
| `VerifiedSkillAsset` | phase4_models | asset sem payload/path local | nao | sim |
| `SkillVerificationMetadata` | phase4_models | observation factual | nao | nao |
| `VerifiedSkillContentSnapshot` | phase4_models | prova imutavel | sim | sim |
| `content_fingerprint` | phase4_models | aggregate canonical | nao | sim |
| `SkillVerificationError` e subclasses | phase4_errors | falhas fixas | base publica | sim |

Nao existem raw DTOs, custom YAML loader ou custom constructors. Raw mappings e
tuples existem apenas durante a chamada e nao atravessam a boundary.

### Fluxo e momento dos limites

| Stage | Input | Output | Limit before costly allocation? | Failure |
| --- | --- | --- | ---: | --- |
| bytes/encoding | bytes | UTF-8 text | bytes antes de decode | invalid/limit |
| token preflight | text | validacao streaming | sim: tokens, scalar, depth | unsafe/unsupported/limit |
| composition | preflighted text | one Node tree | sim, bounded token stream | invalid/unsupported |
| node conversion | Node | typed raw tuple/mapping | depth/items/scalar durante walk | invalid/limit/duplicate |
| schema/domain | raw values | PublishedSkillManifest | declarations antes do dominio | field/invalid |
| root/inventory | explicit Path | sorted FileFacts | count/size/depth/path durante walk | root/path/link/type/limit |
| reads | FileFact | bytes somente para manifest; digest para asset | chunk/maximum durante read | type/change/limit |
| correspondence | manifest + facts | ordered assets | n/a | missing/extra/checksum |
| fingerprint | small verified inventory | SHA-256 | declarations/files ja bounded | correspondence |
| final observation | initial inventory | re-inventory + manifest reread | mesmos bounds | changed |
| snapshot | domain + assets | frozen snapshot | n/a | correspondence |

O raw manifest precisa existir como `bytes` fornecidos pelo caller; isso e o input
autorizado. O decode cria no maximo 1 MiB se a policy for elevada ao bound maximo.
O preflight itera o scanner sem criar tuple de tokens. Anchors, aliases e tags
falham nessa etapa, antes de composition e portanto antes de alias expansion.
Mapping/sequence total e validado durante a conversao da arvore ja preflighted.

### SafeLoader e scalar policy

Usa-se `yaml.scan(..., Loader=yaml.SafeLoader)` e
`yaml.compose_all(..., Loader=yaml.SafeLoader)`. Nao ha `yaml.load`, FullLoader,
UnsafeLoader, constructor ou resolver customizado. Tags explicitas sao proibidas.
Somente tags core `str`, decimal `int`, lowercase `true|false` e `null` sao
convertidas. Float, timestamp, binary, hexadecimal, octal, scientific notation,
`yes/no/on/off`, infinity e NaN falham. Assim, resolucao YAML 1.1 eventualmente
feita pelo SafeLoader nunca vira coercao aceita pelo dominio.

| Raw YAML | Result | Accepted? |
| --- | --- | ---: |
| `text` / quoted text | string | sim |
| `123` | int decimal | sim |
| `true`, `false` | bool | sim |
| `null` | null | sim |
| `1.5`, `1e3`, `.inf`, `.nan` | non-approved tag/text | nao |
| date/timestamp | timestamp tag | nao |
| `!!binary` | explicit tag | nao |
| `0x10`, `0o10` | non-decimal integer form | nao |
| `yes/no/on/off` | ambiguous YAML 1.1 scalar | nao |

Anchor sem alias, multiplos anchors, alias simples/aninhado/recursivo, expansion
reduzida, merge simples/sequence e duplicate via merge sao todos rejeitados no
token preflight. Duplicate key literal e rejeitada em qualquer MappingNode.
Non-string keys falham antes da comparacao; `"true"` e `"1"` sao strings, enquanto
keys plain `true` e `1` falham como non-string. Case variants sao distintas e
depois falham pelo schema quando desconhecidas. Unicode textual e permitido, mas
logical paths permanecem ASCII.

### Raw schema

| Field | Raw type | Required | Default | Nested unknown rejected |
| --- | --- | ---: | --- | ---: |
| format_version | decimal int, bool proibido | sim | nenhum | n/a |
| skill_id/version/display_name/summary/description | string | sim | nenhum | n/a |
| provenance | mapping | sim | optional refs = null | sim |
| scopes | sequence de string enum | sim | nenhum | n/a |
| content | sequence de mapping | sim | nenhum | sim |
| content.logical_path/fingerprint/kind/media_type/size_bytes | tipos exatos | sim | nenhum | sim |
| content.role | string/null | nao | null | sim |
| compatibility/security | empty mapping neste formato | nao | domain defaults | sim |

O formato raw e deliberadamente menor que todo o modelo do Slice 2. Dependencies,
execution e demais declaracoes nao sao silenciosamente ignoradas: sao unknown e
falham. Uma futura ampliacao exige versionamento/revisao de schema. Duplicate
logical path e rejeitada pelo dominio; case-fold duplicate, pelo verifier. Nenhum
mapping, list, bytes, local path ou `Any` fica armazenado.

### Identidade, layout e paths

`PublishedSkillVersionId` combina SkillId, SkillVersion, manifest fingerprint e
content fingerprint. `manifest.yaml` nao entra no content fingerprint para evitar
auto-referencia circular, mas suas declaracoes entram no manifest fingerprint.
Comentario/ordem YAML semanticamente equivalentes produzem o mesmo manifest
fingerprint. Build metadata de SemVer participa da versao. Mudanca de asset exige
novo checksum declarado; se o manifest nao mudar, verification falha.

| Category | Declared | Content fingerprint | Undeclared allowed |
| --- | ---: | ---: | ---: |
| manifest.yaml | nao | nao | unica excecao |
| SKILL.md | sim como instructions | sim | nao |
| docs/schema/resource/entrypoint | sim | sim | nao |
| hidden/temp/backup/OS metadata/nested manifest | sim ou rejeitado | se declarado | nao |
| empty directory | nao | nao | sim, sem semantica |

Logical paths permitem apenas printable ASCII, `/` e segmentos seguros. Absolute
POSIX, drive absolute/relative, UNC, extended/device path, ADS, backslash/mixed
separator, repeated separator, dot segment, reserved name, trailing dot/space,
control/NUL, Unicode homoglyph/normalization e case-fold collision falham da mesma
forma em Windows e Linux. Unicode continua permitido em display/summary/description;
semantic refs e media types seguem seus value objects. `ensure_ascii=False` e
deterministico porque canonical JSON e UTF-8 explicito.

### Links, descriptors e mutation guarantee

| Link | Detection | Platform | Guaranteed |
| --- | --- | --- | ---: |
| file/directory/broken/loop symlink | DirEntry.is_symlink + lstat | POSIX/Windows quando exposto | sim quando OS reporta |
| junction/reparse/mount reparse | FILE_ATTRIBUTE_REPARSE_POINT | Windows | quando atributo exposto |
| hardlink | `st_nlink > 1` | quando stat confiavel | nao universal |

Hardlinks nao possuem promessa universal. Quando o host reporta `st_nlink > 1`,
o candidate falha; caso contrario, o hash ainda cobre os bytes lidos e identidade
nao usa inode. O risco concorrente residual permanece documentado.

O fluxo e lstat no inventory, `os.open` read-only com `O_NOFOLLOW` quando existe,
`fstat`, chunk reads no mesmo descriptor, `fstat` final e close. Size real e
contado. Size/mtime e, quando significativos, device/inode sao comparados. Depois
de todos os assets, ha re-inventory completo e releitura do manifest. Add/remove/
rename/replace normalmente falha por paths ou metadata divergentes. Isto e
best-effort, nao snapshot atomico: uma mutacao que restaure bytes e todos os
metadados observados entre checks pode escapar sem primitive do kernel.

O unico skip restante e criacao real de symlink quando o host nega essa feature.
A classificacao de reparse possui teste unitario independente da plataforma, a
policy runtime continua fail-closed quando o OS reporta o link e nao ha promessa
universal sobre metadata que o OS nao exponha.

### Resource policy e allocation safety

| Limit | Default | Min | Max | Applied |
| --- | ---: | ---: | ---: | --- |
| manifest bytes | 262144 | 1 | 1048576 | before decode/read |
| YAML tokens | 16384 | 1 | 131072 | streaming scan |
| scalar chars | 16384 | 1 | 65536 | token + node |
| collection items | 4096 | 1 | 65536 | node walk |
| YAML depth | 32 | 1 | 64 | token + node |
| files | 256 | 1 | 4096 | inventory |
| bytes/file | 16777216 | 1 | 268435456 | stat + read |
| total bytes | 67108864 | 1 | 1073741824 | inventory |
| package depth | 16 | 1 | 64 | inventory |
| logical path | 512 | 1 | 1024 | inventory/declaration |
| declarations | 512 | 1 | 4096 | schema |
| chunk | 65536 | 1 | 1048576 | descriptor read |

Zero, negative, bool e acima do maximo falham como
`InvalidSkillVerificationPolicy`; file max nao pode exceder total max. Nenhum size
declarado prealoca buffer: assets sao streamed e somente o manifest bounded e
retido transientemente. Python integers evitam overflow, mas policy bounds tambem
limitam soma, recursion e collection growth.

### Checksums, projection e metadata

Asset SHA-256 e lowercase, sempre recomputado dos bytes reais, incluindo empty,
binary e large files. `SkillAssetChecksum`, `SkillContentFingerprint` e
`SkillManifestFingerprint` nao sao intercambiaveis.

| Projection field | Included | Reason |
| --- | ---: | --- |
| logical_path | sim | identidade/localizacao semantica |
| kind | sim | funcao do asset |
| role | sim | papel declarado |
| media_type | sim | interpretacao semantica |
| size_bytes | sim | integridade estrutural |
| checksum_sha256 | sim | bytes |
| root/time/inode/device/owner/permission/platform | nao | incidental/local |

Assets sao ordenados por logical path e serializados como compact JSON com
sort_keys, UTF-8, `ensure_ascii=False` e NaN proibido. Golden vectors:

- minimo `SKILL.md = b"x"`:
  `cadd1f0330417567b50c79b1ebeed77c921b2a9bf18c34da66ed58c7e5758ea1`;
- SKILL.md textual + binary:
  `5fbc7bd02e4ffc84d3c8a4773829def415820ed41839f64e5e4372c19b05f9de`;
- SKILL.md vazio + resource vazio:
  `e4f1570182d2a22999af05da67bcbbb1263fd82e52ef8bc58984cd96323d9f6b`.

Verification metadata contem UTC timestamp, semantic verifier ref e version. E
factual, frozen e segura; nao contem host, user ou path. Timestamp/verifier nao
participam de `technical_identity`. Policy version e separada dos fingerprints.
Nao foi necessario fragmentar o snapshot: identity e observation ja possuem
campos e propriedade distintos.

### Errors, exports e cobertura

Todos os errors possuem mensagem fixa sem raw YAML, asset name ou full path.
YAMLError/OSError sao suprimidos com `from None`. Cada error tem producer real;
`InvalidSkillVerificationPolicy` separa configuracao invalida de correspondence.

Facade final exporta somente policy, stable verifier service, snapshot e base
error. Parser, policy version, asset/checksum/metadata records, filesystem facts,
walker e helpers ficam nos modulos internos.

Cobertura corretiva inclui positive/boundary/adversarial cases para raw bytes,
UTF-8, tokens/features YAML, duplicates, scalar semantics, schema, limits, layout,
portable paths/collisions, reparse/symlink, deterministic TOCTOU mutations,
checksums, tres goldens, identity, immutability, safe errors, exports e Phase 1.
Os casos parametrizados sao reportados como casos efetivos, nao inflados como
funcoes separadas.

Phase 1 permanece intacta e nao importa Phase 4 automaticamente. Nao houve seed,
data migration ou alteracao incidental de install/validate/runtime. O verifier
somente produz prova tecnica local; nao publica, grava catalog, instala, confia,
avalia, aprova, ativa, persiste, recupera ou executa.

**Skills Runtime Phase 2 - Slice 4 security audit complete, module NOT IMPLEMENTED**

**Skills Runtime Phase 2 — Slice 3 APPROVED, module NOT IMPLEMENTED**

Current status supersedes the historical line above:

**Skills Runtime Phase 2 - Slice 4 implemented, module NOT IMPLEMENTED**

Corrective audit gates: Slice 4 65 passed/1 platform skip; Slice 3 8 passed;
Slice 2 88 passed; Phase 1 8 unit + 7 acceptance passed; integrated affected
suite 187 passed/1 skip; architecture 143 passed; Ruff PASS; Mypy Skills PASS
for 18 files; authoritative Mypy inherited baseline 215 errors/58 files with
530 checked and zero Slice 4 errors; scoped diff check PASS; graph 70 contexts
and 263 governed edges; inherited official SCC 13 contexts/35 internal edges
with Skills outside; exact graph 530 modules/1617 runtime edges/zero SCCs.

No stage, commit, push or PR was performed. Backend remains NOT READY.

**Skills Runtime Phase 2 - Slice 4 APPROVED, module NOT IMPLEMENTED**

The Slice 5 section and gates above supersede this historical Slice 4 footer.

**Skills Runtime Phase 2 - Slice 5 implemented, module NOT IMPLEMENTED**

## 36. Auditoria corretiva do Slice 5

### Tres identidades e membership

| Identity | Owner | Lifetime | Persisted in catalog record | Reason |
| --- | --- | --- | ---: | --- |
| published version: PublishedSkillVersionId | immutable version domain | permanente | sim | SkillId/version + manifest/content fingerprints |
| publication fact | catalog membership authority | permanente | sim, campos do record inicial | primeira entrada no catalogo |
| request idempotency ref | application request | request/retry | nao | correlation de tentativa, nao fato publicado |

Essas identidades nao sao fundidas. `idempotency_ref` foi removido de
PublishedSkillVersionRecord e permanece somente no request. Sem idempotency
envelope/store aprovado, o service nao promete deduplicacao global por essa key;
ele oferece semantic idempotency pela versao publicada. Um envelope/audit de
tentativas futuras pertence a outro slice.

PublishedSkillVersionRecord e a unica authority de membership:

| Field | Meaning | Identity | Replay relevant | Request scoped |
| --- | --- | ---: | ---: | ---: |
| identity | immutable published version | sim | sim | nao |
| manifest | declaration covered by identity | sim, por fingerprint | sim | nao |
| recorded_at | first successful catalog publication time | nao | retornado do existing | nao |
| actor_ref | actor efetivo da primeira publication | nao | retornado do existing | nao |
| publication_ref | semantic ref do fato inicial | nao | retornado do existing | nao |

Verification policy/metadata ficam no snapshot e nao sao persistidas no catalog
record. Provenance permanece no manifest. `manifest.provenance.publication_ref`
e publisher-declared lineage; record `publication_ref` referencia o fato local de
entrada no catalogo. Nao precisam coincidir e nenhuma prova de trust/identity
externa e realizada.

Uma published structural version existe uma unica vez por `(SkillId,
SkillVersion)`. Nao ha publication record paralelo. Snapshot, package,
installation ou active state nao criam membership. Republicar a mesma exact
identity por outro actor/request e semantic replay do fato inicial, nao novo audit
fact. Tentativas futuras podem ir para audit authority ainda nao criada.

### Idempotencia, equality e ambiguous writes

| Scenario | Result corrigido |
| --- | --- |
| mesma request integral | IDEMPOTENT_REPLAY, existing record |
| mesma request key, novo timestamp/actor | semantic replay, existing initial fact |
| request key diferente, mesma exact version | semantic replay, existing initial fact |
| mesmo SkillId/version, fingerprints diferentes | conflict |
| lost response apos write | retry reconcilia por save replay/get exact |
| duas equivalentes concorrentes | uma create; outra replay conforme store atomicity |
| duas divergentes concorrentes | uma create; outra divergent duplicate |
| process restart | depende de futuro durable adapter; exact lookup e semantica estao definidas |

Request equality inclui todos os request fields. Dataclass record equality inclui
o publication fact inicial completo. Publication equivalence e mais estreita:
mesma PublishedSkillVersionId e mesmo manifest. Portanto timestamp, actor,
publication ref e request idempotency divergentes em retry nao criam conflito
artificial nem substituem o fato inicial. Divergent fingerprint para a mesma
structural version e conflito semantico real.

O timestamp e UTC-aware, caller-supplied e nao canonicalizado alem da validacao UTC.
Ele participa da igualdade estrutural do record inicial, mas nao da equivalencia
de replay. Se a resposta foi perdida e o retry usa novo timestamp, o service
retorna `recorded_at` original do store. Nao existe `datetime.now` no service.

`SkillCatalogStore.save_version` agora documenta oficialmente:

- unique key `(SkillId, SkillVersion)`;
- exact identity equivalente => IDEMPOTENT_REPLAY;
- fingerprints divergentes na mesma structural version =>
  SkillStoreDivergentDuplicate;
- nenhuma sobrescrita.

O replay sempre executa `get_version` e retorna a authority existente. O service
nao retorna o record candidato divergente. Nao ha transacao, recovery ou
exactly-once claim. Ambiguous write e reconciliado por retry/exact lookup; um
durable restart depende de adapter futuro.

### Version invariant e ordering

Build metadata faz parte da representacao estrutural de SkillVersion. Assim,
`1.0.0+build.1` e `1.0.0+build.2` podem coexistir, possuem mesma SemVer precedence
e sao ordenadas apenas por tie-break textual deterministico; isso nao afirma que
uma build seja semanticamente superior. Para uma mesma SkillVersion estrutural,
qualquer manifest/content fingerprint divergente e proibido e exige nova
SkillVersion.

Listing continua ascending por precedence, concrete version text e exact identity.
Nao existe latest/highest/preferred/wildcard/fallback. PublicationService mantem
publish, get_exact e list_versions porque todos sao uma facade estreita sobre o
mesmo catalog port neste slice; separar query service nao criaria nova authority.
Commands/Queries globais continuam reservados.

### Correspondence, errors, exports e progression

O service checa: snapshot types; policy/verification metadata invariants; manifest
fingerprint; technical identity; content fingerprint da projection; paths e todos
os campos declarados versus verified assets; SkillId/version/fingerprints da
PublishedSkillVersionId derivada. Nao inventaria package, nao recalcula asset
hash, nao abre filesystem, nao parseia YAML, nao decide freshness/trust/approval.

Errors application-level possuem producers reais e mensagens fixas: invalid
request, snapshot mismatch, publication conflict, catalog unavailable e exact
not found. Store causes sao typed e nao carregam payload.

Exports permanecem request/result/outcome/service e errors estaveis. Ordering,
correspondence validator, fake e request-idempotency implementation details nao
sao exportados separadamente. O fake implementa somente os tres protocol methods,
usa a mesma structural-version uniqueness, retorna existing em replay, nunca
overwrite e nao e importado por production.

Publish nao chama lifecycle, installation, binding, verifier, parser, filesystem,
Governance, Intelligence, Private Evals, Sandbox ou Tools. A operacao termina no
catalogo.

**Skills Runtime Phase 2 - Slice 5 corrective audit complete, module NOT IMPLEMENTED**

Corrective gates: Slice 5 23 passed; Slice 4 65 passed/1 platform skip; Slice 3
8 passed; Slice 2 88 passed; Phase 1 15 passed; architecture 144 passed; Ruff
PASS; Mypy Skills PASS for 21 files; authoritative Mypy inherited baseline 215
errors/58 files with 533 checked and zero Slice 5 errors; diff check PASS with
pre-existing line-ending warnings; governed graph 70 contexts/263 edges; inherited
official SCC 13 contexts/35 internal edges with Skills outside; exact graph 533
modules/1633 runtime edges/zero non-trivial SCCs.

No stage, commit, push or PR was performed. Backend remains NOT READY.

**Skills Runtime Phase 2 - Slice 5 APPROVED, module NOT IMPLEMENTED**

## 37. Slice 6 - lifecycle service, activation state and revocation

Date: **2026-07-27**

### Existing-symbol audit

| Existing symbol | Responsibility before Slice 6 | Used by Slice 6? | Risk/decision |
| --- | --- | ---: | --- |
| `SkillLifecycleRecord` | generic append-only lifecycle fact | yes | extended only with optional event/decision refs; no state stored |
| `SkillActivationRecord` | activation fact linked to exact installation ID | yes | link remains mandatory; Slice 6 does not invent or validate the installation parent |
| `SkillRevocationRecord` | terminal security fact and decision ref | yes | extended with event/evidence refs; no external payload |
| `SkillLifecycleKind` | closed kinds for generic lifecycle facts | yes | added explicit `DEACTIVATED`; legacy `DISABLED` remains replay-compatible |
| `SkillLifecycleReason` | closed reason vocabulary | yes | reused unchanged |
| `SkillLifecycleStore` | append/history port without transition authority | yes | protocol unchanged; state machine remains in service |
| `PublishedSkillVersionRecord` | unique catalog-membership authority | yes | exact lookup is the prerequisite for every operation/query |
| `SkillCatalogStore` | exact published-version catalog | yes | lookup only; no latest/fallback/list selection |
| Phase 1 status mutation | legacy manifest rewrite and active-version side effects | no | deliberately untouched; no consumer migration |

### Authority map

| Concern | Authority | Input | Output |
| --- | --- | --- | --- |
| current lifecycle projection | pure `project_skill_lifecycle` | publication + canonical history | immutable projection |
| transition validation | `SkillLifecycleService` via replay | current history + candidate | legal projection or typed error |
| event identity | internal event-ID factory | family + semantic event ref | deterministic namespaced record ID |
| event construction | `SkillLifecycleService` | typed request | typed Phase 3 record |
| append | `SkillLifecycleStore` | constructed record | created/replay |
| replay | service + store equality | record ID + structural record | existing typed result |
| conflict | service | same ID, divergent record | `SkillLifecycleConflict` |
| activation/deactivation | service | exact request | activation/lifecycle record |
| deprecation/re-enable | service | exact request | lifecycle record |
| supersession/rollback | service | source + exact target | reference lifecycle record |
| revocation | service | exact request + decision ref | terminal revocation record |
| history query | service over lifecycle port | exact published identity | timestamp/ID ordered tuple |

The store does not expose state-machine, transition, latest, delete, overwrite, or
projection behavior.

### Derived states

| State | Meaning | Terminal? | Can resolve? | Can activate? |
| --- | --- | ---: | ---: | ---: |
| `PUBLISHED` | catalog member with no lifecycle fact | no | yes | yes, with installation ref |
| `ACTIVE` | an activation fact is currently effective | no | yes | no, already active |
| `INACTIVE` | activation was explicitly deactivated | no | yes | yes, with installation ref |
| `DEPRECATED` | discouraged for new default selection; prior active fact is retained | no | yes, explicitly | no until re-enabled |
| `SUPERSEDED` | replaced or source of a rollback reference | no for revocation; closed for activation | no | no |
| `REVOKED` | externally decided terminal prohibition | yes | no | no |

Active, deprecated, revoked and superseded are also explicit orthogonal projection
facts. Re-enabling restores the state that existed immediately before deprecation;
it creates no activation. A deprecated active version therefore remains factually
active but is not active-selection eligible.

### Events versus states and transition matrix

Publication is the initial catalog fact, not a lifecycle-store event.

| Event | Resulting projection | Reversible? | External ref required? |
| --- | --- | ---: | ---: |
| publish | `PUBLISHED` | no | publication ref belongs to catalog record |
| activate | `ACTIVE` | yes, by deactivate | installation ID required; decision optional |
| deactivate | `INACTIVE` | yes, by a new activation | no |
| deprecate | `DEPRECATED` | yes, by re-enable | no |
| re-enable | prior `PUBLISHED`/`ACTIVE`/`INACTIVE` | n/a | no |
| supersede | `SUPERSEDED` + exact replacement | no automatic reversal | no |
| rollback | source `SUPERSEDED` + exact target/ref | history is never undone | decision ref yes |
| revoke | `REVOKED` | no | decision ref yes; evidence optional |

| From | Event | To | Allowed? | Required references |
| --- | --- | --- | ---: | --- |
| `PUBLISHED` | activate | `ACTIVE` | yes | installation ID |
| `PUBLISHED` | deprecate | `DEPRECATED` | yes | none |
| `PUBLISHED` | supersede | `SUPERSEDED` | yes | exact published replacement |
| `PUBLISHED` | rollback | `SUPERSEDED` | yes | exact target + decision |
| `PUBLISHED` | revoke | `REVOKED` | yes | decision |
| `ACTIVE` | deactivate | `INACTIVE` | yes | none |
| `ACTIVE` | deprecate | `DEPRECATED` | yes | none |
| `ACTIVE` | supersede/rollback | `SUPERSEDED` | yes | exact target; rollback decision |
| `ACTIVE` | revoke | `REVOKED` | yes | decision |
| `INACTIVE` | activate | `ACTIVE` | yes | installation ID |
| `INACTIVE` | deprecate | `DEPRECATED` | yes | none |
| `INACTIVE` | supersede/rollback | `SUPERSEDED` | yes | exact target; rollback decision |
| `INACTIVE` | revoke | `REVOKED` | yes | decision |
| `DEPRECATED` | re-enable | prior state | yes | none |
| `DEPRECATED` | supersede/rollback | `SUPERSEDED` | yes | exact target; rollback decision |
| `DEPRECATED` | revoke | `REVOKED` | yes | decision |
| `SUPERSEDED` | rollback target selection | same source state | only one rollback fact | exact target + decision |
| `SUPERSEDED` | revoke | `REVOKED` | yes | decision |
| `REVOKED` | any lifecycle event | `REVOKED` | no | terminal |

All unlisted transitions fail. Repeated semantic transitions under a different event
ID fail rather than silently creating history spam.

### Publication, ordering and event identity

Every command and query starts with `SkillCatalogStore.get_version` for the exact
`PublishedSkillVersionId`. A snapshot, manifest, package or installation alone does
not prove publication. Missing target/source membership fails before append.

Canonical order is factual UTC timestamp and then `SkillStoreRecordId`. Store
insertion order has no meaning. Histories returned out of order are sorted before
replay. Equal timestamps are deterministic. A new event earlier than the maximum
existing factual timestamp is rejected as backdated. Caller-supplied timestamps are
accepted only when UTC-aware. This slice has no privileged backfill authority.
Clock skew is therefore surfaced as a rejected transition instead of rewriting past
projection.

The inherited history port is bounded at 200 facts and has no page cursor. To avoid
silently projecting a truncated stream, a full 200-record response is rejected as
ambiguous/inconsistent until a future paged durable adapter contract is approved.

| Record | Semantic identity components |
| --- | --- |
| lifecycle | `lifecycle:` + SHA-256 of semantic event reference |
| activation | `activation:` + SHA-256 of semantic event reference |
| revocation | `revocation:` + SHA-256 of semantic event reference |

Timestamp is factual content, not the sole identity. IDs contain no UUID, path,
process state or insertion counter.

### Requests, activation and lifecycle semantics

Seven frozen narrow request types exist: activate, deactivate, deprecate, re-enable,
supersede, rollback and revoke. They share exact identity, actor, closed reason,
UTC occurrence time, semantic event ref and optional decision ref. Target-bearing
requests use exact `PublishedSkillVersionId`, never a constraint or `latest`.

Activation produces `SkillActivationRecord` only when lifecycle-eligible and requires
the caller to supply an exact `installation:` record ID. This is a structural
reference, not proof of local availability. Slice 6 neither creates nor reads an
installation and makes no claim that activation is executable. Parent validation
and coordinated operational activation remain Slice 7/its later atomicity design.

Deactivation is an explicit append-only fact; it never removes the activation.
Deprecation preserves availability/history and is distinct from revocation.
Re-enable removes only the projected deprecation effect and never implies a new
activation.

Supersession requires both exact versions published, the same `SkillId`, distinct
identities and a non-revoked replacement. Lower SemVer is permitted because no
version-order policy authority exists. Rollback has the same exact target checks,
requires a decision ref, preserves both histories and records only eligibility/
reference intent. It does not deploy, install or activate the target. A deprecated
target is permitted only because rollback already carries an explicit decision ref.

Revocation requires exact publication, actor/reason/time and decision ref. Evidence
is an optional semantic reference. It stores no evidence payload, performs no trust
inference, deletes nothing, and terminally blocks resolution/activation.

### External references

| Operation | Governance ref | Intelligence ref | Evidence ref | Required now? |
| --- | ---: | ---: | ---: | ---: |
| activate/deactivate | optional semantic decision | no | no | installation ID only for activate |
| deprecate/re-enable | optional semantic decision | no | no | no |
| supersede | optional semantic decision | no | no | exact replacement |
| rollback | semantic decision (authority-neutral type) | no | no | yes |
| revoke | semantic decision (authority-neutral type) | no | optional | decision yes |

No Governance, Intelligence or Private Evals runtime is imported or called.

### Service, result, replay and concurrency

`SkillLifecycleService` validates exact catalog membership, loads canonical history,
constructs current projection, validates target/transition, constructs a typed record,
appends to the correct protocol method, reconciles replay and returns
`SkillLifecycleResult(identity, record, outcome, projection)`.

Equivalent replay means the same namespaced event ID and structurally equal record;
it returns the existing fact and stable projection. Same ID with different content
is a conflict. An equivalent state transition with a new event ID is an invalid
transition. Lost response after append is reconciled by retry/history lookup.

The service calculates against current history immediately before append. There is
no CAS, UnitOfWork or global serialization in this slice. A future adapter must make
per-record uniqueness atomic and may add coordinated concurrency without moving
transition authority into the store. Concurrent activate/revoke, deprecate/re-enable,
supersede/revoke or competing rollbacks can still race across read/append; this is a
documented limitation, not an exactly-once claim.

Projection exposes `resolvable`, `activatable`, `active_selection_eligible`,
`deprecated`, `revoked`, `superseded`, exact relationship refs, last event ref and a
deterministic fingerprint. It does not choose or resolve a version.

### Errors, fakes, exports and coexistence

Stable safe errors cover unpublished version, invalid request, invalid transition,
conflict, missing decision ref, revoked version, invalid supersession/rollback
target, unavailable store and inconsistent history. Messages are fixed and do not
include history or external references.

There is no production in-memory or concrete store. Test fakes implement the Phase 3
protocol exactly, remain append-only, and contain no state-machine/projection logic.
Public exports are the seven requests, result/outcome/projection/state, service and
stable errors. Ordering, event factory, transition implementation and fake stores are
not exported.

Phase 1 `SkillsRuntime`, manifest status mutation, enable/disable/deprecate behavior,
API/Commands, `FileCollection`, packages, assignments and leases are unchanged.
No implicit consumer migration or progression exists.

### Files and verification

Created:

- `backend/synapse/skills/phase6_errors.py`
- `backend/synapse/skills/phase6_models.py`
- `backend/synapse/skills/phase6_lifecycle.py`
- `tests/test_skills_phase6_lifecycle.py`

Changed:

- `backend/synapse/skills/phase3_records.py` (optional event/decision/evidence refs
  and explicit deactivation kind)
- `backend/synapse/skills/__init__.py` (narrow public Slice 6 surface)
- `tests/architecture/test_skills_boundaries.py`
- this document

`SkillCatalogStore` and `SkillLifecycleStore` protocols were not changed. Concrete
persistence, installation, restart recovery, migrations, UnitOfWork, external
adapters, evaluation/Governance bindings, execution and Sandbox remain absent.
Private Evals was not changed. Slice 7 was not started.

Verification: Slice 6 **17 passed**; Slice 5 **23 passed**; Slice 4 **65
passed/1 platform skip**; Slice 3 **8 passed**; Slice 2 **88 passed**; Phase 1
**15 passed**; Skills boundary **13 passed**; architecture **145 passed**; Ruff
**PASS**; Mypy Skills **PASS for 24 files**; authoritative Mypy retained the
inherited baseline **215 errors/58 files, 536 checked, zero Slice 6 errors**;
diff check **PASS** with pre-existing repository line-ending warnings; official
graph **70 contexts/263 governed edges**; official SCC unchanged at **13
contexts/35 internal edges**, Skills outside; exact graph **536 modules/1,647
runtime edges/zero parse errors/zero non-trivial SCCs**.

Search audit found no Slice 6 status/manifest mutation, overwrite, delete, latest,
wildcard, execution, evaluation, approval, trust, subprocess, importlib,
`datetime.now`, random UUID, background work, auto-promotion/rollback, or external
runtime import. The only `install` matches are the required typed
`installation_id` reference. Broader mutation/execution matches remain in Phase 1
compatibility code and were not changed by this slice.

No stage, commit, push or PR was performed. Backend remains **NOT READY**.

**Skills Runtime Phase 2 - Slice 6 implemented, module NOT IMPLEMENTED**

## 38. Auditoria corretiva do Slice 6

Data: **2026-07-27**

Esta seção substitui integralmente a seção 37 como authority vigente do Slice 6.
A implementação inicial não foi aprovada porque sobrepunha `DISABLED` e
`DEACTIVATED`, restaurava snapshot de state no re-enable, projetava rollback como
supersession, aceitava activation parent não verificado, inferia truncation pelo
número 200 e derivava event ID quase exclusivamente de input arbitrário do caller.

### Inventário exato

| Symbol | File | Responsibility | Public? | State-machine critical? |
| --- | --- | --- | ---: | ---: |
| `SkillActivationState` | phase6_models | dimensão never-active/active/inactive | sim | sim |
| `SkillSelectionState` | phase6_models | dimensão eligible/superseded/revoked | sim | sim |
| `SkillLifecycleKind` | phase3_records | generic event vocabulary | não | sim |
| `SkillLifecycleReason` | phase3_records | reason enum fechado | não | sim |
| six request classes | phase6_models | commands imutáveis por operação | sim | sim |
| `SkillLifecycleResult` | phase6_models | record/outcome/projection tipados | sim | não |
| `SkillLifecycleProjection` | phase6_models | facts ortogonais derivados | sim | sim |
| `SkillLifecycleService` | phase6_lifecycle | lifecycle application authority | sim | sim |
| `SkillLifecycleRecord` | phase3_records | deactivate/deprecate/re-enable/supersede/rollback ref | não | sim |
| `SkillActivationRecord` | phase3_records | activation fact com parent installation | não | sim |
| `SkillRevocationRecord` | phase3_records | terminal decision fact | não | sim |
| `SkillLifecycleHistory` | phase3_contracts | records + completeness assertion | sim | sim |
| `SkillActivationParentVerificationPort` | phase6_models | verifica correspondence sem expor store | sim | sim |
| lifecycle errors | phase6_errors | fixed safe failures | sim | sim |
| `_project_skill_lifecycle` | phase6_lifecycle | pure dimensional replay | não | sim |
| `_canonical_history` | phase6_lifecycle | validation/order/equal-time rejection | não | sim |
| `_event_timestamp`, `_event_order` | phase6_lifecycle | factual order helpers | não | sim |
| `_record_id` | phase6_lifecycle | canonical semantic identity | não | sim |
| projection fingerprint | removido | nenhum consumer antes de Slice 9/14 | não | não |
| test fakes | test_skills_phase6_lifecycle | protocol-only evidence | não | não |

### Event vocabulary corrigido

| Event kind | Record family | Meaning | Overlaps another event? |
| --- | --- | --- | ---: |
| activated | `SkillActivationRecord` | activation operacional com parent verificado | não |
| deactivated | `SkillLifecycleRecord.DEACTIVATED` | encerra activation vigente | não |
| deprecated | `SkillLifecycleRecord.DEPRECATED` | liga advisory flag | não |
| re-enabled | `SkillLifecycleRecord.REENABLED` | limpa advisory flag | não |
| superseded | `SkillLifecycleRecord.SUPERSEDED` | relação de replacement | não |
| rollback referenced | `SkillLifecycleRecord.ROLLBACK_REFERENCED` | decisão/target sem deployment | não |
| revoked | `SkillRevocationRecord` | terminal prohibition | não |

`DISABLED` foi removido. `ROLLED_BACK` foi renomeado para
`ROLLBACK_REFERENCED`: o record não afirma operação concluída. Activated e revoked
não são generic enum kinds porque possuem record families e invariants próprias.

### State vocabulary e dimensões

| State/dimension | Derived from | Mutually exclusive with | Terminal? |
| --- | --- | --- | ---: |
| published baseline | `PublishedSkillVersionRecord`, zero events | unpublished | não |
| activation `NEVER_ACTIVATED` | ausência de activation | active/inactive | não |
| activation `ACTIVE` | valid-parent activation após última deactivation | never/inactive | não |
| activation `INACTIVE` | deactivation ou revocation dominante | never/active | não |
| selection `ELIGIBLE` | ausência de supersession/revocation | superseded/revoked | não |
| selection `SUPERSEDED` | exact replacement relation | eligible/revoked | não; pode revogar |
| selection `REVOKED` | revocation | eligible/superseded | sim |
| `deprecated` flag | deprecated sem re-enable posterior | false | não |
| rollback relation | rollback-reference event | nenhuma dimensão | não |

`PUBLISHED` não é event nem enum de current state: é baseline provado pelo catalog.
`ACTIVE` pode coexistir com deprecated e superseded como histórico operacional, mas
`active_selection_eligible` fica falso. Supersession é relação que altera somente a
dimensão de seleção. Revocation domina current facts: active, activatable,
resolvable, deprecated-current e superseded-current ficam falsos; relações antigas
continuam disponíveis como histórico.

### Matriz completa

Legenda: A=allowed, D=denied. `Act` exige valid installation parent; `Sup` exige
exact compatible target e acyclic chain; `Rb` exige exact target e decision;
`Rev` exige decision. Rollback reference não muda activation/selection.

| From | Event | A/D | Resulting projection | Required refs / reason |
| --- | --- | ---: | --- | --- |
| PUBLISHED | activated | A | activation ACTIVE | verified installation parent |
| PUBLISHED | deactivated | D | unchanged | no active fact |
| PUBLISHED | deprecated | A | deprecated=true | advisory |
| PUBLISHED | re-enabled | D | unchanged | no deprecation |
| PUBLISHED | superseded | A | selection SUPERSEDED | exact replacement |
| PUBLISHED | rollback ref | A | rollback relation only | target+decision |
| PUBLISHED | revoked | A | selection REVOKED | decision |
| ACTIVE | activated | D | unchanged | redundant |
| ACTIVE | deactivated | A | activation INACTIVE | current activation |
| ACTIVE | deprecated | A | ACTIVE+deprecated | orthogonal advisory |
| ACTIVE | re-enabled | D | unchanged | no deprecation |
| ACTIVE | superseded | A | ACTIVE+SUPERSEDED | relational selection |
| ACTIVE | rollback ref | A | ACTIVE+rollback relation | no deployment |
| ACTIVE | revoked | A | REVOKED+INACTIVE | terminal dominance |
| INACTIVE | activated | A | activation ACTIVE | verified parent |
| INACTIVE | deactivated | D | unchanged | redundant |
| INACTIVE | deprecated | A | INACTIVE+deprecated | advisory |
| INACTIVE | re-enabled | D | unchanged | no deprecation |
| INACTIVE | superseded | A | INACTIVE+SUPERSEDED | exact replacement |
| INACTIVE | rollback ref | A | INACTIVE+rollback relation | target+decision |
| INACTIVE | revoked | A | REVOKED | terminal |
| DEPRECATED | activated | D | unchanged | deprecated blocks activation |
| DEPRECATED | deactivated | conditional | INACTIVE+deprecated | only if activation was ACTIVE |
| DEPRECATED | deprecated | D | unchanged | duplicate layer forbidden |
| DEPRECATED | re-enabled | A | deprecated=false; other dimensions unchanged | clear flag only |
| DEPRECATED | superseded | A | deprecated+SUPERSEDED | exact replacement |
| DEPRECATED | rollback ref | A | deprecated+rollback relation | target+decision |
| DEPRECATED | revoked | A | REVOKED | terminal |
| SUPERSEDED | activated | D | unchanged | selection closed |
| SUPERSEDED | deactivated | conditional | INACTIVE+SUPERSEDED | only if still ACTIVE |
| SUPERSEDED | deprecated | D | unchanged | no new default-selection advisory needed |
| SUPERSEDED | re-enabled | conditional | deprecated=false+SUPERSEDED | only if deprecated already true |
| SUPERSEDED | superseded | D | unchanged | one replacement relation |
| SUPERSEDED | rollback ref | A | keeps SUPERSEDED + relation | target+decision |
| SUPERSEDED | revoked | A | REVOKED | terminal |
| ROLLBACK_REF | activated | A if otherwise eligible | ACTIVE+same rollback relation | verified parent |
| ROLLBACK_REF | deactivated | A only if active | INACTIVE+same relation | active prerequisite |
| ROLLBACK_REF | deprecated | A if eligible | deprecated+same relation | advisory |
| ROLLBACK_REF | re-enabled | A only if deprecated | clears flag only | no rewind |
| ROLLBACK_REF | superseded | A if eligible | SUPERSEDED+same relation | exact replacement |
| ROLLBACK_REF | rollback ref | D | unchanged | competing target forbidden |
| ROLLBACK_REF | revoked | A | REVOKED | terminal |
| REVOKED | activated | D | REVOKED | terminal |
| REVOKED | deactivated | D | REVOKED | terminal |
| REVOKED | deprecated | D | REVOKED | terminal |
| REVOKED | re-enabled | D | REVOKED | terminal |
| REVOKED | superseded | D | REVOKED | terminal |
| REVOKED | rollback ref | D | REVOKED | terminal |
| REVOKED | revoked | D/replay | REVOKED | exact same record replays; new fact denied |

As células condicionais são resolvidas pelas dimensões ortogonais, não por um enum
agregado ambíguo. A suíte parametrizada cobre 42 combinações de seis commands
Slice 6 em sete cenários, com testes adicionais para activation records validados.

### Revocation, re-enable e supersession

Após qualquer revocation válida: activation current vira INACTIVE; active,
activatable, resolvable, deprecated-current, superseded-current e
active-selection eligibility são falsos. Exact replay retorna o record existente.
Mesmo ID com record divergente conflita. Outra revocation semanticamente distinta
é terminalmente rejeitada.

Re-enable apenas executa `deprecated=false`. Ele não restaura snapshot. Assim:
deactivation ou supersession ocorridos durante deprecation permanecem efetivos;
duplicate deprecation/re-enable falha; múltiplos ciclos sequenciais são válidos.

Supersession é exact replacement relation e selection closure, não latest nem
SemVer policy. Lower SemVer, build metadata, target deprecated e target já
superseded são permitidos. Self-cycle, direct cycle e longer cycle são detectados
seguindo `superseded_by` por exact lookup/history. Uma race concorrente ainda pode
criar cycle porque não há aggregate CAS.

### Rollback scope

| Rollback concern | Owner atual | Effect in Slice 6 |
| --- | --- | --- |
| request/decision | Skills lifecycle | append exact relation/ref |
| source record | source/current version | recebe `ROLLBACK_REFERENCED` |
| source selection | Skills projection | não muda |
| target activation | Slice 7/deployment futuro | nenhuma |
| installation/restore point | deployment/installation futuro | não consultado |
| deployment rollback | Deployment Runtime futuro | não executado |

O target precisa estar publicado, same SkillId, distinct e não revoked. Deprecated
target é permitido somente porque decision ref é obrigatório. Não há claim de
restore, deployment ou activation concluída.

### Activation decision

Foi escolhida uma combinação estrita das opções C e narrow verification:

- Slice 6 não expõe `activate` nem `ActivateSkillVersionRequest`;
- não constrói ou append `SkillActivationRecord`;
- mantém eligibility (`activatable`) para Slice 7;
- ao projetar um activation record já existente, exige
  `SkillActivationParentVerificationPort`;
- nenhum adapter/store de installation foi implementado;
- parent inválido produz `InvalidSkillActivationParent`, nunca `active=true`.

O port verifica somente correspondence `(exact identity, installation_id) -> bool`;
não expõe path, bytes, payload, availability store ou operação de instalação.

### Publication, completeness e ordering

Source e targets sempre usam exact catalog lookup. Same SkillId/version com
fingerprints diferentes não é fallback. Catalog unavailable é traduzido.

`SkillLifecycleStore.history` agora retorna `SkillLifecycleHistory(records,
complete)`. O limit não prova truncation ou completeness: 200 records com
`complete=true` são aceitos; qualquer quantidade com `complete=false` produz
`IncompleteSkillLifecycleHistory`. Não foi criada paginação genérica.

O service ordena por factual UTC timestamp e record ID, independentemente da ordem
do adapter. Distinct records no mesmo timestamp são rejeitados com
`AmbiguousSkillLifecycleOrdering`: o lexical ID nunca decide state. Exact replay
no mesmo timestamp continua válido. Timestamp anterior ao máximo é backdated e
falha; future timestamp é aceito; não há wall-clock read; precisão é microseconds.

### Semantic identity e equality

| Event | Identity inputs | Caller-controlled? | Deterministic? |
| --- | --- | ---: | ---: |
| lifecycle generic | family, kind, exact identity, actor, reason, UTC time, semantic ref, target, decision | parcialmente | sim |
| revocation | family, kind, exact identity, actor, reason, UTC time, semantic ref, decision, evidence | parcialmente | sim |
| activation | Phase 3 record ID; producer adiado | futuro Slice 7 | fora do producer Slice 6 |

O ID é SHA-256 de canonical domain tuple, não hash isolado do caller ref. Reuso da
mesma ref em operações/conteúdos diferentes não colide semanticamente. Timestamp,
actor, reason, target, decision e evidence participam. `event_ref` é semantic
source/correlation input, não idempotency store independente.

Structural equality compara todo o record. Retry idêntico reconstrói o mesmo ID e
record. Mudança de actor/time/reason/ref/target/decision cria outro fact candidate;
se redundant/ilegal, a transition authority o rejeita. Mesmo ID com bytes
estruturalmente diferentes é divergent duplicate/conflict. Lost response é
reconciliado por exact semantic retry.

### External references

| Event | Governance ref | Intelligence ref | Evidence ref | Current requirement |
| --- | ---: | ---: | ---: | --- |
| deactivate/deprecate/re-enable | não | não | não | none |
| supersede | optional structural decision | não | não | target only |
| rollback ref | structural decision | não | não | required |
| revoke | structural decision | não | optional | decision required |
| activation | não inventado | não | não | verified parent only, producer deferred |

References não provam approval, trust ou authenticity e nenhum runtime externo é
chamado.

### Projection facts

| Fact | Derived from | Future slice | Stable? |
| --- | --- | --- | ---: |
| `activation_state`/`active` | valid-parent activation/deactivation/revocation | 7/9 | sim |
| `selection_state` | supersession/revocation | 9 | sim |
| `deprecated` | deprecate/re-enable, dominated by revoke | 9 | sim |
| `revoked` | revocation | 7/9 | sim |
| `superseded`/target | exact relation unless revoke dominates current flag | 9 | sim |
| `resolvable` | selection eligible | 9 | sim |
| `activatable` | lifecycle eligibility only; not installation availability | 7 | sim |
| active-selection eligibility | active+eligible+not deprecated | 9 | sim |
| rollback target/decision | reference record | deployment future | sim |

Projection fingerprint foi removido: não havia consumer atual e uma derived
projection não deve virar nova persisted authority.

### Service methods e boundaries

| Method | Operation | Catalog | History | Append |
| --- | --- | ---: | ---: | ---: |
| `deactivate` | activation termination fact | sim | sim | lifecycle |
| `deprecate` | advisory on | sim | sim | lifecycle |
| `reenable` | advisory off | sim | sim | lifecycle |
| `supersede` | exact replacement relation/cycle validation | sim | sim | lifecycle |
| `rollback` | exact target/decision relation | sim | sim | lifecycle |
| `revoke` | terminal decision | sim | sim | revocation |
| `projection` | derived query | sim | sim | não |
| `history` | complete canonical query | sim | sim | não |

Não há filesystem, package verification, install, dependency resolution, external
runtime, global event, execution ou Sandbox.

### Concurrency e store sufficiency

O service fornece somente optimistic local validation. O store garante record-ID
uniqueness/replay, history response e completeness assertion; não garante aggregate
CAS. Dois services podem validar a mesma history e append activate/revoke,
deprecate/re-enable, competing supersessions/rollbacks. Slice 14 deverá fornecer
transaction/CAS ou equivalente. Não há claim de state-machine consistency global.

O contract agora é suficiente para completeness, local ordering, replay scan e
conflict reconciliation. Activation parent correspondence usa o narrow port.
Ainda faltam aggregate revision, atomic expected-version append, durable
completeness/pagination evidence e multi-version cycle serialization.

### Phase 3 record corrections

| Record altered | Field/kind | Optional? | Needed? | Compatibility impact |
| --- | --- | ---: | ---: | --- |
| LifecycleRecord | `decision_ref` | sim, kind-dependent | rollback/supersession | strict validation added |
| LifecycleRecord | `DEACTIVATED` | no | unique event authority | `DISABLED` removed |
| LifecycleRecord | `ROLLBACK_REFERENCED` | no | truthful semantics | replaces `ROLLED_BACK` |
| ActivationRecord | event/decision additions removed | — | no | restored narrow Phase 3 shape |
| RevocationRecord | `evidence_ref` | sim | optional evidence pointer | structural only |
| Lifecycle history response | `complete` | no | completeness proof | protocol return type changed |

Lifecycle decision ref is required for rollback, optional only for supersession and
forbidden for deactivation/deprecation/re-enable. Related version is required only
for supersession/rollback. Records não são bags de campos.

### Errors e public surface

Errors reais: unpublished source; invalid request/transition; conflict; missing
decision; revoked terminal; invalid activation parent; invalid targets; incomplete
history; ambiguous ordering; unavailable store; corrupt history. Todos possuem
mensagens fixas sem history/ref payload.

Public: six command requests, activation/selection enums, projection/result/outcome,
service, stable errors, `SkillLifecycleHistory` e parent-verification port. Não são
publicados transition/order helpers, event factory, projection helper/fingerprint,
Phase 3 event enums ou fakes.

### Coverage corretiva

| Concern | Positive | Matrix | Replay | Conflict | Corrupt history | Concurrency limitation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| transitions | sim | 42 cells | sim | sim | sim | documentada |
| revocation dominance | 6 source projections | terminal cells | sim | sim | post-event | documentada |
| re-enable | 8 history shapes/cycles | sim | sim | n/a | sim | documentada |
| supersession | chains/targets/build/lower | sim | sim | target/cycle | cycle | race documentada |
| rollback | relation-only/deprecated target | sim | sim | competing target | sim | race documentada |
| activation parent | valid/invalid | producer deferred | n/a | n/a | invalid parent | port sem adapter |
| publication | source/target/exact fingerprint | n/a | n/a | exact mismatch | n/a | catalog atomicity only |
| ordering | backdated/equal/future/unordered | sim | old replay | equal-time error | sim | equal-time rejected |
| identity/refs | all canonical inputs | n/a | deterministic | divergent defense | n/a | no global request store |
| projection/no progression/exports | sim | dimensional | stable | n/a | sim | boundaries explicit |

`tests/test_skills_phase6_lifecycle.py` possui **73 effective pytest cases** após
parametrização; não é uma contagem de 17 funções amplas.

### Residual risks

- aggregate concurrency/CAS permanece Slice 14;
- adapter pode violar sua assertion `complete`; durable proof é futuro;
- supersession-cycle validation é optimistic e pode perder race;
- activation producer, installation lookup/availability e operational transition
  permanecem Slice 7;
- restart/durability/concrete persistence continuam inexistentes.

No installation, concrete persistence, SQLite, migration, recovery, UnitOfWork,
external adapter/binding, API, Commands/Queries, Composition Root, execution or
Sandbox was implemented. Private Evals and Phase 1 were not changed. Slice 7 was
not started. Backend remains **NOT READY**.

Corrective gates: Slice 6 **73 passed**; Slice 5 **23 passed**; Slice 4 **65
passed/1 platform skip**; Slice 3 **8 passed**; Slice 2 **88 passed**; Phase 1
**15 passed**; Skills boundary **13 passed**; architecture **145 passed**; Ruff
**PASS**; Mypy Skills **PASS for 24 files**; authoritative Mypy retained the
inherited baseline **215 errors/58 files, 536 checked, zero changed-Skills
errors**; diff check **PASS** with pre-existing line-ending warnings; official
graph **70 contexts/263 governed edges**; official SCC unchanged at **13
contexts/35 internal edges**, Skills outside; exact graph **536 modules/1,649
runtime edges/zero parse errors/zero non-trivial SCCs**.

No files were staged and no commit, push or PR was performed.

**SLICE 6 APPROVED**

**Skills Runtime Phase 2 - Slice 6 corrective audit approved, module NOT IMPLEMENTED**

## 39. Slice 7 - installation authority and operational activation

Date: **2026-07-27**

### Existing-symbol audit

| Existing symbol | Responsibility | Used by Slice 7? | Risk/decision |
| --- | --- | ---: | --- |
| `SkillInstallationRecord` | append-only local installation fact | yes | narrowed to exact content/storage refs; no path/payload |
| `SkillInstallationTerminationRecord` | parent termination fact | yes | exact replacement required only for REPLACED |
| `SkillInstallationStore` | append/history port | yes | history now declares completeness |
| `SkillActivationRecord` | operational activation with installation parent | yes | producer now exists only after parent validation |
| `SkillActivationParentVerificationPort` | parent correspondence boundary | yes | implemented by domain verifier, no adapter |
| `SkillLifecycleStore` | lifecycle append/history | yes | activation uses existing port |
| `SkillLifecycleProjection` | lifecycle eligibility/current activation | yes | now exposes active installation ID |
| `VerifiedSkillContentSnapshot` | immutable technical verification result | yes | correspondence checked without re-verification |
| `PublishedSkillVersionRecord` | exact publication membership | yes | prerequisite for every operation/query |

### Authority map

| Concern | Authority | Input | Output |
| --- | --- | --- | --- |
| installation request/correspondence | `SkillInstallationService` | publication+snapshot+local ref | validated candidate |
| publication prerequisite | catalog | exact identity | published record |
| installation identity | internal semantic factory | exact identity+local refs | `installation:` ID |
| installation append/replay | installation service/store | record | typed result |
| termination | `SkillInstallationTerminationService` | exact parent+reason+lifecycle | termination result |
| installation projection | pure internal projector | complete canonical history | projection |
| parent verification | `SkillInstallationParentVerifier` | identity+installation ID | valid record/error |
| lifecycle eligibility | Slice 6 service | exact history | lifecycle projection |
| activation/deactivation | `SkillActivationService` + Slice 6 service | typed request | lifecycle fact/result |
| operational projection | activation service | installation+lifecycle | combined projection |

### Concepts

| Concept | Meaning | Authority | Implies next? |
| --- | --- | --- | ---: |
| published | exact catalog member | Catalog | no |
| technically verified | immutable snapshot correspondence | Phase 4 | no |
| installed | local content reference registered | Installation | no |
| locally available | at least one nonterminated installation fact | projection | no |
| active | exact usable installation selected locally | Lifecycle/Activation | no execution |
| trusted | external policy concept | not represented | no |
| approved | external decision concept | not represented | no |
| executable | future execution/runtime decision | not represented | no |

Verification is not installation; installation is neither trust nor activation;
activation is not execution. Filesystem presence is never inferred.

### Requests and local content reference

`InstallVerifiedSkillVersionRequest` carries exact identity, verified snapshot,
`InstalledSkillContentRef`, actor, semantic installation ref, request-scoped
idempotency ref and caller-supplied UTC time. Local content contains only semantic
content ref, exact fingerprint and storage-profile ref. No path, URI, credential,
bytes, trust, approval, active flag, metadata dict or `Any` exists.

Activation/deactivation/termination requests are separately frozen and operation
specific. Idempotency refs remain request-scoped and are not persisted.

### Correspondence and installation identity

Before append the service checks exact catalog membership; publication manifest;
snapshot manifest/content fingerprints and technical identity; verified asset
correspondence; request exact identity; and local content fingerprint. It does not
open filesystem, recalculate asset checksums or invoke the verifier.

Installation ID is deterministic SHA-256 under `installation:` over exact version,
semantic content ref, content fingerprint, storage profile and installation ref.
Timestamp and request-idempotency ref are excluded. Multiple installations may
coexist only when this semantic local identity differs, allowing another profile or
explicit replica without a preferred/main installation.

### Installation record

| Field | Meaning | Identity component? | Replay relevant? |
| --- | --- | ---: | ---: |
| record ID | semantic installation identity | yes | yes |
| exact identity | published immutable version | yes | yes |
| content fingerprint | verified local content | yes | yes |
| content ref | opaque semantic local reference | yes | yes |
| storage profile ref | storage authority/profile | yes | yes |
| installation ref | installation/replica semantic fact | yes | yes |
| installed_at | initial factual time | no | existing fact wins replay |
| actor ref | initial factual actor | no | existing fact wins replay |

No trust, approval, active state, raw path/package or execution state is stored.

### Installation, termination and projection

`SkillInstallationService` owns install, exact history/query and deterministic
projection. It never copies/downloads/mounts content and never activates.

Termination meanings:

- DETACHED ends the local binding only;
- UNINSTALLED declares local availability ended;
- REPLACED points to another exact usable installation;
- CORRUPTED makes the installation unusable.

Termination preserves the parent/history/content reference, never deletes,
unpublishes, revokes or mutates manifest. `SkillInstallationProjection` exposes all
known installations, usable installations, terminations, terminated/corrupted IDs,
local availability, last fact and completeness. It chooses no preferred/latest
installation.

`SkillInstallationStore.history` returns `SkillInstallationHistory(records,
complete)`. Count is not completeness. Ordering is factual timestamp then record ID;
distinct equal timestamps are ambiguous. Backdated facts and termination not after
its parent are rejected. Exact replay is checked before time validation.

### Parent verification and operational activation

`SkillInstallationParentVerifier` checks complete history, exact version/ID,
content fingerprint and current nonterminated/noncorrupted usability. It reads no
filesystem and grants no trust. An active current parent is revalidated whenever
lifecycle projection is read; historical inactive activation remains history after
an explicit deactivation/termination.

`SkillActivationService.activate` validates the installation parent, causal
timestamp and Slice 6 eligibility, constructs `SkillActivationRecord`, delegates
the state transition/append to `SkillLifecycleService`, and returns a combined
projection. Active means local operational selection of exact verified content; it
does not mean process execution, deployment completion, trust or approval.

`deactivate` delegates the approved append-only Slice 6 event. It preserves
installation and activation history and performs no uninstall, stop-process,
revocation or Sandbox action.

No global one-active-version-per-SkillId invariant is claimed: the current stores
cannot query all active versions atomically. Exact-version state is enforced;
cross-version exclusivity remains Slice 14. No hidden auto-deactivation occurs.

Termination of the currently active parent is rejected until explicit deactivation.
Detached/uninstalled/corrupted parents cannot be activated. Revocation does not
terminate installation: the operational projection remains locally available but
`usable_for_activation=false`.

### Replay, concurrency and results

Install replay uses semantic installation identity and returns the initial fact even
if retry actor/time/request key changes. Activation/termination semantic IDs include
their full factual event projection but exclude request-idempotency key. Exact
structural replay returns existing; same ID/divergent content conflicts; lost
responses reconcile through complete history.

All services provide optimistic validation only. Install/terminate,
activate/terminate, activate/revoke and competing activations can race between read
and append. Stores guarantee only record-ID uniqueness and completeness assertions.
Aggregate CAS/transaction and cross-version exclusivity remain Slice 14.

Typed results are `SkillInstallationResult`,
`SkillInstallationTerminationResult` and `SkillActivationResult`. Projections are
`SkillInstallationProjection` and `SkillOperationalProjection`; no bool/dict/Any
result exists.

### Errors and public surface

Safe fixed errors cover unpublished version, invalid request, snapshot mismatch,
conflict/not found, terminated/corrupted installation, incomplete history,
ambiguous ordering, active-parent termination, invalid activation parent/transition,
store unavailable and corrupt history. No locator/ref/history is exposed.

Public exports are the narrow requests, content reference, projections, results,
three services, parent verifier/protocol and stable errors. Helpers, factories,
ordering, fake stores and raw locator helpers remain internal.

### Phase 1 and boundaries

Phase 1 install/uninstall, copying, registry, mutable status, API/Commands and
`FileCollection` are unchanged and have no migrated consumer. Phase 7 imports no
concrete persistence, filesystem, parser/verifier implementation, bootstrap, API,
Tools, Sandbox, Governance/Intelligence runtime or Private Evals. It uses no
subprocess/importlib/eval/exec, wall clock or random UUID.

Created:

- `backend/synapse/skills/phase7_errors.py`
- `backend/synapse/skills/phase7_models.py`
- `backend/synapse/skills/phase7_installation.py`
- `tests/test_skills_phase7_installation.py`

Changed:

- `backend/synapse/skills/phase3_records.py`
- `backend/synapse/skills/phase3_contracts.py`
- `backend/synapse/skills/phase6_models.py`
- `backend/synapse/skills/phase6_lifecycle.py`
- `backend/synapse/skills/__init__.py`
- `tests/test_skills_phase3_store_contracts.py`
- `tests/test_skills_phase6_lifecycle.py`
- `tests/architecture/test_skills_boundaries.py`
- this document

No concrete persistence, download, copy, clone, dependency resolution, external
binding/adapter, execution or Sandbox was implemented. Private Evals was not
changed. Slice 8 was not started. Backend remains **NOT READY**.

Gates: Slice 7 **28 passed**; Slice 6 **73 passed**; Slice 5 **23 passed**;
Slice 4 **65 passed/1 platform skip**; Slice 3 **8 passed**; Slice 2 **88
passed**; Phase 1 **15 passed**; Skills boundaries **14 passed**; architecture
**146 passed**; Ruff **PASS**; Mypy Skills **PASS for 27 files**; authoritative
Mypy retained the inherited baseline **215 errors/58 files, 539 checked, zero
changed-Skills errors**; diff check **PASS** with pre-existing line-ending
warnings; official graph **70 contexts/263 governed edges**; official SCC
unchanged at **13 contexts/35 internal edges**, Skills outside; exact graph
**539 modules/1,670 runtime edges/zero parse errors/zero non-trivial SCCs**.

Scope search found zero production Slice 7 operations for copy, download, clone,
delete, overwrite, latest, fallback, filesystem, execute, subprocess, importlib,
Sandbox, evaluate, approve, trust, auto activation/deactivation, wall clock,
random UUID or background work. `path` matches are local dictionary variables for
manifest logical-path correspondence, not `pathlib.Path` or filesystem access.
Phase 1 copy/install/uninstall occurrences remain legacy compatibility and were
not changed.

No file was staged and no commit, push or PR was performed.

**Skills Runtime Phase 2 - Slice 7 implemented, module NOT IMPLEMENTED**

## 40. Auditoria corretiva do Slice 7

Esta auditoria corrige a linguagem de custody, a identidade factual da instalação,
a origem de corruption e a modelagem explícita das corridas cross-store. Ela não
adiciona persistence, filesystem custody, transaction, CAS ou qualquer elemento
do Slice 8.

### Installation versus physical custody

`InstalledSkillContentRef` é metadata de endereçamento registrado. Seu nome não
constitui prova de que bytes existem, permanecem legíveis ou são controlados pelo
processo. A prova disponível no Slice 7 é estritamente:

| Concept | Proven by Slice 7 | Physical claim |
|---|---|---:|
| verified content snapshot | immutable Phase 4 snapshot supplied to correspondence validation | no |
| content reference | closed `content:` semantic reference | no |
| content custody | future storage/filesystem adapter | not available |
| locally addressable | registered content and storage-profile references | logical only |
| locally available | no fact with this name is projected | not asserted |
| installed | immutable installation-registration record exists | no |
| usable | current registration plus valid lifecycle/parent facts | operational only |
| activatable | combined registration and Slice 6 lifecycle eligibility | no |
| active | Slice 6 operational selection backed by a current registration | not execution |

Accordingly, `locally_available` and `usable_installations` were removed. The
installation projection now exposes `current_registrations` and
`has_current_registration`; the combined projection exposes
`activation_eligible` and `operationally_active`. None means executable,
deployed, healthy storage or physically present.

`InstalledSkillContentRef` accepts only a `content:` reference, the exact content
fingerprint and a `storage-profile:` reference. `SkillSemanticReference` forbids
URLs and paths and applies a closed namespaced format. No absolute path, URI,
credential, host state, mutable locator or request key is present.

### Corrected installation identity

The canonical installation ID projection is:

```text
(
  PublishedSkillVersionId.canonical_text,
  content_ref.canonical_text,
  content_fingerprint.canonical_text,
  storage_profile_ref.canonical_text,
)
```

`registration_ref`, actor, timestamp and request idempotency do not participate.
`registration_ref` replaces the ambiguous `installation_ref`: it is the
observation reference retained on the first registration fact, not an external
authority, locator, request identity or factual-identity component.

| Field | Category | ID component | Replay behavior |
|---|---|---:|---|
| exact published version | factual identity | yes | must match |
| content fingerprint | factual identity | yes | must match |
| content reference | factual identity/replica address | yes | must match |
| storage profile | factual identity/placement class | yes | must match |
| registration reference | first-fact observation | no | original retained |
| actor | first-fact observation | no | original retained |
| installed timestamp | first-fact observation | no | original retained |
| idempotency reference | request identity | no | never persisted |

This gives the following multiple-installation policy:

| Scenario | Result |
|---|---|
| same version, content reference and storage profile | same installation fact |
| different content reference | distinct coexisting installation |
| different storage profile | distinct coexisting installation |
| same fingerprint, distinct replica reference | distinct coexisting installation |
| same semantic registration after termination | replay of the terminal history; no recreation |
| same semantic registration after corruption | replay of the terminal history; no restoration |
| concurrent equivalent registrations | converge on one deterministic ID |

A new installation after a terminal fact therefore needs a new factual
content-reference or storage-profile identity. History is neither erased nor
ambiguously reused.

### Correspondence and custody boundary

Before append, `SkillInstallationService` validates exact catalog membership,
publication identity, manifest equality, manifest-derived identity, technical
identity, snapshot asset fingerprint, registered fingerprint, manifest/asset
logical correspondence and causal time after publication. These checks are
structural over already verified values. The service does not open files,
recompute bytes from storage, invoke the parser/verifier, inspect a provider,
infer trust or assert physical custody.

### Termination and corruption semantics

All termination reasons are terminal for the registration, not statements about
physical byte operations:

| Reason | Meaning | Current registration afterward | Physical claim | Recoverable in place |
|---|---|---:|---:|---:|
| `DETACHED` | logical association ended | no | no | no |
| `UNINSTALLED` | registration ended following an external uninstall assertion | no | no deletion claim | no |
| `REPLACED` | registration ended in favor of an exact current replacement ID | no | no | no |
| `CORRUPTED` | marked unusable from an external integrity observation | no | no damage claim | no |

`CORRUPTED` remains a terminal registration fact, but now requires a closed
`integrity-observation:` reference in both request and record. The Slice 7
authority records that external observation; it does not detect corruption,
recalculate a digest, read storage, attach evidence payload, decide trust or
restore content. Reverification/restoration is not available. A later usable
registration must have a new factual identity.

### Authority and service decomposition

| Concern | Single owner |
|---|---|
| publication prerequisite | Phase 5 catalog |
| snapshot correspondence | `SkillInstallationService` |
| registration identity and append | `SkillInstallationService` |
| installation projection/order | pure Phase 7 helpers |
| termination append | `SkillInstallationTerminationService` |
| corruption marking | termination service, only from typed external observation |
| parent validity | `SkillInstallationParentVerifier` |
| lifecycle eligibility/transition/append | `SkillLifecycleService` from Slice 6 |
| activation coordination | `SkillActivationService` |
| combined operational projection | `SkillActivationService` |

The approximately 630-line module contains four separately constructed
authorities plus their shared pure event algebra. They do not share write
authority: installation, termination and lifecycle stores are injected
explicitly. A file split would duplicate or expose private canonical identity
and projection helpers without changing ownership, so no size-only
fragmentation was performed.

`SkillActivationService` validates the exact parent and causal timestamp, builds
the activation fact and delegates the transition matrix and append to
`SkillLifecycleService`. It contains no second transition table. The lifecycle
service calls the same parent-verification port; therefore parent validity also
has one concrete authority.

The parent verifier proves exact installation ID/version/fingerprint, complete
history, current registration and absence of a corruption termination. It does
not prove trust, approval, execution, physical bytes, storage health or
filesystem presence.

### Activation semantics, replay and limitations

Activation means local operational selection supported by a current registration
record. It is not a running process, deployment, approval or trust decision.
Activation factual identity uses exact version, installation ID, actor, reason
and occurrence time. Request idempotency is not persisted. The redundant
`activation_ref` was removed because it was not represented by the approved
Phase 3 activation fact. Activation results now retain the Slice 6
`SkillLifecycleOutcome` instead of relabeling it as an installation outcome.

Deprecated activation remains denied solely by the Slice 6 projection and
transition authority. Slice 7 contains no duplicate policy table. Projection is
per exact version: there is no query by `SkillId`, global “active version”,
cross-version exclusivity proof or automatic deactivation.

### Cross-store races

The services provide optimistic validation only:

```text
installation termination:
installation read/history and validation
-> lifecycle projection
-> installation append

activation:
installation history and parent verification
-> lifecycle history/transition validation
-> activation append
-> combined projection
```

No aggregate lock, revision, CAS, UnitOfWork or transaction spans the two stores.
An activation may race after the active-parent check, and a termination may race
after parent validation. A late activation after revocation is a corrupted
lifecycle history under the approved Slice 6 rule; revocation is never reversed.
A termination racing an already appended activation preserves both facts but
makes the combined projection fail with
`InvalidOperationalActivationParent`. No rollback, restoration, deactivation or
other hidden progression occurs.

Slice 14 must provide aggregate revision and transactional/CAS coordination if
the product requires universal prevention rather than detection of these races.

### Combined facts

| Fact | Lifecycle only | Installation only | Combined required |
|---|---:|---:|---:|
| lifecycle active selection | yes | no | no |
| current registration | no | yes | no |
| activation eligible | no | no | yes |
| operationally active | no | no | yes |
| executable | no | no | unavailable |

Combined projection is returned only for histories whose current active parent
remains valid. A terminated active parent is surfaced as inconsistency rather
than hidden by a Boolean.

### Public surface and errors

Requests, result/projection types, application services, the parent verifier
needed by future composition, store histories/protocols and safe domain errors
remain public. Pure helpers and all fakes remain internal/test-only.
`SkillActivationResult` uses `SkillLifecycleOutcome`;
`SkillInstallationOutcome` remains limited to installation and termination.
Lifecycle-store failures are no longer mislabeled as installation-store
failures.

Every public Slice 7 error has a producer. Messages contain no content reference,
storage profile, locator or integrity-observation value. The corruption error
now says “marked unusable by integrity observation,” not that bytes are damaged.

### Corrective coverage and residual risks

Corrective tests cover closed reference namespaces, factual identity independent
of registration/request observations, distinct storage profiles, terminal
semantic replay, typed corruption observation, reversed history input,
revocation race, termination race, combined projection naming and no implicit
progression. Existing correspondence, completeness, ordering, lost-response,
conflict, replacement, deprecation, revocation and supersession coverage remains.

Residual risks are intentionally unchanged: no physical custody proof,
persistence, restart recovery, transaction/CAS, global active-version
exclusivity or concrete authorization adapter. Phase 1 and Private Evals were
not changed. Slice 8 was not started. Backend remains **NOT READY**.

Corrective gates: Slice 7 **34 passed**; Slice 6 **73 passed**; Slice 5 **23
passed**; Slice 4 **65 passed/1 platform skip**; Slice 3 **8 passed**; Slice 2
**88 passed**; Phase 1 **15 passed**; Skills boundaries **14 passed**;
architecture **146 passed**; Ruff **PASS**; Mypy Skills **PASS for 27 files**.
Authoritative Mypy retained the inherited **215 errors/58 files, 539 checked**
baseline and reported zero Skills error lines. The governed runtime graph remains
**70 contexts/263 edges**, with the official SCC unchanged at **13 contexts/35
internal edges** and Skills outside it. The exact runtime graph remains **539
modules/1,670 edges/zero parse errors/zero non-trivial SCCs**. Diff check passed
with only pre-existing line-ending warnings. No file was staged and no commit,
push or PR was performed.

**Skills Runtime Phase 2 - Slice 7 corrective audit APPROVED, backend NOT READY**

## 41. Slice 8 — dependency declarations, compatibility facts and validation

Slice 8 is a pure, read-only analysis authority. It turns the immutable Phase 2
declarations, exact catalog records, approved Slice 6 lifecycle projections,
explicit compatibility observations and an optional explicit graph boundary into
typed facts. It neither resolves a dependency nor changes runtime state.

### Existing-symbol audit

| Existing symbol | Responsibility | Slice 8 use | Risk/decision |
|---|---|---:|---|
| `SkillVersionConstraint` | strict caret or bounded SemVer range | yes | matcher consumes the validated type only |
| `SkillDependencyDeclaration` | exact or constrained dependency plus reason/cardinality | yes | manifest is not expanded |
| `SkillCompatibilityDeclaration` | environment/runtime requirements | yes | declaration is not a decision |
| `SkillSecurityDeclaration` | structural security requirements | yes | never grants trust or approval |
| `PublishedSkillVersionId` | exact immutable node/candidate identity | yes | no structural-version fallback |
| `PublishedSkillVersionRecord` | exact manifest catalog fact | yes | read-only |
| `SkillCatalogStore` | exact lookup and bounded listing | yes | listing lacks explicit completeness |
| `SkillLifecycleProjection` | approved derived lifecycle facts | yes | transition table is not duplicated |
| Slice 7 facts | registration and operational selection | no | not required for structural analysis |
| Phase 1 dependency resolver | legacy selection/install/runtime behavior | no | untouched and not an authority here |

Phase 1 continues to accept its legacy wildcard and performs concrete selection.
That behavior is isolated in the frozen compatibility runtime and is not imported
or reused by Phase 2 Slice 8.

### Authority map and concept separation

| Concern | Single authority | Input | Output |
|---|---|---|---|
| declaration validation | analysis service | published manifest | validated requirements or safe error |
| dependency identity | `SkillDependencyId.from_declaration` | owner + declaration | deterministic semantic ID |
| candidate enumeration | dependency-catalog provider | `SkillId` + explicit limit | explicit complete/incomplete page |
| constraint matching | pure matching module | typed constraint/exact version | match/mismatch fact |
| lifecycle eligibility | Slice 6 projection/provider | exact candidate | closed candidate status |
| compatibility declaration | Phase 2 manifest | typed requirements/conflicts | requirement facts |
| compatibility observation | immutable caller-provided fact | exact pair/profile/requirement | observed status |
| missing information | analysis service | unavailable/incomplete facts | typed diagnostic/reason |
| cycle detection | graph-analysis service | manifest-attested explicit graph | canonical cycle facts |
| result projection | analysis service | all derived facts | immutable analysis |

Matching means only that a concrete published version satisfies the exact version
or constraint. Eligible additionally consumes lifecycle facts. Compatible adds
declared/observed compatibility for the supplied analysis profile. None of these
means installed, active or resolved. An observed positive fact is profile-scoped
and does not prove universal compatibility. Absence of negative evidence remains
`UNKNOWN`, not compatible.

### Dependency declarations and identity

The existing declaration remains:

| Field | Type | Meaning |
|---|---|---|
| `skill_id` | `SkillId` | dependency identity |
| `version` | `SkillVersion | None` | exact structural version |
| `constraint` | `SkillVersionConstraint | None` | strict range |
| `reason` | `SkillDependencyReason` | dependency role |
| `optional` | `bool` | required versus optional |

Exactly one of exact version or constraint is required. The existing value object
already rejects empty, unbounded, naked exact, wildcard, moving aliases, tilde,
URLs and package-manager syntax.

The canonical dependency-ID projection is:

```text
(
  owner PublishedSkillVersionId canonical text,
  dependency SkillId,
  ("exact", SkillVersion) or ("constraint", SkillVersionConstraint),
  SkillDependencyReason,
  optional,
)
```

Input order, timestamp, actor, request correlation, process, path and random IDs
do not participate.

Identical declarations have the same canonical identity and are already rejected
as duplicate tuple members by manifest construction. Distinct declarations for
the same dependency Skill ID remain independent requirements: they are neither
merged nor intersected. This includes different constraints, cardinalities and
roles. Intersection and resolution remain reserved for Slice 9. Manifest
construction rejects self-dependency; Slice 8 repeats that structural check. A
bounded range with no stable SemVer solution is also rejected.

### SemVer matching and candidate enumeration

Matching uses only `SkillVersion` and `SkillVersionConstraint`:

- caret upper bounds follow the major-zero rules;
- bounded lower/upper inclusivity is honored;
- prereleases do not satisfy range declarations because the approved constraint
  grammar cannot opt into prerelease ranges;
- build metadata is ignored by precedence comparisons but retained in every
  concrete candidate identity;
- exact-version declarations retain structural build/prerelease equality.

Every catalog record returned within the explicit `SkillStoreQueryLimit` receives
a fact, including constraint mismatches. Every matching candidate is preserved.
There is no winning, first or default candidate.

`SkillCatalogStore.list_versions` returns only a tuple and therefore cannot prove
termination. Slice 8 no longer consumes that method directly. Its narrow
`SkillDependencyCatalogProvider` returns `SkillDependencyCatalogPage(records,
complete)`, so completeness is provider-attested and never inferred from
`len == limit`. No page token or generic pagination protocol was introduced.

### Required, optional and lifecycle facts

Required dependencies without a conclusive eligible/compatible candidate are
blocking. Optional dependencies never block for ordinary absence or mismatch,
but emit explicit unavailable, unmatched or incompatible diagnostics. Optional
facts are never silently dropped or used as an alternative branch.

Candidate lifecycle classification consumes the Slice 6 projection:

| Slice 6 fact | Slice 8 lifecycle dimension |
|---|---|
| eligible/resolvable, not deprecated | `ELIGIBLE` |
| deprecated | `DEPRECATED` |
| superseded | `SUPERSEDED` |
| revoked | `REVOKED` |
| store unavailable | `UNAVAILABLE` |
| history incomplete | `INCOMPLETE` |
| inconsistent history/projection | `INCONSISTENT` |

Activation state is not a matching prerequisite. Installation and physical
custody are not consulted.

### Compatibility declarations and observations

Only approved manifest dimensions are projected: operating profiles, platforms,
Python constraint, external runtimes, providers, schemas and non-default
security requirements. Default restrictive security declarations need no
machine observation; non-default requirements become explicit facts.

`SkillCompatibilityObservation` is an immutable input fact containing exact
subject/dependency identities, the analysis profile, exact requirement ID,
closed positive/negative status, observer/time/observation reference and an
optional evidence reference. It carries no payload, log, stack trace, path,
approval or trust decision. No observation store is introduced.

The reconciliation matrix is:

| Declared state | Observed state | Result |
|---|---|---|
| no conflict/no outstanding requirement | none | `DECLARED_COMPATIBLE` |
| requirements | all positive for this profile | `OBSERVED_COMPATIBLE` |
| requirements | any negative | `OBSERVED_INCOMPATIBLE` |
| requirements | missing fact | `UNKNOWN` |
| any | positive and negative for one requirement | `CONFLICTING_INFORMATION` |
| declared conflict | none/negative | declared or observed incompatible |
| declared conflict | positive | `CONFLICTING_INFORMATION` |

The service does not inspect the operating system, Python process, hardware,
environment variables, network or Sandbox. `analysis-profile:` is an abstract
typed reference supplied by the caller.

### Analysis request, result and completeness

`AnalyzeSkillDependenciesRequest` contains the exact subject, one abstract
analysis profile, immutable observations and an explicit catalog limit. Graph
input is deliberately absent. It has no store, callback, executor, mutable
dictionary, write idempotency or runtime preference.

`SkillDependencyAnalysis` contains requirement facts, every candidate fact,
compatibility requirement facts, used observation references, diagnostics,
incompleteness reasons and a convenience summary status. Independent
`complete`, `has_unsatisfied_required` and `has_conflicting_facts` dimensions
preserve simultaneous conditions. There is no analysis fingerprint because no
approved consumer requires one.

Completeness is false for possible catalog truncation/unavailability, lifecycle
unavailability/incompleteness/inconsistency or missing compatibility facts.
Missing information is never converted into a definitive incompatibility.

### Explicit graph boundary and cycles

Graph analysis is a separate invocation through
`SkillDependencyGraphAnalysisService`; common dependency analysis neither
accepts nor returns a graph. `SkillDependencyGraphInput` is bounded to 200
published records and 1,000 typed edges. It is never populated through implicit
recursive catalog traversal. Snapshot node identity is the exact
`PublishedSkillVersionId`; a graph edge is identified by declaration identity
plus its exact target. Nodes, edges and cycles are canonically ordered.

Repeated nodes, duplicate/conflicting edges, unknown endpoints, mismatched target
versions, inconsistent IDs and edges absent from the owner's supplied manifest
are rejected. Valid direct and longer cycles are detected. Self-dependency cannot
enter this boundary because the authoritative manifest prohibits it. A cycle is
blocking only when every edge is required; a cycle containing any optional edge
is advisory because that edge may be omitted by a future resolver. No install or
runtime order is produced.

### Errors, ports and public surface

The lifecycle port remains the minimal read-only projection shape that the Slice
6 service satisfies structurally. `SkillDependencyCatalogProvider` is the
analysis query port needed to carry an explicit completeness assertion; it does
not persist or reinterpret catalog facts. No compatibility store or graph source
is created because observations and graph boundaries are explicit inputs.

Public Slice 8 surface consists of semantic IDs, closed enums, facts,
observations, request/result, graph contracts, the narrow lifecycle provider,
analysis service and safe application errors. SemVer matchers, graph algorithms,
ordering helpers, diagnostic factories and fakes remain internal.

The analysis is deterministic and requires no write idempotency: identical facts
produce the same result, reordered inputs produce the same result and changed
facts change the derived result.

### Corrective-audit decisions

The dependency ID is the identity of one declaration occurrence inside one exact
owner publication. Its canonical projection contains the owner's complete
`PublishedSkillVersionId` (Skill ID, version, manifest fingerprint and content
fingerprint), target Skill ID, tagged exact-version/constraint value, reason and
cardinality. Consequently the same text in owner versions `1.0.0` and `1.0.1`
has different IDs, as does a hypothetically different fingerprint for the same
structural version. Original tuple position and all observation fields are
excluded. A graph edge has a different lifetime and is identified structurally
by this declaration ID plus the exact target publication; the dependency ID is
not misrepresented as an exact resolved edge ID.

Candidate classification is dimensional:

| Dimension | Values | Meaning |
|---|---|---|
| constraint | match, mismatch | structural SemVer fact only |
| lifecycle | eligible, deprecated, superseded, revoked, unavailable, incomplete, inconsistent | Slice 6 projection only |
| compatibility | declared/observed compatible or incompatible, unknown, conflicting | reconciliation of scoped facts |

A mismatching candidate has no fabricated lifecycle or compatibility result. A
matching revoked candidate remains in the result with `match`, `revoked` and its
independent compatibility fact. No enum combines these dimensions and no
candidate is removed because it is ineligible.

Required/optional and summary semantics are:

| Requirement | Condition | Requirement fact | Global dimension |
|---|---|---|---|
| required | no candidate or conclusive mismatch | unsatisfied | `has_unsatisfied_required=true` |
| required | all matching candidates revoked | unsatisfied | `has_unsatisfied_required=true` |
| required | compatibility/lifecycle/catalog unknown | incomplete | `complete=false` |
| required | observed incompatible | unsatisfied | `has_unsatisfied_required=true` |
| optional | unavailable or incompatible | unsatisfied + warning | does not set required blocking |
| optional | catalog/compatibility incomplete | incomplete | `complete=false` |
| any | conflicting observations | unsatisfied | `has_conflicting_facts=true` |

The closed `status` remains a convenience projection with precedence
conflicting, incomplete, unsatisfied, satisfiable. It is not the sole carrier of
meaning: diagnostics, requirement facts, completeness, conflict and blocking
dimensions coexist, so a conflict can remain visible while completeness is
false. Cycle facts live in the separate graph result and cannot erase these
dependency-analysis dimensions.

Compatibility remains fact combination, not trust policy. Negative observation
is never hidden; positive observation cannot override a declared structural
conflict; missing observation remains unknown; contradictory observers coexist
as conflicting information. Observer identity and timestamp are metadata, not
priority or freshness policy. There is no TTL, trust score, safety verdict or
implicit trusted observer.

The graph boundary is non-authoritative evidence supplied for bounded structural
analysis. Each node carries a self-validating published record and each edge must
correspond to a declaration in its owner's supplied manifest, match the exact
target and use the correct declaration ID. The snapshot does not claim that the
records came from a persistent store and contains no chosen candidate edge.
Slice 9 may consume normalized dependency facts and may independently use this
explicit graph analysis, but Slice 8 does not construct an exact graph from
unresolved declarations.

The public façade exposes only the immutable request/result facts, their closed
value enums, safe errors, the two narrow read-only provider contracts and the two
application services. Matching, compatibility combination, canonicalization,
cycle traversal, ordering and diagnostic factories remain module-internal.

### Boundaries, files and status

Created:

- `backend/synapse/skills/phase8_errors.py`
- `backend/synapse/skills/phase8_contracts.py`
- `backend/synapse/skills/phase8_models.py`
- `backend/synapse/skills/phase8_matching.py`
- `backend/synapse/skills/phase8_compatibility.py`
- `backend/synapse/skills/phase8_graph.py`
- `backend/synapse/skills/phase8_analysis.py`
- `tests/test_skills_phase8_dependencies.py`

Changed:

- `backend/synapse/skills/__init__.py`
- `tests/architecture/test_skills_boundaries.py`
- this document

Phase 1, persistence, installation, activation, lifecycle mutation, Repository
Runtime, Governance/Intelligence adapters, Private Evals, API, Commands,
composition, execution and Sandbox were not changed or started. Slice 9 was not
started. Backend remains **NOT READY**.

Quality gates after the corrective audit: Slice 8 **50 passed**; Slice 7 **34 passed**; Slice 6 **73
passed**; Slice 5 **23 passed**; Slice 4 **65 passed/1 platform skip**; Slice 3
**8 passed**; Slice 2 **88 passed**; Phase 1 **15 passed**; Skills boundaries
**15 passed**; architecture **147 passed**; Ruff **PASS**; Mypy Skills **PASS
for 34 files**. Authoritative Mypy retained the inherited **215 errors/58
files**, checked **546 files** and reported zero Skills error lines.

The governed graph remains **70 contexts/263 edges** with the official SCC
unchanged at **13 contexts/35 internal edges** and Skills outside it. The exact
runtime graph is **546 modules/1,707 edges/zero parse errors/zero non-trivial
SCCs**. Diff check passed with only pre-existing line-ending warnings.

Production Slice 8 contains zero occurrences of moving-version/choice,
progression, execution, process/network client or background operations.
`FilesystemRequirement`, `NetworkRequirement` and sandbox-profile occurrences
are typed Phase 2 declaration facts only; they do not inspect the machine.
`SAFE_MESSAGE` occurrences are fixed error-message constants, and “approved” in
the lifecycle-provider docstring identifies the previously approved Slice 6
projection. Phase 1 selection, installation, filesystem paths, execution
descriptors, trust text and random record IDs remain legacy compatibility code
and were not changed.

No file was staged and no commit, push or PR was performed.

**Skills Runtime Phase 2 — Slice 8 corrective audit APPROVED, backend NOT READY**

## 42. Slice 9 — governed deterministic dependency resolution

Slice 9 is the pure resolution authority over completed or explicitly incomplete
Slice 8 facts. It selects exact published identities according to a caller-supplied,
versioned policy and produces an immutable plan. It does not query a catalog,
install, activate, execute, persist, approve or grant trust.

### Existing facts and authority map

| Existing symbol | Slice 9 use | Risk controlled |
|---|---|---|
| `SkillDependencyAnalysis` | complete input fact set | correspondence is revalidated |
| `SkillDependencyRequirementFact` | requirement grouping | declarations are not merged |
| `SkillDependencyCandidateFact` | dimensional filtering | matching is not selection |
| `SkillDependencyCatalogPage` | indirect completeness source | no count heuristic |
| `SkillDependencyGraphSnapshot` | optional structural evidence | never used as implicit selection |
| constraint/lifecycle/compatibility enums | independent eligibility inputs | no combinatorial status |
| `SkillDependencyCardinality` | required/optional semantics | omissions stay explicit |
| `PublishedSkillVersionId` | exact selected identity | no structural fallback |
| `SkillVersionConstraint` | approved intersection input | no new syntax |

| Concern | Single authority | Input | Output |
|---|---|---|---|
| request validation | resolution service/models | exact subject, analysis, policy, profile | safe error or validated facts |
| completeness prerequisite | policy + service | analysis completeness dimensions | resolvable/incomplete result |
| requirement grouping | resolution service | immutable requirement facts | canonical groups by target Skill ID |
| constraint intersection | constraints module | exact/caret/bounded declarations | internal intersection or conflict |
| candidate filtering | selection module | candidate dimensions + policy | typed decision/rejections |
| policy evaluation | immutable policy | closed enums/limits | allowed resolution behavior |
| deterministic selection | selection module | selectable candidates | exact identity + rationale |
| group resolution | groups module | grouped views + policy | resolved/omitted/conflict facts |
| graph consistency | resolution service | optional Slice 8 snapshot | applicable cycle evidence |
| plan construction | resolution service | canonical facts | immutable plan |
| replay | pure value semantics | identical facts/policy | identical plan |

### Concept separation

Matching is only the Slice 8 structural constraint fact. Eligible adds lifecycle,
compatible adds compatibility facts, selectable applies the explicit Slice 9
policy, and selected is the exact identity recorded in the plan. A resolved
requirement references that selection. A shared resolution satisfies multiple
requirement IDs with one exact identity. Resolution conflicts are typed domain
facts. Installation, activation and execution plans do not exist in Slice 9.

### Request and explicit policy

`ResolveSkillDependenciesRequest` is frozen and contains the exact subject,
`SkillDependencyAnalysis`, mandatory `SkillDependencyResolutionPolicy`, a
`resolution-profile:` reference and an optional graph snapshot. It contains no
store, callback, executor, installer, arbitrary mapping or idempotency key.

There is no implicit/default policy. Every request supplies:

- policy version 1;
- single-version or multi-version mode;
- higher- or lower-SemVer preference;
- observed-only, declared-or-observed, or explicitly allow-unknown compatibility;
- denied/deprecated/deprecated-and-superseded lifecycle fallback;
- resolve-when-possible or omit optional dependencies;
- require-complete or allow-optional-incomplete behavior;
- explicit exact-prerelease permission;
- immutable validated limits.

The policy contains no callback, code, provider payload or arbitrary comparator.
Revoked and proven incompatible candidates are never selectable under any policy.

### Grouping, intersection and selection

Requirements are grouped canonically by target `SkillId` while retaining owner,
dependency ID, cardinality, reason, declaration and individual candidate facts.
Grouping never changes or persists the declarations.

The internal intersection handles exact versions, caret bounds including
major-zero, and inclusive/exclusive bounded ranges. Exact versions retain
prerelease/build identity. Exact-versus-range and partially overlapping ranges
are evaluated without inventing a serializable manifest constraint. Disjoint
ranges and structurally different exact builds conflict.

Single-version mode requires one exact identity to satisfy every required
requirement in a group. Optional requirements contribute coverage but may be
explicitly omitted. Multi-version mode resolves each requirement independently.
There is no implicit coexistence.

Selection ordering is policy-controlled and recorded:

1. required coverage;
2. optional coverage;
3. regular lifecycle before an explicitly enabled degraded fallback;
4. higher or lower SemVer precedence according to policy;
5. concrete version text;
6. exact publication identity.

Build metadata does not change SemVer precedence. Concrete text and exact identity
are deterministic tie-breakers, not claims that one build is superior. Range
requirements still exclude prereleases. Exact prereleases require both an exact
declaration and explicit policy permission.

### Compatibility, lifecycle and completeness

Declared/observed compatible candidates are treated only as allowed facts under
the selected compatibility mode. Unknown requires explicit permission.
Declared incompatible, observed incompatible and conflicting information are
always rejected. Observed compatible remains profile-scoped and grants no trust.

Deprecated and superseded versions are denied unless the policy explicitly
enables their fallback class. Regular lifecycle candidates precede degraded
candidates even when degraded fallback is enabled. Revoked is always rejected.

Required incomplete requirements never receive a definitive selection. With
`ALLOW_OPTIONAL_INCOMPLETE`, complete required groups may resolve while optional
incomplete requirements remain `UNRESOLVED_INCOMPLETE`. A globally strict policy
rejects any incomplete analysis. Catalog completeness is consumed from Slice 8
facts and is never inferred from candidate count.

### Plan, rationale, conflicts and status

The plan contains per-requirement outcomes, shared or independent resolved
dependencies, exact selected identities, policy version, lifecycle/compatibility
facts, degraded flags, typed rationale, conflicts, diagnostics, applicable graph
cycles and independent summary dimensions.

Optional outcomes are explicit: resolved, omitted-no-candidate,
omitted-conflict, omitted-policy or unresolved-incomplete. Required absence is a
blocking diagnostic rather than an exception.

Conflict taxonomy distinguishes constraint intersection, lifecycle eligibility,
compatibility, single-version incompatibility, graph cycle, incomplete facts,
search-limit exhaustion and no selectable candidate. Structural request,
analysis, graph or policy corruption remains a safe exception.

The convenience status is `RESOLVED`, `PARTIALLY_RESOLVED`, `UNRESOLVABLE`,
`INCOMPLETE` or `CONFLICTING`; detailed requirements, conflicts, completeness,
optional omissions and degraded-selection dimensions remain authoritative.

No plan ID/fingerprint was added because no approved Slice 10/13 consumer yet
requires durable identity. Plans depend only on supplied facts and policy, never
on clock, actor, process, machine, request key or input order.

### Graph and bounded search

The optional Slice 8 snapshot is revalidated as structural evidence. After exact
selection, only cycles whose exact nodes are in the proposed selection are
retained. Required-only cycles conflict; optional/mixed cycles remain advisory.
No resolved graph, installation order or execution order is produced. A future
transitive resolved graph remains reserved.

The search strategy is bounded deterministic group evaluation, not incidental
greedy traversal and not a generic SAT solver. It evaluates all supplied
candidates for each group, computes coverage, then applies the recorded policy
ordering. Limits cover requirements, candidates per requirement, groups, search
states, graph nodes/edges and diagnostics. Exceeding a policy limit returns an
explicit incomplete plan.

### Files, public surface and boundaries

Created:

- `backend/synapse/skills/phase9_errors.py`
- `backend/synapse/skills/phase9_policy.py`
- `backend/synapse/skills/phase9_constraints.py`
- `backend/synapse/skills/phase9_models.py`
- `backend/synapse/skills/phase9_selection.py`
- `backend/synapse/skills/phase9_groups.py`
- `backend/synapse/skills/phase9_resolution.py`
- `tests/test_skills_phase9_resolution.py`

Altered:

- `backend/synapse/skills/__init__.py`
- `tests/architecture/test_skills_boundaries.py`
- this architecture document

The public façade exports only policy values, request, immutable resolution facts,
plan, service and stable errors. Intersection structures, candidate filtering,
ordering, group state, factories and fakes remain internal.

Slices 1–8 do not import Slice 9 and were not changed semantically. No concrete
persistence, lifecycle transition, installation, activation, download, copy,
execution, API, Commands, Composition Root, Governance/Intelligence adapter,
Private Evals binding or Sandbox behavior was introduced.

Corrective audit after reconstruction hardened analysis correspondence: derived
eligible candidates and aggregate Slice 8 status flags are now revalidated, and
shared exact-candidate lifecycle/compatibility facts must agree across grouped
requirements. Typed rationale no longer reports a SemVer tie-break when optional
coverage or regular lifecycle already decided the selection. Regression cases
also make duplicate requirements, mixed cycles and the full supported
intersection boundary matrix explicit.

Quality gates: Slice 9 **65 passed**; Slice 8 **50 passed**; Slice 7 **34
passed**; Slice 6 **73 passed**; Slice 5 **23 passed**; Slice 4 **65 passed/1
platform skip**; Slice 3 **8 passed**; Slice 2 **88 passed**; Phase 1 **15
passed**; Skills boundaries **16 passed**; architecture **148 passed**; Ruff
**PASS**; Mypy Skills **PASS for 41 files**. Authoritative Mypy retained the
inherited **215 errors/58 files**, checked **553 files** and reported zero Skills
error lines.

The governed graph remains **70 contexts/263 edges** with the official SCC
unchanged at **13 contexts/35 internal edges** and Skills outside it. The exact
runtime graph is **553 modules/1,737 edges/zero parse errors/zero non-trivial
SCCs**. Diff check passed with only pre-existing line-ending warnings. Production
Slice 9 contains zero forbidden runtime/progression/search-policy terms from the
scope audit. No file was staged and no commit, push or PR was performed.

**Skills Runtime Phase 2 — Slice 9 implemented, module NOT IMPLEMENTED**

## 43. Slice 10 — neutral Governance and Intelligence bindings

### Corrective audit (2026-07-29)

This subsection supersedes the original Slice 10 identity, evidence,
multiplicity and graph claims below where they differ.

- `ExternalBindingRef` identifies the local semantic association. It does not
  identify an act performed by a binder.
- `ExternalBindingOccurrenceRef` identifies one local append-only act as the
  SHA-256 digest of the semantic binding ref, binder ref and caller-supplied
  `bound_at`.
- An exact retry replays the first occurrence. A different binder or
  `bound_at` is a legitimate additional occurrence, even when it has the same
  semantic binding ref.
- Governance evidence belongs to the immutable external decision identified by
  `GovernanceDecisionRef`. Skills neither duplicates evidence references nor
  treats a changed evidence list as a local update.
- `observed_at` is external fact metadata, may predate publication and is not
  local occurrence identity; a different value for the same occurrence is a
  divergent duplicate.
- Projection diagnostics describe only structural multiplicity:
  multiple authority, decision, decision-kind, policy, fact, fact-kind,
  profile or analysis references. They do not assert contradiction, current
  state, precedence, approval, trust or safety.
- A complete empty history is a normal state and has no missing-binding
  diagnostic. An incomplete history is explicitly marked and cannot be used to
  reconcile an append.
- Canonical occurrence ordering is `(bound_at, occurrence_ref)`. It is
  deterministic and never selects a current or winning binding.

The corrective graph audit separates runtime imports from typing-only imports:

| Graph | Modules/contexts | Edges | Parse errors | Non-trivial SCCs |
|---|---:|---:|---:|---:|
| official runtime context graph | 70 | 263 | 0 | 1 inherited SCC: 13 contexts/35 internal edges |
| exact runtime module graph | 561 | 2,190 | 0 | 0 |
| exact graph including `TYPE_CHECKING` | 561 | 2,266 | 0 | 4 SCCs/15 modules |

The four typing-inclusive SCCs contain 7 Private Evals modules, 4 delegation
modules, 2 execution-router/tool-intent modules and 2 multimodal/perception
modules. They are not runtime SCCs. The official runtime architecture metric
continues to exclude imports guarded by `TYPE_CHECKING`.

Slice 10 owns immutable local correspondence facts between an exact
`PublishedSkillVersionId` and opaque references produced by external
authorities. A reference is not a payload, truth assertion, approval, trust
grant or policy execution. Skills never imports or calls Project Governance,
Intelligence Boundary or Private Evals.

### Prior contract audit and family separation

| Existing symbol | Responsibility | Reused | Boundary decision |
|---|---|---:|---|
| `PublishedSkillVersionId` | exact structural version plus fingerprints | yes | mandatory binding subject |
| `SkillCatalogStore.get_version` | exact publication lookup | yes | publication prerequisite only |
| `SkillStoreWriteOutcome` | created/replay result | yes | shared append outcome |
| `SkillStoreQueryLimit` | bounded local read | yes | explicit service dependency |
| `SkillSemanticReference` | generic Phase 2 reference | no for Slice 10 fields | namespace is too broad |
| Phase 3 `SkillGovernanceBindingRecord` | legacy generic Governance ref/fingerprint | preserved, not reused | insufficient authority/policy/evidence typing |
| Phase 3 `SkillEvaluationBindingRecord` | legacy Evaluation result reference | preserved, not reused | reserved for Slice 11/Private Evals |
| Phase 3 `SkillBindingStore` | legacy Governance/Evaluation histories | preserved, not reused | changing it would create Phase 3→10 coupling |
| lifecycle decision/evidence refs | lifecycle progression evidence | no | lifecycle authority remains unchanged |
| Governance internal models | decisions/reviews/evidence | no | external context owns them |
| Intelligence internal models | egress/trust/information facts | no | external context owns them |

The Slice 10 `SkillExternalBindingStore` is therefore a new application port
with four type-safe methods: `append_governance`, `append_intelligence`,
`list_governance_for_version` and `list_intelligence_for_version`. It contains
no generic append, union binding DTO or Evaluation method. The legacy Phase 3
contract remains source-compatible and frozen.

| Binding family | External owner | Slice | Local purpose |
|---|---|---:|---|
| Governance decision | external Governance authority | 10 | exact reference correspondence |
| Intelligence fact/analysis | external Intelligence authority | 10 | exact fact/profile correspondence |
| Evaluation result/evidence | Private Evals | 11 | reserved; not implemented |

### Authority and trust boundaries

| Concern | Authority | Input | Output |
|---|---|---|---|
| reference syntax | Skills reference values | closed ASCII namespace | valid value or safe error |
| decision/fact meaning | external authority | opaque reference | not interpreted |
| subject correspondence | binding service + catalog port | exact identity | published record or safe error |
| binding identity | Skills | canonical semantic projection | deterministic binding ref |
| append/replay | local binding store port + service | immutable record | created/existing/conflict |
| history completeness | future adapter | bounded history | records plus explicit `complete` |
| ordering | Skills projection | local facts | `bound_at`, occurrence ref |
| structural multiplicity | Skills projection | all local facts | typed multiplicity diagnostics |
| approval/trust/current decision | external authority | — | never produced by Skills |

| Concept | Owner | Stored by Skills | Proven by reference |
|---|---|---:|---:|
| external reference | external authority; syntax owned locally | yes | only identity syntax |
| external decision/evidence/policy | Governance | no | no |
| external fact/analysis | Intelligence | no | no |
| binding fact | Skills | yes through a future adapter | yes, local correspondence only |
| local interpretation | none in Slice 10 | no | no |
| trust/approval | external authority | no | no |

### Neutral references and records

Slice 10 defines closed, bounded ASCII wrappers for authority, binder,
Governance decision/kind/policy, Intelligence fact/analysis/kind/profile,
semantic binding identity and occurrence identity. Values cannot contain URL/path separators,
credentials, arbitrary JSON, provider bodies or Unicode/control characters.

`SkillGovernanceBindingRecord` contains the exact version, decision and
decision-kind references, policy reference, external authority, binder,
binding ref, occurrence ref and UTC `bound_at`. It has no decision
payload, state machine, text rationale, trust score or progression flag.

`SkillIntelligenceBindingRecord` contains the exact version, fact reference,
optional analysis reference, semantic fact kind and profile, external authority,
binder, UTC `observed_at`/`bound_at`, binding ref and occurrence ref. It has no model output,
raw analysis, prompt, chain of thought, score or provider response.

Governance binding identity is SHA-256 over:

1. family `governance`;
2. exact published identity;
3. external authority;
4. decision reference;
5. decision-kind reference;
6. policy reference.

Intelligence binding identity is SHA-256 over:

1. family `intelligence`;
2. exact published identity;
3. external authority;
4. fact reference;
5. fact-kind reference;
6. profile reference;
7. optional analysis reference.

Binder and `bound_at` do not change the semantic binding identity; they create
the occurrence identity. A different binder or time therefore records another
legitimate local act. An exact retry returns the existing occurrence. Governance
evidence references are not stored because their semantic owner is the
external decision authority.

### Services, histories, projections and conflicts

`SkillGovernanceBindingService` and `SkillIntelligenceBindingService` validate
their frozen requests, require exact publication, check only timestamp/subject
correspondence, build the record, reconcile append-only replay and return typed
results. Neither service has an external read port because there is no approved
consumer requiring payload retrieval or remote validation.

Histories are family-specific values with `records` and `complete`. Adapters
must assert completeness; candidate count never infers it. Canonical ordering is
`bound_at` then occurrence ref. Projections retain canonical reference
collections and diagnose only incomplete history and structural multiplicity.
A complete empty history is normal. They do not choose precedence, infer a
current decision or characterize multiple opaque external facts as conflicts.

Publication is checked before history or append. Governance and Intelligence
`bound_at` cannot predate publication. An Intelligence observation may predate
publication but cannot follow binding. Bindings remain
historical if lifecycle later changes; Slice 10 does not read or mutate
lifecycle. Slice 9 intentionally has no plan identity, so no resolution-plan
binding was invented.

### Files, public surface and boundaries

Created:

- `backend/synapse/skills/phase10_errors.py`
- `backend/synapse/skills/phase10_refs.py`
- `backend/synapse/skills/phase10_models.py`
- `backend/synapse/skills/phase10_identity.py`
- `backend/synapse/skills/phase10_contracts.py`
- `backend/synapse/skills/phase10_projection.py`
- `backend/synapse/skills/phase10_governance.py`
- `backend/synapse/skills/phase10_intelligence.py`
- `tests/test_skills_phase10_bindings.py`

Altered:

- `backend/synapse/skills/__init__.py`
- `tests/architecture/test_skills_boundaries.py`
- this architecture document

The public façade exports only typed references, requests, records, histories,
projections, results, the store port, services and safe errors. Hashing,
canonicalization, projection builders, ordering helpers and test fakes remain
internal. Slices 1–9 do not import Slice 10.

No Governance/Intelligence/Private Evals adapter, concrete persistence,
SQLite, migration, restart recovery, UnitOfWork, CAS, API, Commands,
Composition Root, install, activation, lifecycle change, execution or Sandbox
behavior exists in Slice 10.

### Slice 10 quality evidence

- focused Slice 10 tests: `58 passed`;
- prior Skills slices: Slice 9 `65 passed`, Slice 8 `50 passed`, Slice 7
  `34 passed`, Slice 6 `73 passed`, Slice 5 `23 passed`, Slice 4
  `65 passed, 1 skipped`, Slice 3 `8 passed`, Slice 2 `88 passed` and
  Phase 1 `8 passed`;
- Skills boundary suite: `17 passed`;
- full architecture suite: `149 passed`;
- Ruff over `backend/synapse` and `tests`: passed;
- Mypy over the Skills package: `Success: no issues found in 49 source files`;
- fresh authoritative repository Mypy: `Success: no issues found in 561 source
  files`;
- official context graph: `70` nodes, `263` governed edges, one pre-existing
  SCC with `13` contexts and `35` internal edges; Skills is outside it;
- exact runtime module graph: `561` modules, `2,190` edges, zero parse errors
  and zero non-trivial SCCs;
- exact typing-inclusive module graph: `561` modules, `2,266` edges, zero parse
  errors and four SCCs containing `15` modules; Skills is outside every cycle;
- `git diff --check`: passed; staged files: zero;
- negative production search found only the safe-error constant name
  `SAFE_MESSAGE`; it found no execution, installation, activation, revocation,
  external runtime, Private Evals, payload, prompt, model output, subprocess,
  dynamic import, filesystem, network, clock, UUID or background behavior.

**Skills Runtime Phase 2 — Slice 10 implemented, module NOT IMPLEMENTED**

## 44. Slice 11 — Private Evals result and Evidence bindings

Slice 11 adds a reference-only boundary between an exact
`PublishedSkillVersionId` and immutable facts owned by Private Evals. Skills
does not import that bounded context, retrieve an eval payload, recalculate a
score, interpret a verdict or convert an eval into approval, trust, promotion,
rollback, installation, activation or lifecycle progression.

### Prior-contract audit and family decision

| Existing symbol | Responsibility | Reused | Boundary decision |
|---|---|---:|---|
| `PublishedSkillVersionId` | exact version plus manifest/content fingerprints | yes | mandatory binding subject |
| `SkillCatalogStore.get_version` | exact publication lookup | yes | publication prerequisite only |
| `SkillStoreWriteOutcome` | created/replay outcome | yes | neutral append result |
| `SkillStoreQueryLimit` | bounded history read | yes | explicit service dependency |
| Phase 3 `SkillEvaluationBindingRecord` | generic eval ref/fingerprint | no | preserved; lacks run/result/granularity/Evidence semantics |
| Phase 3 `SkillBindingStore` | legacy Governance/evaluation store | no | preserved; not extended |
| Slice 10 `ExternalBinderRef` | closed local binder identity | yes | neutral occurrence component |
| Slice 10 binding records/store | Governance and Intelligence families | no | unchanged and separate |
| Private Evals run/result/suite/case IDs | internal domain identities | audited only | never imported or copied |
| Private Evals baseline/comparison/regression IDs | analysis-owned identities | audited only | represented by local opaque refs |
| `EvalEvidenceProjection` and evidence-submission ports | external evidence artifacts/workflow | no | no payload or port dependency |
| Private Evals record/schema versions | persistence/domain formats | no | not duplicated by Skills |

The new `SkillPrivateEvalBindingRecord` and
`SkillPrivateEvalBindingStore` form a third bounded family:

| Binding family | External owner | Local record | Slice |
|---|---|---|---:|
| Governance | Governance authority | `SkillGovernanceBindingRecord` | 10 |
| Intelligence | Intelligence authority | `SkillIntelligenceBindingRecord` | 10 |
| Private Evals | Private Evals | `SkillPrivateEvalBindingRecord` | 11 |

### Authority and trust boundary

| Concern | Authority | Input | Output |
|---|---|---|---|
| reference syntax | Skills | closed ASCII namespace | typed opaque ref |
| Skill publication | catalog | exact identity | published record |
| run/result/verdict/Evidence meaning | Private Evals | opaque refs | never interpreted locally |
| binding identity | Skills | canonical structural tuple | deterministic binding ref |
| occurrence identity | Skills | binding, binder, caller time | deterministic occurrence ref |
| append/replay | store port and service | immutable record/history | created/replay/conflict |
| history completeness | future adapter | bounded records | explicit `complete` |
| ordering/projection | Skills | local history | deterministic structural facts |
| approval/trust/promotion | external authorities | — | never produced |

A reference is not a payload. A binding is not a verdict. A verdict reference
is not approval. Evidence references do not prove sufficiency. Comparison and
regression references do not prove improvement or rejection.

### References, granularity and Evidence

Slice 11 defines closed, bounded ASCII refs for run, result, verdict, Evidence,
suite, case, profile, baseline, comparison, regression, binding and occurrence.
They reject locator/path/query/fragment syntax, whitespace, Unicode, control
characters, JSON, credentials and raw external content. Errors use fixed
messages and never echo a supplied ref.

Granularity is explicit:

| Granularity | Required refs | Optional refs | Valid |
|---|---|---|---:|
| suite result | run, result, suite, profile | verdict, Evidence | yes |
| case result | run, result, suite, case, profile | verdict, Evidence | yes |
| comparison result | run, result, suite, profile, baseline, comparison | verdict, Evidence | yes |
| regression result | run, result, suite, profile, baseline, comparison, regression | verdict, Evidence | yes |
| run without result | — | — | no |
| verdict/Evidence without result | — | — | no |

Evidence uses alternative B: the referenced external artifacts are semantic
associations selected for this local binding. They are not assumed to be owned
by the result itself. Evidence refs are therefore canonicalized, duplicates
are rejected and the canonical tuple participates in binding identity.

Binding identity is SHA-256 over:

1. family `private-evals`;
2. exact published identity;
3. explicit granularity;
4. run and result refs;
5. optional verdict ref;
6. suite and optional case refs;
7. profile ref;
8. optional baseline, comparison and regression refs;
9. canonical Evidence refs.

Occurrence identity is SHA-256 over binding ref, binder ref and caller-supplied
`bound_at`. Binder/time changes create another local occurrence; they do not
change the semantic binding. `evaluated_at` is immutable external-result
metadata: it does not participate in binding identity, and a different value
for the same run/result pair is divergent history.

### Correspondence, histories and projections

The service performs the exact publication lookup before any history read or
append. `bound_at` cannot predate publication or `evaluated_at`. Evaluation may
predate publication because the exact fingerprinted candidate can be evaluated
before the immutable publication record exists; binding can occur only after
that exact publication is present.

Histories contain `records` plus explicit `complete`. Complete empty history is
normal. Incomplete history remains projectable but blocks append reconciliation.
Canonical ordering is `(evaluated_at, bound_at, occurrence_ref)` and never
chooses a latest, best, winning or current result.

Projections contain only canonical collections of granularities, run/result/
verdict/suite/case/profile/baseline/comparison/regression/Evidence/binder/
binding/occurrence refs and structural multiplicity diagnostics. They contain
no score, pass/fail, trust, approval, safety, improvement, regression finding,
current verdict or promotion recommendation.

### Files, boundaries and quality evidence

Created:

- `backend/synapse/skills/phase11_errors.py`
- `backend/synapse/skills/phase11_refs.py`
- `backend/synapse/skills/phase11_models.py`
- `backend/synapse/skills/phase11_identity.py`
- `backend/synapse/skills/phase11_contracts.py`
- `backend/synapse/skills/phase11_projection.py`
- `backend/synapse/skills/phase11_bindings.py`
- `tests/test_skills_phase11_bindings.py`

Altered:

- `backend/synapse/skills/__init__.py`
- `tests/architecture/test_skills_boundaries.py`
- this document

The façade exports only stable refs, values, records, histories, projections,
results, store port, service and fixed errors. Hashing, canonicalization,
ordering, multiplicity builders and fakes remain internal. Earlier slices do
not import Slice 11. Production Slice 11 imports no Private Evals, Governance,
Intelligence, API, Commands, bootstrap, Tools, storage, filesystem, network,
execution or Sandbox module.

Quality evidence:

- focused Slice 11 tests: `73 passed`;
- Slice 10: `58 passed`; Slice 9: `65 passed`; Slice 8: `50 passed`;
  Slice 7: `34 passed`; Slice 6: `73 passed`; Slice 5: `23 passed`;
  Slice 4: `65 passed, 1 skipped`; Slice 3: `8 passed`; Slice 2:
  `88 passed`; Phase 1: `8 passed`;
- Skills boundaries: `18 passed`; architecture suite: `150 passed`;
- Ruff over backend and tests: passed;
- Mypy Skills: `Success: no issues found in 56 source files`;
- fresh global Mypy: `Success: no issues found in 568 source files`;
- official runtime context graph: `70` contexts, `263` governed edges, zero
  parse errors and one inherited SCC of `13` contexts/`35` internal edges;
  Skills remains outside it;
- exact runtime graph: `568` modules, `2,226` edges, zero parse errors and zero
  non-trivial SCCs;
- exact typing-inclusive graph: `568` modules, `2,302` edges, zero parse errors
  and four SCCs/`15` modules; Skills is outside all four.

Residual implementation responsibility is limited to a future adapter that
must preserve append-only occurrence uniqueness and report history completeness.
No concrete adapter or persistence is part of Slice 11.

**Skills Runtime Phase 2 — Slice 11 implemented, module NOT IMPLEMENTED**

## Slice 12: governed execution handoff

Slice 12 constructs an immutable draft describing facts that may be submitted
to a future boundary. It does not authenticate the source authority, execute,
authorize, admit, install, activate, materialize or persist anything.

### Fact trust boundary and authorities

Slice 12 deliberately uses **pure value validation**. Records and projections
are supplied by a future trusted Composition Root. The service validates
internal structure, exact subject correspondence and canonical relationships,
but a Python caller can fabricate typed values. Consequently the draft never
labels these inputs verified, authenticated, physically present or available.
No duplicate read port was added for Slices 5–11.

| Concern | Real authority | Supplied fact | Slice 12 role |
|---|---|---|---|
| publication | Slice 5 catalog | exact publication record | validate manifest/fingerprints |
| installation registration/termination | Slice 7 | installation projection | validate registral consistency |
| physical custody/readability | future adapter/Sandbox | none | no claim |
| lifecycle/activation | Slice 6/7 | projection, completeness fact, activation | validate correspondence only |
| dependency resolution | Slice 9 | complete plan | create local canonical projection |
| dependency registration | future trusted composition | explicit selected registration fact | distinguish known/unknown/terminated |
| capabilities/security/resources | published manifest | immutable declarations | project without grant |
| external bindings | Slices 10/11 | projections, histories and selected occurrences | recompute structural refs |
| authorization | Governance | none | not implemented |
| admission/execution | future Sandbox/execution boundary | none | not implemented |

An installation record proves a registral association only. Current
registration, terminated registration, corrupted-registration observation and
history completeness are distinct. None proves bytes present, readable,
materialized, executable or physically corrupted.

### Draft, completeness and identity

`SkillExecutionHandoffService.build()` returns
`SkillExecutionHandoffBuildResult`, containing a
`SkillExecutionHandoffDraft` and its readiness. Incomplete prerequisites are
normal diagnostics, not exceptions. The object remains explicitly a draft even
when `handoff_structurally_complete` is satisfied; only then is it eligible for
submission to the next boundary. It is never called execution-ready.

`SkillExecutionHandoffId` is SHA-256 over semantic inputs only:

- format V1 and exact published identity;
- selected installation and activation IDs;
- semantic handoff requirements, excluding collection limits;
- registral installation and lifecycle facts;
- canonical resolution status, policy version, conflicts, omissions and cycle fact;
- selected dependencies, including lifecycle/compatibility/degraded facts;
- explicit dependency registration selections;
- capability, security, resource and tool declarations;
- runtime, profile and logical entrypoint declarations;
- selected external occurrences and supplied-history completeness.

Readiness and diagnostics are derived outputs and are excluded from identity.
Tests replace those outputs independently and reproduce the same ID, proving
there is no identity/artifact/readiness/diagnostic cycle. Human messages, clock,
UUID, actor observation, request correlation and mutable limits are also
excluded. Input collections are canonicalized before hashing.

V1 governs only the artifact structure. It does not version the manifest,
resolution policy, transport, Commands/Queries or future Sandbox protocol.

### Resolution and dependency registration

Slice 9 remains unchanged and still has no plan ID. The local resolution fact
preserves profile, policy version, status, completeness, required resolution,
optional omissions, degraded selections, conflict kinds and graph-cycle
presence. Selected dependencies preserve exact identity and fingerprints,
requirement IDs, policy version, lifecycle/compatibility status and degraded
state. Candidate ranking and textual rationale are excluded.

`dependency_registration_known` is registral terminology. It never means
materialization. Each registration names an exact resolved identity and an
explicit installation ID when registered. The current V1 policy applies one
explicit rule to every resolved dependency:
`require_resolved_dependency_registrations`. Slice 9 does not expose enough
cardinality information to invent separate required-versus-optional resolved
registration rules. Multiple candidates are never selected implicitly.

### Manifest declarations

Capabilities come from `manifest.capabilities` plus the selected execution
declaration's `required_capabilities`, with canonical deduplication. They remain
declared/required, never granted or runtime-available.

V1 has no independent permission model. The exact
`SkillSecurityDeclaration` is carried as security, not converted into
permissions. Network forbidden/required, external-processing behavior,
filesystem mode, egress, Sandbox-profile requirement and secret-reference
requirements retain their original constraint/declaration semantics.

Resources reuse `SkillResourceRequirement` in seconds, MiB and millicores from
the selected manifest execution declaration. They are declarations, not
allocation, reservation, scheduler policy or grant.

`SkillExecutionProfileRef` is a bounded opaque namespace and proves no profile
existence. The entrypoint is the exact `SkillLogicalPath` present in a manifest
execution declaration and its published content set. Absolute POSIX/Windows,
drive, UNC, traversal, import, command, shell and control syntax is rejected.
No content is opened.

### External occurrences, readiness and limits

For Governance, Intelligence and Private Evals, each selected occurrence must
exist in the supplied history for the exact subject. Slice 12 recomputes the
binding ref and occurrence ref from the record's semantic fields, binder and
time. Duplicates are rejected. Sorting is canonical only and never selects a
current, first, last or preferred occurrence. Complete history is enforced only
when the explicit binding policy requires it; content is never interpreted.

The ten readiness dimensions are:

1. publication correspondence;
2. installation registration correspondence;
3. lifecycle activation satisfaction;
4. dependency resolution;
5. dependency registration knowledge;
6. capability declaration completeness;
7. security declaration completeness;
8. execution profile presence;
9. external binding completeness;
10. structural handoff completeness.

States are `SATISFIED`, `INCOMPLETE`, `UNKNOWN` and `NOT_REQUIRED`. Revocation
is always blocking even when active selection is not required. Unknown
dependency registration blocks only when the explicit policy requires those
registrations. Structural cross-subject/corrupt inputs remain errors.

Configured limits must be integers from 1 through 5,000; booleans, zero,
negative and 5,001 are rejected. Actual collections may legitimately be empty.
Limits bound dependencies, capabilities, the one security declaration,
resources, selected external occurrences and diagnostics.

### Public surface and reserved work

The façade exports only stable request/draft/result/service contracts, format,
profile and handoff refs, policies/limits, the caller-supplied dependency
registration fact, readiness/diagnostics and the errors needed by a future
boundary. Canonical resolution/install/lifecycle/binding facts, hash helpers,
validators and narrow internal errors remain internal.

Commands/Queries are reserved to Slice 13 and were not started. Sandbox,
execution, concrete adapters, persistence, automatic installation/activation,
approval, trust and promotion remain unimplemented. Residual risks are source
authentication by composition, physical custody, profile existence,
permission/resource decisions, Governance authorization, Sandbox admission and
execution results.

**Skills Runtime Phase 2 — Slice 12 corrective audit implemented, module NOT IMPLEMENTED**
## Slice 13 — typed application boundary

The public `synapse.skills.application` submodule exposes explicit, immutable
commands and queries for the use cases already supported by the Skills domain.
Its handlers delegate to one approved domain service and return stable
application DTOs. Mutation results distinguish creation from idempotent replay;
read projections expose completeness as `complete`, `incomplete`, or `unknown`
instead of implying facts that the underlying bounded read cannot prove.

This boundary is intentionally not a generic command/query bus. It contains no
dispatcher, registry, transport, serialization protocol, composition root,
concrete persistence, provider execution, sandbox integration, approval logic,
or runtime wiring. Dependency analysis and resolution remain queries;
execution handoff construction remains a read-only structural query and does
not execute or authorize a skill. Raw histories are not separately exposed:
the typed projections retain the facts and completeness needed by this slice.

The existing `synapse.skills` root façade is unchanged. Consumers that need the
application contracts import `synapse.skills.application` explicitly. Backend
readiness remains **NOT READY** until a later, explicitly authorized integration
slice supplies composition and transport wiring.

### Slice 13 corrective audit

The roadmap is Slice 14 for concrete local persistence and migrations, Slice 15
for Phase 1 compatibility adapters, Slice 16 for the Composition Root and
delivery adapters, Slice 17 for E2E and failure recovery, and Slice 18 for final
audit and freeze. Composition Root work does not belong to Slice 14.

| Application operation | Existing authority | Kind |
|---|---|---|
| publish version | `SkillPublicationService.publish` | command |
| lifecycle transition | explicit `SkillLifecycleService` transition | command |
| install/terminate | installation and termination services | command |
| activate/deactivate | `SkillActivationService` | command |
| bind Governance/Intelligence/Private Eval facts | corresponding binding service | command |
| exact/list catalog | `SkillPublicationService` reads | query |
| lifecycle/installation projection | corresponding projection service | query |
| dependency/graph analysis and resolution | analysis/resolution service | query |
| binding projections | corresponding binding service read | query |
| structural handoff draft | `SkillExecutionHandoffService.build` | query |

Commands retain the approved Slice request as one immutable field. Each handler
coordinates one explicit authority and maps typed outcomes and safe error
categories without repeating request validation or domain transition rules.
Created and idempotent replay remain distinct; divergent duplicates remain
conflicts.

Queries call only existing read/build methods. Lifecycle, installation and
binding responses retain the complete typed domain projection, including
diagnostics and non-boolean states. Binding and installation completeness is
explicit; bounded catalog listing remains `UNKNOWN`, since an empty or
limit-sized tuple does not prove completeness. Dependency analysis, resolution
and handoff retain their domain results and diagnostics.

The public surface is the explicit `synapse.skills.application.__all__`.
Internal mappers and aliases are not exported, and the `synapse.skills` root
facade remains unchanged. There is no bus, mediator, dynamic registry,
reflection, auto-registration, framework, transport serialization, async
duplicate, concrete store, migration, compatibility adapter, Composition Root,
API/CLI, execution, or Sandbox integration.

Deferred work is persistence/migrations (Slice 14), compatibility adaptation
(Slice 15), composition/delivery (Slice 16), integrated recovery (Slice 17),
and freeze (Slice 18). The residual risk is integration-only: these contracts
are not wired to production delivery or durable adapters. Backend status remains
**NOT READY**.

## Slice 14 — concrete local persistence and migrations

Slice 14 adds the opt-in `synapse.skills.persistence` submodule. It uses one
dedicated local SQLite database supplied as an explicit absolute `Path`; it does
not discover a data directory and rejects relative paths, directories and
network shares. Each operation opens and closes its own connection. Connections
enable foreign keys, WAL, full synchronous writes, a bounded busy timeout,
`trusted_schema=OFF`, and disabled extension loading.

The persistence schema has an independent `SkillPersistenceSchemaVersion.V1`.
The forward-only `skills-schema-v1` migration has fixed SQL, a deterministic
SHA-256 checksum, explicit from/to versions and a caller-clock `applied_at`.
`skill_schema_metadata` and `skill_migration_history` are separate audit
authorities; `PRAGMA user_version` is not used as the authority. The migrator
rejects partial metadata, future schemas and checksum divergence and runs
integrity and foreign-key checks. It never resets or repairs data.

The V1 database contains publications, lifecycle records, installation records
and terminations, assignments and terminations, leases and terminations, legacy
Governance/Evaluation bindings, Slice 10 Governance/Intelligence bindings and
Slice 11 Private Eval bindings. It does not persist projections or application
DTOs. Typed identity/index columns accompany closed canonical JSON payloads;
pickle, repr and dynamic class loading are absent. UTC timestamps use canonical
ISO 8601 text with microsecond precision.

All domain record tables have triggers rejecting UPDATE and DELETE. Primary and
unique keys enforce record IDs, exact publication identity, structural
`(SkillId, SkillVersion)`, binding and occurrence identities. Local foreign keys
cover publication ownership and locally owned installation, assignment and
lease parents; opaque external references are stored as validated text and are
never resolved.

Every append owns one `BEGIN IMMEDIATE` transaction. Existing equivalent
canonical payloads return idempotent replay; divergent content under the same
semantic identity raises the stable store conflict, including retry after a
concurrent unique-key race. Reopening the database preserves records and replay.
No cross-store atomicity, global CAS, one-active-version rule, auto-deactivation
or global lifecycle guarantee is claimed.

Lifecycle, installation and Slice 10/11 binding histories use canonical indexed
ordering and `LIMIT requested + 1`, returning `complete=False` only when the
adapter observes an extra row. Catalog dependency enumeration performs the same
termination proof after approved semantic-version ordering. Legacy assignment,
lease and binding contracts return their exact bounded tuple contracts, which
do not contain a completeness field.

The public persistence façade exports only configuration/connection factory,
schema/migrator, concrete typed stores and safe persistence errors. SQL,
codecs, row mappers, triggers and transaction helpers remain internal. Domain,
application and the root Skills façade do not import persistence. Manual test
wiring proves compatibility without creating Composition Root behavior.

Operational backup/restore and failure recovery remain reserved to Slice 17.
Slice 15 owns compatibility adapters; Slice 16 owns Composition Root and
delivery; Slice 18 owns final audit/freeze. No compatibility adapter,
Composition Root, API/CLI, execution or Sandbox behavior was added.

**Skills Runtime Phase 2 — Slice 14 implemented, module NOT IMPLEMENTED**

### Slice 14 corrective durability audit

The corrective audit changed replay equivalence from raw JSON text equality to
decode, immutable typed-record reconstruction and record equality. Canonical
encoding remains sorted ASCII JSON with closed separators, but decoding also
rejects duplicate keys, floats, NaN/Infinity, payloads above 1 MiB and nesting
beyond 64 levels. Record constructors revalidate enums, references,
fingerprints, optional fields, tuples and UTC timestamps.

The V1 checksum authority now includes the stable migration ID, from/to
versions, normalized ordered schema steps, all constraints, eleven indexes and
twenty-six triggers. The migration state machine distinguishes an empty
database, partial metadata, valid V1 and unsupported future state. Successful
migration and explicit integrity checks verify the exact table set, column
order, primary/unique indexes, foreign-key counts, explicit indexes and
append-only triggers; recording version V1 alone is insufficient.

`SkillPersistenceIntegrityChecker.check()` is the explicit health entry point.
It runs schema verification, `PRAGMA integrity_check` and
`PRAGMA foreign_key_check`; ordinary reads do not run these expensive checks.
Missing tables, indexes or triggers, malformed records, migration divergence
and broken foreign keys fail closed without repair.

All append paths explicitly validate the local publication and typed parent
identity before INSERT, preventing a foreign-key failure from being mislabeled
as a divergent duplicate. Equivalent and divergent retries use the same key as
the database uniqueness constraint. A uniqueness race rereads, decodes and
compares the stored record. Lost responses therefore replay after restart
without relying on SQLite exception text.

Connections use a configurable finite busy timeout and do not retry internally.
A lock timeout becomes the safe persistence-unavailable error, which also
satisfies the existing `SkillStoreUnavailable` port contract. Commit success is
not described as rollback-capable: failure before commit rolls back on close;
failure after commit requires retry and semantic replay. Cross-store commit
uncertainty and global CAS remain outside the guarantee.

Legacy assignment, lease and binding reads remain explicitly bounded by the
caller-supplied `SkillStoreQueryLimit`. Their approved ports have no completeness
field, so no completeness assertion is invented; the residual risk is that a
caller cannot distinguish exact-limit completion from truncation. Slice 10/11
histories and dependency catalog pages retain `LIMIT + 1` completeness proof.

The path boundary rejects relative/empty paths, UNC/network shares, traversal,
Windows reserved device names, directories and symlinked parents. It creates no
directories and exposes no path in safe errors. SQL value inputs are
parameterized. The few dynamic identifiers are selected only from closed
internal constant sets; there is no public SQL, ATTACH, URI mode or extension
loading.

The persistence façade adds only the explicit integrity checker to the prior
configuration, migrator, schema, error and eight-store surface. Codec, migration
definition/checksum input, SQL, schema verifier, row mappers and transaction
helpers remain internal. Compatibility adapters remain reserved to Slice 15;
Composition Root/delivery remain Slice 16; operational recovery remains Slice
17. Backend status remains **NOT READY**.

## Slice 15: opt-in Phase 1 compatibility

Slice 15 adds `synapse.skills.compatibility` as an opt-in, unwired adapter
boundary. Phase 1, the root Skills facade, application, persistence, bootstrap,
API, CLI and runtime wiring are unchanged.

### Legacy inventory

| Legacy symbol/family | Responsibility | Active consumers | Decision |
|---|---|---|---|
| `SkillManifest`, package inspection | Filesystem package description | runtime, API tests | partial read-only |
| `SkillRegistry`, discovery, loader, resolver, `SkillsRuntime` | registry, loading and orchestration | bootstrap, API, commands, context, tests | remain Phase 1 |
| registration/install/uninstall | local package and record mutation | API/runtime tests | incompatible |
| lookup/list and descriptors | reduced `(SkillId, version)` views | API, commands, context | partial read-only |
| assignments and leases | agent/runtime allocation | bootstrap, ephemeral agents | remain Phase 1 |
| script descriptors/execution port | executable descriptors | bootstrap adapter | incompatible |
| capabilities/tools/providers | runtime requirements | resolver and commands | partial read-only |
| permissions/security dictionaries | mixed requirement/grant-like data | package/runtime | incompatible for writes |
| record stores and legacy errors | generic persistence/delivery contracts | runtime/bootstrap/tests | remain Phase 1 |

External production consumers are the Skills API router, bootstrap Skills
feature and execution adapter, command handlers, context loader and ephemeral
agent runtime. Acceptance/runtime tests import the same contracts. No consumer
is migrated by this slice.

### Compatibility and authority

| Legacy operation | Phase 2 authority | Decision |
|---|---|---|
| register/publish | verified publication request/service | incompatible |
| get/list | application catalog query | partial read-only |
| lifecycle state | application lifecycle query | partial read-only |
| activate/deactivate | installation handler with exact Phase 2 request | exact |
| install/download/load | installation facts versus custody/runtime | incompatible |
| capabilities | immutable manifest declarations | partial read-only |
| permissions/security | security requirements, never grants | incompatible for writes |
| dependencies | typed declarations and closed constraints | incompatible from arbitrary strings |
| execution descriptors | verified logical content references | incompatible |

Identity, manifest, publication, lifecycle, installation, dependencies,
security, persistence, replay and completeness remain owned by their approved
Phase 2 boundaries. Adapters only validate, delegate and project.

The direction is exclusively legacy consumer -> compatibility adapter -> Phase
2 handler. `LegacyCatalogAdapter.get_exact()` is operational with the approved
Slice 13 handler and retains the full exact identity. Reduced `get()` and
`list()` enumerate and require explicit COMPLETE; with the current Slice 13
handler they are intentionally unavailable because it reports UNKNOWN.
Complete test boundaries prove found, not-found and ambiguous behavior without
choosing first/latest/current.

`LegacyLifecycleAdapter` is read-only. It exposes the Phase 2-owned
`activation_state`, `selection_state`, `active`, `deprecated`, `revoked` and
active installation identity. The corrective audit removed the invented
`enabled` and `available` labels. Activation/deactivation passthrough methods
were also removed: accepting an already constructed Phase 2 request was not
legacy translation and offered no replay compatibility to a Phase 1 consumer.

Catalog results are accepted only when explicitly complete. Incomplete or
unknown pages raise a fixed compatibility-incomplete error. Application
not-found, dependency-unavailable, incomplete, conflict and invalid-input
families translate to fixed safe errors without payloads, paths, SQL or full
fingerprints.

Legacy manifests lack immutable verified content references, package
verification facts and exact manifest/content fingerprints. No publication or
manifest adapter is exposed. The ornamental checker and its unsupported error
were removed. Callable/module entrypoints, arbitrary constraints, permissions,
secrets, host/filesystem access and download/install/load assertions have no
compatibility code path.

The compatibility facade exports only the two read adapters, their read
models/outcomes and safe errors with real producers. Ambiguous identity remains
a lookup outcome, not an unused exception. Adapters open no database or
filesystem, generate no clock or UUID, import no package, and execute no Skill.

Residual risk is deliberate: the current application catalog handler reports
unknown completeness, so production list/get adaptation remains fail-closed
until a bounded query proves completeness. Reduced legacy identity may be
ambiguous. Phase 1 remains active until explicit future migration. Slice 16 owns
Composition Root selection and delivery. No production wiring, API/CLI,
execution or Sandbox work began.

**Skills Runtime Phase 2 — Slice 15 implemented, module NOT IMPLEMENTED**

### Slice 15 corrective compatibility audit

The audit classifies exact identity lookup as the only catalog operation that
can succeed through the current Slice 13 handler. Reduced identity lookup and
list are structural fail-closed guards until an approved query can prove
enumeration completeness. UNKNOWN never means absence, including empty pages or
pages containing a match. Exact lookup does not enumerate.

All compatibility models are read-only projections and cannot be reused as
write requests. Display name, summary, description and declared capability IDs
lose most Phase 2 manifest information, while `PublishedSkillVersionId` is
retained explicitly. Capability declarations are not grants; security and
secret references are not projected.

Using one reconciled AST configuration, the current official context graph has
74 contexts and 298 governed edges. It contains two existing SCCs:
`audio/multimodal/perception` with 4 internal edges, and the 26-context
operational SCC with 84 internal edges. Skills is outside both. The exact
runtime graph has 593 modules, 2,316 unique internal edges, zero parse errors
and zero non-trivial SCCs. Including `TYPE_CHECKING` gives 593 modules, 2,392
edges and four SCCs/15 modules, all outside Skills.

The earlier 588/2,361 and 594/2,321 reports did not use the same edge
normalization and cannot be compared as a delta. The reconciled figures above
resolve relative imports, deduplicate module-to-module edges and exclude
`TYPE_CHECKING` only for the runtime graph. The second official SCC was not
introduced by compatibility: compatibility adds no cross-context edge because
it remains inside Skills.

No Composition Root, delivery, API/CLI, execution, Sandbox, production wiring
or Phase 1 fallback was introduced. Backend status remains **NOT READY**.

## Slice 16: local Composition Root and delivery

Slice 16 adds the opt-in `synapse.skills.composition` package. It is not
imported by bootstrap, API, commands, workers, daemon, the root Skills facade
or any Phase 1 consumer.

`SkillsRuntimeConfiguration` is frozen and contains only the validated SQLite
configuration, explicit migration and integrity policies, compatibility mode
and binding-history limit. `MIGRATE_IF_NEEDED` invokes the approved V1
migrator; `REQUIRE_CURRENT` and `VERIFY_ONLY` require the existing schema.
Future schemas, checksum divergence and corrupt state fail construction with
safe errors. The approved migrator itself verifies schema and database
integrity; the composition-level `FULL` policy additionally records startup
integrity as checked, while `EXPLICIT_ONLY` requires the administrative
`verify_integrity()` call before health claims that dimension.

Construction order is configuration validation, connection factory,
migration/verification, optional explicit full integrity, eight concrete
stores, domain services, application handlers, optional read-only
compatibility and the local gateway. A failure returns no partial composition
and performs no repair. Every build creates an independent composition; there
is no singleton, global registry, connection singleton or service locator.

The eight store instances are retained privately. The catalog store also
serves the approved dependency-catalog port. Services are wired for
publication, lifecycle, installation/termination/activation, dependency
analysis/graph/resolution, Governance/Intelligence/Private Eval bindings and
handoff draft construction. All Slice 13 handler groups are available through
`SkillsApplicationGateway`.

Delivery here means a synchronous typed local boundary. It contains no HTTP,
RPC, CLI parsing, JSON mapping, Pydantic transport model, async mirror,
background work, logging or tracing. Raw stores, services, connection factory,
migrator and SQL are not exposed.

Compatibility has closed modes `DISABLED` and `READ_ONLY`. Disabled mode
exposes no adapter. Read-only mode exposes the approved exact catalog and
lifecycle views; reduced lookup/list retain their fail-closed UNKNOWN
completeness behavior. It never replaces or falls back to Phase 1.

Local runtime states are only READY and CLOSED; initialization/failure cannot
be observed because construction is atomic to the caller. Health separately
reports configuration, schema, migration, reachability, integrity,
foreign-key, application, compatibility and local state. This local READY does
not mean backend or execution readiness.

Stores open SQLite connections per operation. Immutable configuration,
stateless handlers and the persistence locking model permit concurrent
operations, but no claim of global transaction or total thread safety is made.
The composition lock protects close state. Close is idempotent; gateway,
compatibility, configuration and administrative access fail with a safe closed
error afterward, while health returns the closed state.

No production activation, API/CLI, Skill execution, Sandbox, package loading,
backup/restore or automatic recovery was added. Slice 17 remains responsible
for broad E2E and operational failure recovery. Backend status remains
**NOT READY**.

**Skills Runtime Phase 2 — Slice 16 implemented, module NOT IMPLEMENTED**

### Slice 16 corrective wiring and lifecycle audit

The corrective audit traced every concrete instance from configuration through
the gateway. One catalog store is shared by publication, lifecycle,
installation and dependency analysis. Lifecycle and installation stores are
injected only into their corresponding services. The external binding store is
shared by Governance and Intelligence; the Private Eval store remains
separate. Assignment, lease and legacy binding stores are constructed once and
retained for the complete approved persistence surface, but no application
handler currently consumes them.

Handoff remains the pure Slice 12 service: its query carries caller-supplied
publication, lifecycle, installation, dependency and binding facts. The
composition neither authenticates nor constructs those facts.

Migration health is now factual. `MIGRATE_IF_NEEDED` first verifies; only
`SkillPersistenceMigrationRequired` triggers V1 migration. Health records
`APPLIED` or `CURRENT_VERIFIED`, rather than inferring migration from configured
policy. REQUIRE_CURRENT and VERIFY_ONLY never call migrate. Checksum mismatch,
unsupported schema, migration-required, database unavailable, corruption and
generic migration failure have distinct safe composition categories.

`FAILED` was removed from public runtime state because atomic build never
returns a failed artifact. Public configuration access now returns a redacted
immutable view, and the input configuration has a path-redacted repr.
Reachability is probed by each open-composition health call. Integrity remains
NOT_CHECKED until the composition-level full or explicit check actually
completes.

Every gateway and compatibility operation checks the close guard at invocation;
captured gateway, compatibility and bound-method references therefore cannot
bypass close. Close is idempotent. An operation that passed the guard before a
concurrent close may finish; operations entering after close are rejected.
Close does not wait for in-flight calls. Independent compositions have
independent close state, including when they address the same SQLite file;
SQLite locking and caller coordination remain the concurrency boundary.

Failure after a committed V1 migration leaves the valid durable schema in
place. A later explicit build verifies CURRENT and completes without reset or a
second divergent migration. Fault injection remains test-only and no production
construction hook is exported.

## Slice 17: verified local recovery

Slice 17 adds `synapse.skills.recovery` as an explicit administrative boundary
outside the Composition Root. It covers only the local Skills SQLite database;
package bytes, external databases, secrets, logs, Sandbox state and executable
custody are excluded.

Recovery invariants are rollback before repair, no record-level editing, no
destructive reset, no restore from an unverified artifact, no overwrite of a
restore point, no restore while a supplied composition is open, no downgrade,
no checksum bypass and no automatic fallback, promotion or execution.

`SkillsRecoveryCoordinator` exposes create, verify and restore. Configuration is
frozen and path-redacted in repr; the caller explicitly supplies the source,
an existing local recovery directory, maximum size and an injected clock.
Network shares, relative directories, symlinks and bool limits are rejected.

Backup uses the SQLite Backup API, never a raw live-database copy. The caller
must provide a CLOSED Composition as its declaration of operational
exclusivity; external processes and writers cannot be detected, and SQLite's
consistent backup snapshot is the guarantee in their presence. A narrow local
lock serializes operations using one recovery directory. Staging is closed,
schema/integrity/FK verified, logically fingerprinted, size checked and fsynced
before publication. Backup bytes are published before their manifest; a crash
between them can leave only an invalid orphan, never a valid restore point.
Existing artifacts are never overwritten and reuse requires revalidation.

The logical fingerprint includes schema version, the V1 migration checksum and
all 13 closed record families. JSON payloads are decoded, canonically encoded,
ordered, length-delimited and separated by named family boundaries. Counts
come from the same read transaction. It excludes paths, rowids, insertion
order, indexes, page layout, free pages, WAL layout and clock. Restore point
identity is semantic content identity: format/schema, logical fingerprint,
checksum and counts. `created_at`, size, physical hash and backup reference are
occurrence/artifact binding, not semantic identity.

`backup:<sha256>` is exclusively the SHA-256 identity of the published file
bytes. A canonical adjacent manifest inseparably binds restore point identity,
logical fingerprint, physical hash/reference, schema/checksum, counts, size and
creation occurrence. Verification requires both files and compares all fields.
Restore copies through SQLite and verifies both physical and logical identity
again on same-filesystem target staging, closing the verify/copy TOCTOU window.

Restore verifies the backup again, creates and verifies target staging beside
the target, captures the exact current target through SQLite backup as a
size/physical-hash-bound private rollback artifact, then replaces. Keeping
restore and rollback staging in the target directory satisfies the
same-filesystem precondition. Atomicity is logical only on a local filesystem
whose replace operation supports atomic replacement; Windows sharing,
antivirus/indexer locks and hardware durability remain platform limitations.
The published backup and manifest are fsynced; directory fsync is applied where
the platform supports it.

After replacement, restore verifies the artifact, rebuilds the typed local
Composition and requires READY, current schema, reachable database, integrity,
foreign keys and constructed application. Failure closes any rebuilt
Composition and restores the previous whole database. Rollback is copied and
verified before its own replace. If rollback replace or verification fails,
private artifacts are preserved, target health is not asserted, and the only
public outcome is manual intervention without paths.

The restore result explicitly transfers ownership of the rebuilt Composition
to the caller and is a context manager with `close()`. The coordinator retains
no singleton or callback. Rebuild accepts only the typed runtime configuration,
uses the existing Composition Root directly and performs no API/bootstrap,
Phase 1 activation or Skills execution.

Restore points may be stale and are valid only when explicitly selected; there
is no latest/current/first selection or automatic retention. Recovery evidence
is external to the restored database and does not mutate restored content.

Lost-response recovery is semantic: reopen and retry yields CREATED or REPLAYED
according to durable facts; divergence remains conflict. Full-state tests bind
and restore all 13 record families as one database, including multi-family
rollback. Corruption recovery is never automatic: the caller closes and
explicitly restores a verified point.

The final Slice 17 audit exercises lost-response retry both before and after a
restore for publication, lifecycle, installation, installation termination,
activation, Governance, Intelligence and Private Eval. Publication, lifecycle
and Governance also exercise commit-uncertain reconciliation by semantic query
before retry; no caller-side commit flag is introduced.

Full-state recovery is compared through the Composition gateway and the
approved persistence ports. Exact publication, lifecycle and installation
projections, external binding histories, assignment/lease histories and legacy
Governance/evaluation histories are captured before backup and compared after
restore. Direct SQL remains supplementary fault setup, not the state authority.

Post-replace verification has distinct checks for target open, schema,
migration checksum, integrity, foreign keys, logical state, physical bytes,
Composition rebuild, health and configured compatibility. Each failure enters
the same verified rollback protocol. The private rollback binding records the
resolved target identity, physical and logical fingerprints, schema version,
migration checksum, all family counts and artifact size. It is verified before
target replacement and again on both rollback staging and restored target.
Rollback success additionally requires a rebuilt READY Composition with
healthy integrity/FK results; that temporary Composition is always closed.
Failure at any rollback copy, replace, open, schema, integrity, FK, logical,
rebuild or health step preserves surviving private artifacts and returns only
manual intervention.

Filesystem hardening rejects symlink and multiply-linked published artifacts
and targets. Restore staging and rollback files are constructed in the target
directory, so no cross-device rename is used; the immutable published backup
may live elsewhere and is copied into local staging. Symlink creation and
exclusive handle behavior remain platform/privilege dependent and are reported
as such by tests. The recovery lock is a narrow local artifact lock with
fail-closed collision semantics; it is not a distributed lock. Other processes
and handles remain the caller's operational-exclusivity responsibility.

Recovery result ownership is explicit: the caller closes the returned
Composition, directly or through the result context manager. Close is
idempotent, exceptions inside the context close it, and there is no finalizer or
coordinator-held singleton. Cleanup removes only operation-owned staging on
safe failures; rollback/manual-intervention artifacts are retained.

The recovery facade exports only operational contracts, result ownership,
physical/logical identities and errors with actual producers. Counts,
verification/action/rollback internals, filesystem helpers, path resolvers,
fingerprint helpers, arbitrary rebuild callbacks and test hooks remain private.
The final facade has 24 exports. The physical fingerprint value type and clock
protocol are internal implementation dependencies; callers observe the bound
physical identity through the restore point without constructing low-level
artifact primitives. The unreachable future-format error was removed; invalid
or unknown persisted manifests fail as invalid artifacts.

No production wiring, public API, interactive CLI, execution, Sandbox,
autonomous generation/evolution, approval, trust or promotion was added. Slice
18 remains reserved for final audit and freeze. Backend status is **NOT READY**.

**Skills Runtime Phase 2 — Slice 17 APPROVED**

## Slice 18: final audit and operational freeze

Slice 18 reconstructs and audits the complete Phase 2 implementation without
adding runtime capability. Slices 1 through 17 remain approved. Phase 1 remains
intact and coexists as a legacy runtime; it is neither imported as a fallback
by Phase 2 nor replaced by it.

### Final module summary

The 18-slice history is authoritative:

1. discovery and Phase 1 coexistence;
2. immutable manifests, values and exact identities;
3. append-only store contracts;
4. package/content verification without execution or trust;
5. immutable publication and catalog;
6. lifecycle, revocation and explicit transitions;
7. installation registration and activation facts;
8. dependency facts, analysis and graph;
9. deterministic dependency resolution;
10. external Governance and Intelligence bindings;
11. external Private Eval bindings;
12. non-authoritative execution handoff drafts;
13. typed Commands and Queries;
14. SQLite schema V1 and durable adapters;
15. fail-closed read-only compatibility;
16. explicit Composition Root and local delivery;
17. verified backup, restore and rollback;
18. final audit and freeze.

### Frozen invariants and public contracts

Manifests, content snapshots, publications and every append-only fact remain
immutable. Exact identities contain canonical semantic content and never path,
random UUID or occurrence clock unless time is itself part of the occurrence.
Publication, lifecycle, installation, activation, dependency resolution,
external authority binding and execution handoff remain separate authorities.
There is no implicit latest/current/best selection, automatic promotion,
in-place mutation, execution authorization or hidden fallback.

The approved public surfaces are frozen at the final audit baseline:

- `synapse.skills`: 272 exports, preserving the approved Phase 1 and Phase 2
  domain facade;
- `synapse.skills.application`: 48;
- `synapse.skills.persistence`: 25;
- `synapse.skills.compatibility`: 14;
- `synapse.skills.composition`: 24;
- `synapse.skills.recovery`: 24.

SQLite schema version **V1** and restore-point format **V1** are frozen.
Persistence has 15 tables (13 fact families plus schema and migration
metadata), 11 explicit indexes, 26 append-only triggers and one factual
migration identity/checksum. Restore points bind physical bytes, logical state,
schema/checksum, counts and immutable manifests.

### Operational guarantees and accepted limitations

The module provides deterministic validation, publication, histories,
dependency analysis/resolution, external binding, handoff drafting, durable
local persistence, read-only compatibility, explicit composition health and
whole-database recovery. It does not provide package custody, global
cross-store CAS, a global one-active-version policy, external-process recovery
coordination or universal filesystem durability.

Accepted limitations are:

- the caller supplies operational exclusivity for external SQLite processes;
- atomic replace and fsync guarantees remain filesystem/OS dependent;
- an orphan recovery lock requires explicit operator intervention;
- legacy Phase 1 contracts do not acquire invented completeness;
- reduced compatibility fails closed when the old shape cannot represent the
  Phase 2 fact;
- production wiring remains absent and the backend remains NOT READY.

### Future governed creation and evolution

A future Synapse-created Skill must enter through the same immutable package,
verification, publication, dependency, Private Eval and Governance contracts
as an externally supplied Skill. Future evolution creates a candidate version;
it never modifies a published version in place and never self-promotes.
Governed promotion requires a verified restore point, Private Evals, an
external Governance decision and human approval by default. Sandbox admission
and execution remain outside Skills authority.

The next documented bounded context is **Sandbox Execution Boundary**. It has
not started. Repository Runtime, generator/workspace tooling, package custody,
promotion and execution remain explicitly excluded.

### Frozen architecture baseline

- 602 Python modules;
- 74 governed contexts and 298 governed edges;
- official SCCs remain 3 contexts/4 edges and 26 contexts/84 edges;
- exact runtime graph has 2415 edges and zero non-trivial SCCs;
- typing-inclusive graph has 2492 edges and four pre-existing SCCs;
- Skills is outside every SCC.

Historical intermediate status lines above remain audit history. This section
is the final authoritative status:

**Skills Runtime Phase 2 — IMPLEMENTED / OPERATIONALLY COMPLETE / FROZEN**

The global backend remains **NOT READY**.
