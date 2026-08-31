# Synapse V3 — Auditoria de higiene, código morto e redução do repositório

**Data da coleta:** 2026-07-22
**Workspace:** `E:\Projetos\Synapse`
**Natureza:** auditoria somente-leitura, exceto pela criação deste relatório
**Estado de produto:** **backend NOT READY**; **Private Evals Runtime ainda não congelado**

Os números representam uma fotografia do workspace dirty, não uma árvore reproduzível do Git. Tamanhos em MB usam 1 MB = 1.000.000 bytes nas sínteses; listas originadas pelo PowerShell podem aparecer em MiB (1.048.576 bytes). Categorias se sobrepõem quando explicitamente indicado; estimativas de recuperação evitam dupla contagem.

## 1. Executive summary

O workspace ocupa **1.021.173.354 bytes** (aprox. 1,02 GB), com **15.100 arquivos** e **1.790 diretórios**. Apenas **158 arquivos / 659 KB** são rastreados; há **1.014 arquivos não rastreados / 245,6 MB** e **12.184 ignorados / 769,9 MB**. O principal volume é local ou recriável: ambientes Python (402,8 MB), `backend/build` + `backend/dist` (314,6 MB) e caches estáticos (34,4 MB, sem contar `__pycache__`). Dados de runtime/modelos somam pelo menos 230,4 MB e não podem ser tratados como descarte automático.

Há uma oportunidade conservadora de recuperar cerca de **752 MB** removendo futuramente ambientes, builds e caches comprovadamente recriáveis, mas somente após restore point e testes de recriação. Logs, áudio temporário, dados privados e modelos de voz exigem decisões de retenção/ownership; incluí-los elevaria o potencial condicional para aproximadamente **986–996 MB**, o que **não é uma recomendação de remoção**.

Nenhum código foi provado como `CONFIRMED DEAD`. Dois candidatos merecem investigação: `notifications/console_provider.py` (`PROBABLY DEAD`) e `speech_adapters/interfaces.py` (`CONTRACT-ONLY`, sensível ao grafo). Shims de `api`, `commands`, `chat` e `core` continuam ativos. A remoção dirty do antigo `synapse.communication` parece uma migração intencional, mas deve ser validada e registrada como lote atômico.

O Private Evals possui 56 arquivos Python, está amplamente untracked e foi preservado integralmente. Ruff, Mypy direcionado e testes arquiteturais passaram; o Mypy global falhou com 215 erros em 58 arquivos. Portanto a higiene não altera o estado: **NOT READY**.

## 2. Tamanho e contagem atuais

| Path | Size | Files | Git status | Candidate category |
|---|---:|---:|---|---|
| Workspace | 1.021.173.354 B | 15.100 | mixed/dirty | mixed |
| `.git` | 5.022.397 B | 1.752 | Git metadata | TOOLING / protected |
| `.venv` | 373.317.583 B | 6.507 | ignored | LOCAL ENVIRONMENT |
| `.venv-release` | 29.472.587 B | 3.619 | ignored | LOCAL ENVIRONMENT |
| `backend` | 325.366.707 B | 2.130 | tracked + modified + untracked + ignored | SOURCE + BUILD ARTIFACT |
| `data` | 230.494.395 B | 117 | tracked + untracked + ignored | RUNTIME/PRIVATE DATA |
| `.mypy_cache` | 34.099.429 B | 18 | ignored | REGENERABLE CACHE |
| `tests` | 8.205.874 B | 600 | tracked + untracked + ignored | TEST SOURCE + CACHE |
| `docs` | 6.376.862 B | 292 | tracked + untracked | DOCUMENTATION |
| root logs (`*.log`) | 8.064.092 B | 35 | untracked | TOOL OUTPUT / possibly private |

Foram contados 1.790 diretórios. A extensão mais volumosa foi `.dll` (349,2 MB); em seguida `.bin` (220,8 MB), `.pyd` (172,4 MB), `.exe` (65,2 MB), `.py` (62,9 MB, inflado por ambientes) e `.db` (34,1 MB, essencialmente cache Mypy).

## 3. Tamanho da `.git`

`.git` ocupa **5.022.397 bytes**, aproximadamente **0,49%** do workspace. Não é alvo de limpeza. A presença de objetos com nomes internos `tmp_obj_*` não autoriza ação: são implementação do object database e ficam expressamente protegidos.

## 4. Top-level por tamanho

| Path | Bytes | Files | Share aproximado | Classificação dominante |
|---|---:|---:|---:|---|
| `.venv` | 373.317.583 | 6.507 | 36,6% | ambiente local |
| `backend` | 325.366.707 | 2.130 | 31,9% | fonte + build |
| `data` | 230.494.395 | 117 | 22,6% | runtime/modelos/private data |
| `.mypy_cache` | 34.099.429 | 18 | 3,3% | cache |
| `.venv-release` | 29.472.587 | 3.619 | 2,9% | ambiente local de release |
| `tests` | 8.205.874 | 600 | 0,8% | testes + pycache |
| `docs` | 6.376.862 | 292 | 0,6% | documentação |
| `.git` | 5.022.397 | 1.752 | 0,5% | histórico Git |
| demais arquivos/diretórios de raiz | ~8,9 MB | ~65 | <1% | logs, lockfile, áudio, configs |

