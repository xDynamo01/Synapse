# Artemis: acesso a ferramentas e discos

Validação local em 2026-10-29. O status global do backend continua NOT READY.

## Mudança

Agentes com papel `primary_agent` recebem as permissões das ferramentas registradas pelo mesmo `PermissionManager` usado pelos executores. Não é necessário habilitar manualmente permissões de leitura. Negativas explícitas e ferramentas proibidas continuam prevalecendo. Aprovar ou rejeitar aprovações não faz parte dessa concessão.

O catálogo enviado ao modelo inclui as ferramentas registradas, inclusive os adaptadores internos de Desktop, preservando a governança própria desses adaptadores. Descritores enviados ao modelo contêm nome, descrição e argumentos, sem o excesso de metadados internos. Turnos locais de seleção de ferramentas usam uma reserva padrão de 256 tokens; a resposta posterior tem seu próprio orçamento.

`config/filesystem_tools.yaml` aceita `all_disks: true`. Essa opção foi ativada no perfil instalado em `%APPDATA%/Synapse`. Os discos são descobertos a cada chamada: não existe uma lista fixa contendo somente um projeto. `list_disks` informa os caminhos disponíveis; `read_file`, `list_directory`, `search_files`, `write_file`, `edit_file` e `delete_file` aceitam caminhos absolutos. Acesso continua sujeito às permissões do Windows.

Criação/alteração/exclusão de arquivos e alterações de tarefas/memória geram aprovação vinculada aos argumentos. `edit_file` exige uma única ocorrência do texto antigo; `delete_file` remove somente um arquivo regular, nunca uma árvore. Links, junções, hardlinks de escrita e registros de controle do próprio Synapse não podem contornar a governança. Caminhos relativos continuam ancorados no diretório de dados.

## Evidência real

- `scripts/validate_artemis_tools.py` executa os handlers reais com uma Artemis sem permissões manuais, em perfil descartável. Aprova automaticamente somente as operações das fixtures deste teste, explicitamente autorizadas pelo usuário.
- C:, D:, E: e F:: listagem, criação, leitura, busca, edição e exclusão passaram. As pastas temporárias foram removidas depois dos testes.
- G:: listagem passou; gravação retornou `WinError 5`, acesso negado pelo Windows.
- Modelo local Qwen 2.5 0.5B: recebeu o catálogo completo, emitiu `read_file`, recebeu o resultado real e retornou `ORBITA-7291`.
- Executável recompilado: API validou todos os discos, criação, leitura, edição, exclusão e a chamada real de `read_file` pelo modelo, com aprovação antes das mutações.

| Ferramentas | Resultado |
| --- | --- |
| `list_disks`, `list_directory`, `read_file`, `search_files`, `write_file`, `edit_file`, `delete_file` | Operações reais verificadas nos discos, conforme restrição de G: acima |
| `create_task`, `update_task`, `send_agent_message` | Persistência real em perfil isolado; mensagem somente entre agentes de teste, sem destinatário externo |
| `remember`, `recall`, `memory_index`, `consolidate_memory` | Gravação e recuperação verificadas; consolidação retorna fila pendente, não promessa de persistência concluída |
| `health.summary`, `readiness.summary`, `provider.summary`, `tool.summary`, `agent.summary`, `conversation.summary`, `mission.summary` | Consultas reais retornaram dados |
| `voice.transcribe` | Recuperação de transcrição persistida verificada |
| `audio.transcribe` | STT real executado com WAV falado; reconheceu a frase inicial e a lista, com erros de transcrição no modelo tiny |
| `web_search` | Chamada chegou ao provedor, mas SearXNG estava indisponível; busca externa não passou |
| `desktop:runtime:preview`, `execute`, `cancel`, `recover` | Plano em dry-run, cancelamento e rejeição de recuperação inválida verificados; execução/recuperação também verificadas com provider de conformidade, sem operar janelas pessoais |

Não há evidência de execução visual real de Desktop nesta validação. Sucesso do transporte de uma ferramenta não implica sucesso do serviço: `web_search` retornou `provider_unavailable`, registrado como indisponível.

Relatórios: `artifacts/reports/artemis-real-tools.json`, `artemis-real-model.json`, `artemis-compiled-tools.json`, `artemis-final-focused.txt`, `artemis-architecture.txt`, `artemis-mypy.txt`, `artemis-mypy-final.txt`, `artemis-ruff.txt` e `artemis-global-tests.txt`.

## Gates executados

- Regressão global: 4.660 aprovados, cinco skips de plataforma e quatro falhas em testes que ainda esperavam mutações sem aprovação ou a antiga mensagem de caminho inválido. Essa execução começou antes dos ajustes finais; não é declarada uma execução global limpa.
- Os quatro casos foram atualizados para verificar a nova aprovação, persistência e isolamento. Nova execução dos módulos de chat, memória, acesso da Artemis e descoberta: **73 aprovados** (`artemis-final-regression.txt`).
- Arquitetura: **274 aprovados**; fronteira de ferramentas repetida após o ajuste de descoberta: **cinco aprovados**.
- NORMAL/SWARM: **19 aprovados**, sem modelos pesados.
- Ruff: aprovado. Mypy global: 835 arquivos sem erros; alterações posteriores também passaram no escopo local.
- Backend e launcher recompilados; teste no executável final confirmou os seis critérios: discos, criação, leitura, chamada real pelo modelo, edição e exclusão.
- Diff check: sem erros de whitespace; avisos de conversão LF/CRLF do worktree foram mantidos. Mudanças preexistentes de outros trabalhos foram preservadas, sem commit.

## Limites de escopo

Esta entrega conecta a Artemis às ferramentas registradas. Não transforma toda API interna em ferramenta e não altera a semântica de execução, reservas de modelos ou isolamento do Swarm. Serviços externos continuam precisando estar operacionais. O modelo continua responsável por escolher chamadas adequadas; os resultados concretos, não declarações do modelo, são a evidência de execução.