## 5. Maiores arquivos

Os 100 maiores arquivos foram medidos. A tabela abaixo preserva a lista em ordem; estado e ação são consolidados por prefixo: `.venv*` = ignored/local env; `backend/build|dist` = ignored/build; `.mypy_cache` = ignored/cache; `data/voice/models` = untracked/runtime model; `data/logs` = ignored/runtime/private; docs e logs de raiz = untracked.

| # | MiB | File |
|---:|---:|---|
| 1 | 138,49 | `data/voice/models/faster-whisper/.../base/.../model.bin` |
| 2 | 72,04 | `data/voice/models/faster-whisper/.../tiny/.../model.bin` |
| 3–4 | 56,55 cada | `.venv/.../ctranslate2.dll`; `backend/dist/.../ctranslate2.dll` |
| 5 | 30,81 | `.venv/Scripts/ruff.exe` |
| 6–7 | 19,46 cada | OpenBLAS em `backend/dist` e `.venv` |
| 8 | 18,89 | `.venv/.../__mypyc.cp312-win_amd64.pyd` |
| 9–10 | 18,37 cada | `avcodec` em `backend/dist` e `.venv` |
| 11–12 | 17,14 cada | `onnxruntime_pybind11_state.pyd` em build e env |
| 13–14 | 16,52 cada | `onnxruntime.dll` em build e env |
| 15–16 | 13,71 cada | `synapse_backend.exe` em `dist` e `build` |
| 17 | 13,38 | `backend/build/.../synapse_backend.pkg` |
| 18 | 13,35 | `backend/build/.../PYZ-00.pyz` |
| 19–20 | 12,16 cada | `libx265` em build e env |
| 21–22 | 9,45 cada | `cryptography/.../_rust.pyd` em env e build |
| 23–24 | 8,98 cada | `hf_xet.pyd` em env e build |
| 25 | 7,53 | `.venv/.../PIL/_avif...pyd` |
| 26–27 | 7,32 cada | `libSvtAv1Enc` em env e build |
| 28–29 | 7,21 cada | `tokenizers.pyd` em env e build |
| 30 | 6,65 | `backend/dist/.../python312.dll` |
| 31 | 5,66 | `backend/dist/.../libcrypto-3-x64.dll` |
| 32–33 | 5,62 cada | `avfilter` em build e env |
| 34–36 | 5,01 cada | `pydantic_core` em `.venv-release`, build e `.venv` |
| 37 | 4,14 | `data/logs/events.jsonl` |
| 38 | 4,13 | `.mypy_cache/3.12/cache.4.db` |
| 39–40 | 3,71 cada | NumPy `_multiarray_umath` em env e build |
| 41 | 3,39 | `backend/build/.../xref-synapse_backend.html` |
| 42 | 3,16 | `.mypy_cache/3.12/cache.3.db` |
| 43–44 | 2,71 cada | `avformat` em env e build |
| 45 | 2,66 | `.mypy_cache/3.12/cache.10.db` |
| 46–47 | 2,54 cada | `libstdc++` em env e build |
| 48 | 2,51 | `.venv/.../PIL/_imaging...pyd` |
| 49–50 | 2,48 cada | `libvpx` em build e env |
| 51 | 2,43 | `docs/audit/current-dependency-graph.json` |
| 52 | 2,35 | `.venv/.../ast_serialize.pyd` |
| 53–54 | 2,16 cada | `libx264` em env e build |
| 55–56 | 2,16; 2,14 | `.mypy_cache/.../cache.5.db`; `cache.1.db` |
| 57–58 | 2,10 cada | tokenizer dos modelos tiny e base |
| 59 | 2,07 | `.venv/.../PIL/_imagingft...pyd` |
| 60–61 | 2,04 cada | `libdav1d` em build e env |
| 62–68 | 2,00–1,81 | sete bancos `.mypy_cache/3.12/cache.*.db` |
| 69–70 | 1,93 cada | `swscale` em build e env |
| 71–72 | 1,66; 1,55 | dois bancos Mypy |
| 73–74 | 1,54 cada | `libiomp5md.dll` em env e build |
| 75 | 1,50 | `backend/dist/.../sqlite3.dll` |
| 76–78 | 1,47–1,38 | três bancos Mypy |
| 79 | 1,30 | `backend/dist/.../ucrtbase.dll` |
| 80–81 | 1,27 cada | `base_library.zip` em build e dist |
| 82 | 1,22 | banco Mypy |
| 83–84 | 1,19 cada | `silero_vad_v6.onnx` em build e env |
| 85–88 | 1,09 cada | `avutil` e `libiconv` duplicados em env/build |
| 89 | 1,07 | `backend/dist/.../unicodedata.pyd` |
| 90–96 | 0,92–0,74 | sete logs pytest na raiz |
| 97–98 | 0,73 cada | OpenAPI after/before em `docs/validation` |
| 99–100 | 0,72 cada | `libwebp` em build e env |

Conclusão: a cauda dos 100 maiores comprova duplicação física esperada entre ambiente e pacote PyInstaller; não comprova duplicação arquitetural. Modelos e logs têm riscos de retenção distintos.

## 6. Maiores diretórios

Os 100 maiores diretórios foram medidos recursivamente. Como pais incluem filhos, seus tamanhos não devem ser somados. Os grupos dominantes e a cauda do top 100 são:

| Rank/faixa | Path/group | Size | Files | Interpretação |
|---|---|---:|---:|---|
| 1 | `.venv` | 373,3 MB | 6.507 | ambiente local |
| 2 | `.venv/Lib/site-packages` | 338,9 MB | 6.458 | dependências instaladas |
| 3 | `backend` | 325,4 MB | 2.130 | fonte + build |
| 4 | `backend/dist/synapse_backend` | 266,1 MB | 872 | pacote PyInstaller |
| 5 | `backend/dist/.../_internal` | 251,7 MB | 871 | dependências empacotadas |
| 6 | `data` | 230,5 MB | 117 | runtime/private/models |
| 7–12 | `data/voice/models` e seus diretórios base/tiny/snapshots | 226,1–75,5 MB | 4–13 | cache/modelos de voz |
| 13–18 | árvores `av.libs`, `ctranslate2`, `onnxruntime` em env/dist | 65,6–35,3 MB | mixed | duplicação de empacotamento |
| 19 | `backend/build` | 48,5 MB | 17 | build PyInstaller |
| 20 | `.venv/Scripts` | 34,4 MB | mixed | executáveis locais |
| 21 | `.mypy_cache` | 34,1 MB | 18 | cache regenerável |
| 22 | `.venv-release` | 29,5 MB | 3.619 | ambiente local de release |
| 23 | `.venv-release/Lib/site-packages` | 28,8 MB | mixed | dependências locais |
| 24 | `backend/synapse` | 10,7 MB | 1.236 | fonte + pycache |
| 25 | `tests` | 8,2 MB | 600 | testes + pycache |
| 26 | `docs` | 6,4 MB | 292 | documentação/evidência |
| 27 | `tests/__pycache__` | 5,9 MB | 306 | cache regenerável |
| 28 | `.git` | 5,0 MB | 1.752 | protegido |
| 29 | `data/logs` | 4,34 MB | 1 | runtime/private log |
| 30 | `docs/validation` | 3,08 MB | mixed | evidência histórica |
| 31 | `docs/audit` | 2,68 MB | mixed | grafos/relatórios |
| 32–100 | subárvores de packages, build, contexts, caches e docs | <2,7 MB cada | mixed | ver autoridade pelo prefixo |

A apresentação consolidada evita a falsa impressão de que 100 diretórios aninhados são 100 oportunidades independentes. O inventário completo foi usado na classificação, mas não foi persistido como segundo artefato, pois este relatório é a única alteração autorizada.

## 7. Tracked, untracked, ignored e estado Git

Branch: `backend-freeze-cleanup`. HEAD: `8196eb11c34442af563b20082bc1666755f4d8a9` (`feat: add scheduler recurring jobs`, 2026-06-19T13:39:49-03:00).

| State | Files | Size aproximado | Observação |
|---|---:|---:|---|
| tracked | 158 | 659 KB | autoridade Git muito menor que o workspace |
| modified tracked | 85 | incluído acima | preservar; estado dirty material |
| untracked | 1.014 | 245,6 MB | inclui Private Evals, docs, testes e modelos |
| ignored | 12.184 | 769,9 MB | ambientes, builds, caches e runtime |
| staged | 0 | 0 | nenhum |
| deleted tracked | 8 | small | antigo domínio communication + ADR + teste |
| renames | 0 | 0 | nenhum detectado |

Deletados no working tree, sem correção nesta auditoria: os seis arquivos de `backend/synapse/communication/`, `docs/adr/0017-communication-runtime.md` e `tests/test_communication_runtime.py`.

Private Evals ainda não rastreado explicitamente: `backend/synapse/private_evals/` (todos os 56 `.py`), `docs/architecture/private-evals-runtime.md`, `tests/architecture/test_private_evals_boundaries.py` e `tests/test_private_evals_commands.py`. Outros testes de Private Evals estão sob os grupos untracked de `tests/` e devem ser preservados pela listagem completa futura.

## 8. Núcleo oficial

| Path | Purpose | Current authority | Referenced by | Required? |
|---|---|---|---|---:|
| `backend/synapse/` | implementação backend | código corrente no workspace | bootstrap, testes, API | sim |
| `backend/synapse/bootstrap/` | composition/wiring atual | código corrente | aplicação e testes | sim |
| `backend/synapse/contracts/` + contratos por contexto | boundaries | fonte + architecture tests | múltiplos contexts | sim |
| `tests/` | comportamento e regressão | suíte corrente dirty | pytest | sim |
| `tests/architecture/` | boundaries/grafos/SCC | guardrail corrente | CI/local | sim |
| `docs/architecture/` | arquitetura declarada | autoridade documental, com drift pontual | engenharia | sim |
| `docs/adr/` | decisões históricas | histórico de decisão | arquitetura | sim |
| `docs/rfcs/`, `docs/plans/`, templates | propostas/planos | vigente caso a caso | processo | revisão manual |
| manifests em `data/config/provider_plugins/` | provider discovery/config | runtime local | bootstrap/plugin loading | sim |
| `backend/synapse/migrations/`, `data/migrations/status.yaml` | evolução de schema/estado | código + estado | runtime | sim |
| `pyproject.toml` | dependências/tooling | autoridade de declaração | uv/build/tools | sim |
| `uv.lock` | lock de dependências | estratégia indicada pelo README, mas untracked | uv | preservar/regularizar |
| `Dockerfile`, `docker-compose.yml` | packaging/deployment | tooling atual aparente | operadores | manter/revisar |
| `README.md`, `ROADMAP.md` | entrada e ponte | supporting; métricas parcialmente stale | usuários | sim, documentar drift |

Não foram encontrados requirements alternativos, `setup.py` ou configuração de CI. `apps/` está vazio; a aplicação Electron descrita como planejada não existe na árvore atual.

## 9. Ambientes locais

`.venv` e `.venv-release` totalizam **402.790.170 bytes / 10.126 arquivos**. São ambientes distintos (desenvolvimento e packaging), mas ambos recriáveis em princípio. A remoção futura só é segura após provar `uv sync --extra dev`, reconstrução do ambiente de release e execução dos gates. Nenhum `node_modules` ou outro `venv` top-level foi encontrado.

## 10. Caches

| Group | Size/files | Action |
|---|---:|---|
| `.mypy_cache` | 34,10 MB / 18 | SAFE TO REMOVE após registrar falha baseline |
| `.pytest_cache` | 0,21 MB / 5 | SAFE TO REMOVE |
| `.ruff_cache` | 0,05 MB / 15 | SAFE TO REMOVE |
| todos `__pycache__` | 32,98 MB / 2.355 em 310 dirs | SAFE TO REMOVE por escopo; há sobreposição com env/build |
| `backend/synapse_v2.egg-info` | ~23 KB / 5 | BUILD METADATA, regenerável |

## 11. Builds

`backend/dist` ocupa 266,10 MB / 872 arquivos e `backend/build` 48,53 MB / 17, totalizando **314,63 MB / 889**. São outputs PyInstaller ignorados. O executável e DLLs duplicam dependências do ambiente por desenho. A ação é `SAFE TO REMOVE` apenas depois de registrar receita, reconstruir e fazer smoke test do pacote; não misturar com mudanças de fonte.

## 12. Runtime data

`data/voice/models` ocupa 226,09 MB / 13 arquivos e contém modelos third-party necessários ao caminho de voz offline. `data/logs/events.jsonl` tem 4,34 MB. Configurações, estado de migrations, agents, conversations, multimodal e perception são pequenos, mas semanticamente importantes. Ação: KEEP ou MIGRATE THEN REMOVE conforme ownership, download determinístico e política de retenção.

## 13. Private data

| Path/group | Type | Size | Risk | Recommended action |
|---|---|---:|---|---|
| `data/logs/events.jsonl` | event log | 4,34 MB | conteúdo operacional/possível PII | MUST PRESERVE LOCALLY; SECURITY REVIEW |
| `data/conversations/**` | conversation state | small | conteúdo de usuário | MUST PRESERVE LOCALLY |
| `data/agents/**` | memory/inbox/soul state | small | estado pessoal/privado | HISTORY REVIEW REQUIRED |
| `data/multimodal/**`, `data/perception/**` | provider/user observations | small | private payloads | MUST PRESERVE LOCALLY |
| `tmp_voice_backend_test.wav` | áudio untracked | 0,216 MB | mídia potencialmente privada | SECURITY REVIEW REQUIRED |
| `.env.example` | template sem segredo confirmado | 192 B | baixo | KEEP |

Nenhum valor sensível é reproduzido neste relatório. A varredura por padrões não encontrou literal de credencial de produção confirmado; resultados em enums/test fixtures não foram tratados como segredo real. Certificados dentro de dependências instaladas são parte de packages ignorados.

## 14. Código morto confirmado

**Nenhum item atingiu o padrão `CONFIRMED DEAD`.** Ausência de import textual, isoladamente, não é prova suficiente diante de bootstrap, reflection, registries, scanners e APIs externas.

## 15. Código provavelmente morto

| Symbol/path | Evidence of non-use | Dynamic/reference risk | Classification | Proposed action |
|---|---|---|---|---|
| `backend/synapse/notifications/console_provider.py` / `ConsoleNotificationProvider` | zero imports de produção/teste no grafo AST; sem wiring encontrado; apenas docs mencionam | import externo/manual ainda possível | PROBABLY DEAD | REMOVE ONLY AFTER TESTS e checagem de API pública |

## 16. Legacy ainda ativo

| Path | Evidence | Classification | Action |
|---|---|---|---|
| `backend/synapse/api/routes.py` | importado por `api/__init__` e muitos testes | LEGACY BUT ACTIVE | KEEP BUT DOCUMENT |
| `backend/synapse/commands/runtime.py` | façade exportada e usada | LEGACY BUT ACTIVE | KEEP |
| `backend/synapse/chat/runtime.py` | composto no bootstrap e testado | LEGACY BUT ACTIVE | KEEP BUT DOCUMENT |
| `backend/synapse/core/app.py` | boundary de compatibilidade usada por testes | LEGACY BUT ACTIVE | KEEP |
| `backend/synapse/core/model_router.py` | compatibility boundary com consumidores | LEGACY BUT ACTIVE | KEEP |
| `backend/synapse/core/__init__.py` | export público e exclusão consciente do grafo | LEGACY BUT ACTIVE | KEEP |

## 17. Contract-only/reserved modules

`backend/synapse/speech_adapters/interfaces.py` não apresentou consumidor Python direto, mas é citado pela documentação de estabilização e seus imports afetam scanners/grafos. Classificação: **CONTRACT-ONLY**, não morto. Ação: `MIGRATE THEN REMOVE` somente após provar que todos os adapters consomem `audio.contracts`, atualizar a autoridade documental e validar grafos/SCC.

## 18. Módulos órfãos

O scan AST de 510 módulos encontrou apenas os dois candidatos descritos nas seções 15 e 17 entre módulos não-`__init__` sem inbound de produção e sem imports de testes. Não foram encontrados packages inteiros órfãos nem exports órfãos conclusivos. Marcadores `TODO` (4 arquivos), `FIXME` (2), `deprecated` (9), `legacy` (63), `compatibility` (88) e `remove` (91) são sinais de revisão, não prova de orfandade.

## 19. Duplicações arquiteturais

| Concept | Current authority | Duplicate paths | Risk | Proposed action |
|---|---|---|---|---|
| agent communication | `backend/synapse/agents/communication.py` aparente | antigo `synapse/communication/` está deleted | migração dirty incompleta | validar e registrar lote atômico |
| speech contracts | `audio.contracts` aparente | `speech_adapters/interfaces.py` | quebra de boundary/grafo | definir autoridade, migrar, depois remover |
| dependency graph baseline | teste/grafo executado agora | `docs/audit/current-dependency-graph.json` e SCC históricos | baseline stale | regenerar apenas em lote aprovado; marcar data |
| OpenAPI evidence | gerador/API corrente | before/after em `docs/validation` | volume e obsolescência | ARCHIVE/CONSOLIDATE índice |
| roadmap entry | `docs/roadmap.md` | `ROADMAP.md` é ponte, não cópia | baixo | KEEP |
| env vs packaged dependencies | `pyproject.toml` + `uv.lock` | `.venv`, `.venv-release`, `dist` | duplicação física esperada | não consolidar como código |

Não foi detectada autoridade dupla conclusiva para DTOs, enums ou stores que justifique consolidação automática.

## 20. Auditoria específica do Private Evals

O bounded context contém **56 arquivos Python** e Slices 1–15 reportados como aprovados. Todo o diretório permanece protegido e untracked. Os arquivos estão organizados por responsabilidades:

| File/group | Current responsibility | Referenced by | Redundant? | Safe action |
|---|---|---|---:|---|
| `__init__.py`, `contracts.py`, `errors.py`, `values.py`, `canonical.py`, `states.py` | superfície e valores de domínio | módulos internos/testes | não provado | KEEP |
| `analysis.py`, `evaluation.py`, `case_evaluation*.py`, `evaluation_records.py` | avaliação/casos/records | serviços, exports e testes | não provado | KEEP |
| `catalog*.py` | catálogo e falhas | runtime/commands/tests | não | KEEP |
| `command_*.py`, `command_contracts.py`, `command_error_mapping.py`, `command_errors.py` | command surface, handlers e mapping | testes/CLI surface | não | KEEP |
| `query_handler.py`, `query_models.py` | queries/read models | commands/tests | não | KEEP |
| `evidence*.py` | projeção/submissão de evidência | evaluation/commands/tests | não | KEEP |
| `execution*.py` | contratos, policy e records de execução | runtime/services/tests | não | KEEP |
| `runs.py`, `run_*.py` | lifecycle/finalização de runs | runtime/commands/tests | não | KEEP |
| `results.py`, `result_*.py` | materialização/modelos/erros de resultado | services/tests | não | KEEP |
| `scoring*.py` | score service/errors | evaluation/runtime/tests | não | KEEP |
| `security*.py` | contracts/service/errors de segurança | command/runtime/tests | não | KEEP |
| `store*.py` | persistência/models/errors | services/runtime/tests | não | KEEP |
| `runtime.py` | composição do bounded context | bootstrap/commands/tests | não | KEEP |

Todos os módulos, exceto o agregador `__init__.py`, tiveram ao menos uma referência estática; `evaluation.py` é reexportado e pertence a slices anteriores. Não houve unused import no Ruff, nem referência quebrada encontrada. O grafo oficial mostra Private Evals dependendo apenas de `intelligence_boundary` e `project_governance`, fora do SCC não trivial. Drift: `docs/architecture/private-evals-runtime.md` ainda afirma “domain NOT IMPLEMENTED” apesar do avanço dos Slices; `KEEP BUT DOCUMENT` e corrigir somente em lote documental aprovado. Resultado: **nenhuma remoção segura nesta fase**.

## 21. Documentação superseded

| Document | Classification | Superseded by | Historical value | Proposed action |
|---|---|---|---:|---|
| `docs/audits/project-state-for-new-chat.md` | SUPERSEDED/V2 | auditorias V3 | alta | MARK SUPERSEDED/ARCHIVE |
| `docs/audits/synapse-v3-current-state-audit.md` | HISTORICAL | este relatório + grafo corrente | alta | KEEP, marcar data |
| `docs/audit/current-dependency-graph.json` e SCCs | GENERATED/HISTORICAL | execução corrente | média/alta | ARCHIVE; regenerar controladamente |
| `docs/validation/backend-freeze-audit.md` | HISTORICAL | baseline cumulativo | alta | KEEP/ARCHIVE |
| `docs/validation/backend-freeze-baseline.md` | CURRENT SUPPORTING, porém stale | gates atuais | alta | KEEP BUT DOCUMENT |
| OpenAPI before/after | GENERATED/HISTORICAL | API corrente | média | CONSOLIDATE índice/ARCHIVE |
| `README.md` | CURRENT SUPPORTING com métricas stale | testes/grafos correntes | alta | KEEP BUT DOCUMENT |
| `docs/architecture.md` | AUTHORITATIVE com contagem stale | metodologia/grafo corrente | alta | KEEP; corrigir em lote futuro |
| `docs/architecture/private-evals-runtime.md` | AUTHORITATIVE/SUPPORTING com drift | implementação atual | alta | KEEP; atualizar depois do freeze |

## 22. Testes e fixtures suspeitos

| Test/fixture | Rule protected | Duplicate coverage? | Still valid? | Proposed action |
|---|---|---:|---:|---|
| `tests/architecture/**` | boundaries, grafos, SCC, frozen contracts | não provado | sim | KEEP |
| `tests/factories/agents.py` | fixtures de agentes | não; muitos consumidores | sim | KEEP |
| `tests/factories/audio.py` | fixtures de áudio | não; muitos consumidores | sim | KEEP |
| deleted `tests/test_communication_runtime.py` | runtime antigo | provável migração para agents | requer revisão | validar junto da remoção do domínio |
| testes Private Evals | slices 1–15 | não provado | sim | KEEP integralmente |
| `tests/__pycache__` | nenhum | n/a | não é fonte | SAFE TO REMOVE como cache |

Há 205 arquivos `.py` de teste (1,53 MB); o tamanho físico de `tests/` é inflado por 306 `.pyc` (~5,88 MB). Não foram encontrados snapshots/goldens órfãos. Nenhum teste fonte adicional é recomendado para remoção.

## 23. Dependências duplicadas

| File/environment | Purpose | Current authority? | Duplicate? | Action |
|---|---|---:|---:|---|
| `pyproject.toml` | declaração de dependências/tooling | sim | não | KEEP |
| `uv.lock` | resolução determinística | provável; untracked | não | KEEP; regularizar no Git após revisão |
| `.venv` | desenvolvimento | não | conteúdo derivado | recriar/limpar em lote B |
| `.venv-release` | packaging | não | parcialmente com `.venv` | manter só se receita exigir; validar |
| `backend/dist` | distribuição standalone | não | duplica DLLs por design | regenerar em lote |
| `backend/build` | intermediários PyInstaller | não | sim, temporário | regenerar em lote |
| `synapse_v2.egg-info` | metadata gerada | não | derivada | SAFE TO REMOVE após teste |
| `Dockerfile`, `docker-compose.yml` | container/deploy | tooling corrente | não provado | KEEP/MANUAL REVIEW |

## 24. Security findings

Não foi impresso nenhum segredo. Os achados são de **risco de conteúdo**, não confirmação de vazamento: logs de evento, conversations/agent state, respostas multimodais/perception e áudio WAV. Devem permanecer fora de commits não revisados, ter retenção explícita e, quando necessário, armazenamento secreto/criptografado. A árvore Git/histórico não foi reescrita. O fato de um path estar ignorado não substitui controles de acesso e retenção.

## 25. KEEP

Todo `backend/synapse/private_evals`, testes/docs associados; fonte ativa; architecture tests; contratos; manifests; migrations; bootstrap; `pyproject.toml`; `uv.lock`; factories ativas; ADRs e histórico útil; modelos de voz enquanto o cache/ownership não for decidido.

## 26. KEEP BUT DOCUMENT

Shims ativos de `api`, `chat` e `core`; README/baselines com métricas stale; grafo/SCC gerados com data explícita; `speech_adapters/interfaces.py`; runtime/private data com ownership e retenção; `.venv-release` enquanto a receita de release depender dele.

## 27. ADD TO GITIGNORE

**Nenhuma alteração recomendada para execução nesta auditoria.** Candidatos para discussão futura: logs pytest de raiz, `tmp_voice_backend_test.wav` e outputs temporários equivalentes. `uv.lock` **não** deve ser ignorado por padrão. Modelos/dados devem usar regra específica somente após definir ownership; a regra atual já cobre ambientes, caches e builds principais.

## 28. ARCHIVE

Relatórios de auditoria antigos, evidências OpenAPI before/after e baselines de grafo datados podem ir para arquivo documental com índice e checksums. Arquivar não significa apagar; preservar decisões e capacidade de auditoria.

## 29. MARK SUPERSEDED

`docs/audits/project-state-for-new-chat.md` e relatórios que apresentem métricas antigas como atuais. Marcar, não reescrever o conteúdo histórico.

## 30. CONSOLIDATE

Criar futuramente um índice de evidências em `docs/validation`/`docs/audit`, com autoridade, data, gerador e status. Consolidar referências, não misturar ou apagar provas antes de checksum/archive.

## 31. MIGRATE THEN REMOVE

`speech_adapters/interfaces.py` somente após migração comprovada para `audio.contracts`; modelos de voz apenas após cache externo/redownload verificado; logs/dados somente após retenção/export seguro; antigo `synapse.communication` somente como migração atômica para `agents.communication`.

## 32. SAFE TO REMOVE

Em lote futuro e após restore point: `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `__pycache__` e metadata `egg-info`. Builds e ambientes são recriáveis **condicionalmente** e por isso ficam nos lotes próprios, não recebem autorização imediata deste relatório.

## 33. REMOVE ONLY AFTER TESTS

`notifications/console_provider.py`; `backend/build`, `backend/dist`; `.venv`, `.venv-release`; logs de teste; `tmp_voice_backend_test.wav` após security review. “After tests” inclui recriação e validações da seção 39.

## 34. MANUAL REVIEW REQUIRED

Todos os 1.014 untracked antes de qualquer limpeza ampla; 85 tracked modifications; oito tracked deletions; `data/**`; RFCs/Plans/drafts; Docker/tooling; documentação histórica; nomes com `legacy/deprecated/archive`; modelo de distribuição; autoridade do lockfile; toda possível API pública sem consumidor interno.

## 35. Lotes propostos

| Batch | Paths/groups | Estimated files | Estimated size | Risk | Required validation |
|---|---|---:|---:|---|---|
| A — caches/temporários | mypy/pytest/ruff caches, source/test pycache; logs e WAV só após revisão | ~350–750 fora de env/build | ~42–50 MB | baixo a médio | restore, Ruff, testes, privacidade |
| B — ambientes locais | `.venv`, `.venv-release` | 10.126 | 402,8 MB | médio | `uv sync`, tools e suíte |
| C — grandes/runtime/build | `backend/build`, `backend/dist`, egg-info; modelos em sublote separado | ~894 build; 13 models | 314,7 MB + 226,1 MB condicional | médio/alto | rebuild/smoke; download/hash dos modelos |
| D — docs superseded | audits, graphs, OpenAPI evidence | ~15–30 | ~4–5 MB | médio | índice, links, checksums, docs review |
| E — código morto | console provider; communication somente como migração | 1 + lote dirty existente | <0,1 MB | alto | imports, context/global tests, graph/SCC |
| F — testes/fixtures | nenhum candidato imediato; test communication acompanha E | 0–1 | trivial | alto | provar cobertura preservada |
| G — duplicações | speech contract/interface e authorities documentais | 1 + docs | trivial | alto | authority decision + migration |
| H — segurança | logs, WAV, conversations, agents, provider data | indeterminado | ≥4,6 MB | crítico | retenção, archive seguro, history review |

## 36. Estimativa de arquivos removíveis

Alta confiança após restauração/recriação: **aprox. 11,1 mil–11,4 mil arquivos**, dominados pelos 10.126 arquivos de ambientes, 889 de build e caches. O intervalo evita dupla contagem de `.pyc` já contidos em ambientes/builds. Não inclui fonte, Private Evals, documentos históricos, modelos ou private data.

## 37. Estimativa de espaço recuperável

Alta confiança condicional a testes: **~752 MB** (ambientes + build + caches não sobrepostos), cerca de **74%** do workspace. Com logs/pycache adicionais validados: **~760–770 MB**. Modelos de voz acrescentariam 226,1 MB somente após migração, levando o teto teórico a **~986–996 MB**; esse teto não é meta nem autorização.

## 38. Restore-point procedure

Antes de qualquer remoção futura:

1. registrar branch e SHA do HEAD;
2. salvar `git status --short --branch`, incluindo staged, deleted e renames;
3. salvar listas completas tracked, untracked e ignored;
4. gerar manifest de paths, tamanhos, mtimes e SHA-256 fora do workspace;
5. criar archive externo do workspace necessário, sem `.git` ser manipulado;
6. separar private data/secrets em storage de acesso controlado;
7. registrar baseline de Ruff, Mypy, testes e falhas conhecidas;
8. registrar grafo de contexts, SCC oficial e SCC exato;
9. escrever instruções de restauração por lote e por classe de dados;
10. verificar hashes, listagem e extração amostral/isolada do archive antes da limpeza.

Este restore point **não foi criado** durante a auditoria.

## 39. Validation procedure

Cada lote futuro exige, na ordem apropriada:

1. `git diff --check`;
2. Ruff;
3. Mypy relevante;
4. testes do bounded context afetado;
5. architecture tests;
6. suíte global se produção for removida;
7. `_runtime_context_graph()`;
8. SCC oficial;
9. exact-module SCC;
10. busca por imports quebrados;
11. busca por referências órfãs, incluindo registries/bootstrap/reflection;
12. comparação de contagem e tamanho antes/depois;
13. teste de restauração do lote;
14. nenhum commit até aprovação explícita.

Gates desta auditoria: Ruff **PASS**; Mypy Private Evals **PASS (56 files)**; Mypy global **FAIL (215 erros/58 files)**; architecture tests **130 passed em 29,80 s**. Grafo oficial: **70 contexts / 263 edges**, um SCC não trivial de **13 contexts / 35 edges internos** (`agents`, `approvals`, `avatar`, `context`, `conversations`, `decisions`, `delegation`, `embodiment`, `missions`, `models`, `policies`, `tools`, `voice`). Grafo exato: **510 módulos / 1.913 edges / zero SCC não trivial**. Nenhum baseline foi alterado.

## 40. Protected paths

- `backend/synapse/private_evals/**`, documentação e todos os testes Private Evals;
- `backend/synapse/bootstrap/**` e configuração atual;
- arquitetura oficial, contracts congelados e `tests/architecture/**`;
- manifests, migrations e estados de migration;
- RFCs, Plans e templates vigentes ou ainda não classificados;
- todos os untracked não classificados;
- `data/**` até classificação de privacy/retention/ownership;
- secrets, private data, agent memory, conversations, logs e mídia;
- `.git/**` e todo histórico Git;
- `pyproject.toml`, `uv.lock`, Docker/tooling até confirmação de autoridade;
- ADRs e documentação histórica antes de archive verificado;
- shims ativos e APIs públicas sem prova de migração.

## 41. Riscos

O maior risco é confundir um workspace majoritariamente untracked/ignored com material descartável. Outros riscos: perder Private Evals; apagar private/runtime state; quebrar imports externos/dinâmicos; invalidar scanners de arquitetura; remover shims ainda usados; eliminar evidência histórica; tornar builds irreproduzíveis; considerar o Mypy global verde quando ele está vermelho; e somar diretórios aninhados, superestimando recuperação.

## 42. Itens não verificáveis

Não foi possível provar consumidores externos ao repositório, necessidade operacional dos modelos/logs, estratégia organizacional de retenção, autoridade final dos drafts/RFCs, reprodutibilidade completa dos dois ambientes, uso real do pacote PyInstaller, ou integridade de um restore archive que não foi autorizado a criar. Também não se executou a suíte global completa nesta coleta; a contagem de 1.626 testes vem de execução anterior do mesmo workspace, enquanto esta auditoria executou somente a suíte arquitetural. Esses limites impedem classificações agressivas.

## 43. Confirmação: nada foi deletado

Confirmado. A auditoria não deletou arquivos. As oito deleções tracked já existiam no working tree e não foram alteradas.

## 44. Confirmação: nenhum arquivo foi movido

Confirmado. Nenhum arquivo ou diretório foi movido ou renomeado.

## 45. Confirmação: produção não foi alterada

Confirmado. Nenhum código de produção foi modificado.

## 46. Confirmação: `.gitignore` não foi alterado

Confirmado. `.gitignore` foi somente inspecionado.

## 47. Confirmação: sem stage, commit ou push

Confirmado. Não houve stage, commit, push, PR, stash, reset, checkout, restore ou clean.

## 48. Confirmação: próximo slice/módulo não iniciado

Confirmado. Nenhum novo slice, adapter, Composition Root ou módulo funcional foi iniciado.

## 49. Estado final do backend

**O backend permanece NOT READY.** O Private Evals Runtime permanece em fechamento, amplamente untracked e **não congelado**. O próximo passo permitido é revisar/aprovar este relatório e escolher um lote independente; nenhuma limpeza deve começar sem restore point verificado.
