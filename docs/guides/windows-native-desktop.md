# Cliente nativo e ponte local do Synapse no Windows

A [fundação Rust + Slint](desktop-slint.md) está disponível em paralelo.
Este guia descreve o cliente eframe e a ponte nativa já integrados ao Core.

Compile `cargo build --locked -p synapse-core -p synapse-desktop`. Prepare o
[Python e os runtimes de testes](windows-mission-recovery.md) para os fluxos que
precisam deles. Registre o modelo local no Core pelo protocolo v1.

Inicie o Core em um terminal com um diretório de estado privado e um Workspace
existente. Para publicação automática nesta etapa, use um Workspace fora de
qualquer repositório Git. O Core permanece ativo enquanto o cliente está fechado.

```powershell
.\target\debug\synapse-backend.exe --state-dir $state --workspace $workspace --local-endpoint desktop
```

Em outro terminal, abra a interface ou a ponte. Ambos usam o mesmo controlador
Rust e a mesma conexão v1. O canal do Windows aceita apenas conexões locais da
conta proprietária. Cada solicitação libera o canal ao terminar, permitindo que
mais de um cliente consulte o mesmo Core sem abrir outro armazenamento.

```powershell
.\target\debug\synapse-desktop.exe desktop
.\target\debug\synapse-desktop.exe --bridge desktop
```

A ponte recebe um objeto JSON por linha em `stdin` e devolve um resultado por
linha em `stdout`. Nenhuma janela é aberta pela ponte. `state` consulta a seleção
do cliente e atualiza trabalhos ativos. `open_chat` e `open_mission` restauram
registros do Core em um novo processo cliente.

```jsonl
{"action":"state"}
{"action":"open_chat","chat_id":"presence-e2e"}
{"action":"send_message","model":"modelo-local","text":"Qual a decisão do projeto Atlas?"}
{"action":"open_mission","mission_id":"minha-missao"}
```

Use `create_chat` com `chat_id`, `title` e `scope` para abrir uma conversa nova.
`send_message` aceita `context` com `scope` e `key` para selecionar uma memória
específica. No Presence, o seletor **Sem Skill** lista versões
registradas para o escopo da conversa. Na ponte, `send_message` aceita
opcionalmente `skill` com `scope`, `id`, `version` e `digest`.

A ponte também aceita `plan` com `mission_id`, `scope`, `model` e `objective`,
`approve` com o `contract_digest` da proposta, e `execute` após a aprovação.
Uma missão em `recovery_required` oferece `inspect_recovery` e
`resolve_recovery` com `mode` igual a `finalize` ou `rollback`. O Core aplica
as mesmas verificações de autorização e evidência do
[protocolo v1](../../backend/contracts/v1/README.md).

Uma referência natural usa um nome conhecido após “projeto” ou “project”. O
cliente usa metadados de eventos para descobrir chaves ativas e o Core carrega
somente as referências exatas da mensagem. Na interface, os campos de projeto e
chave permitem selecionar uma memória específica em caso de ambiguidade.

Para cadastrar projetos, editar arquivos Git e escolher receitas por domínio,
consulte o [guia de Workspaces](windows-project-workspaces.md).


No Workspace, abra **Importar Skill**. Cole um pacote JSON com `manifest` e
`license` ou informe sua URL HTTPS pública e selecione **Buscar pacote**.
A busca mostra a origem final e preenche o editor. Inspecione o pacote,
revise sua procedência e instruções e confirme
a instalação da versão apresentada. Clique em **Usar no próximo planejamento**
para fixar essa versão no próximo plano do projeto. A ponte oferece `skill_inspect` e
`skill_install`. Envie o mesmo pacote e o `inspected_digest` retornado pela
inspeção ao instalar.


Use **Buscar catálogo** para um índice JSON público com até 50 itens. Cada
item contém `name` e `url`. URLs relativas são resolvidas a partir do índice,
e os pacotes ficam na mesma origem HTTPS. Selecione um item para carregar
o pacote e seguir com a inspeção.

A ponte também permite propor uma versão com `skill_revise`, registrar um
parecer com `skill_review`, consultar a versão ativa com `skill_active` e
restaurar a anterior com `skill_rollback`. Os resultados aparecem em
`state.skill_package`. Para avaliar com o modelo local, envie
`skill_benchmark_case` para cada versão com o mesmo enunciado e a mesma
resposta esperada. Consulte os resultados com `skill_benchmark_get` e
envie os pares concluídos a `skill_benchmark_review`. O Core calcula a
pontuação e promove a candidata se houver melhora sem regressão.

A ação `skill_benchmark_run` executa a comparação e solicita a decisão
do Core em uma chamada. Informe `proposal_cursor`, `model_id` e
`scenarios`, cada um com `prompt` e `expected`. A ponte devolve o
recibo após os trabalhos terminarem. Um parecer manual fica registrado
como evidência do operador.

Use `skill_evolve` para pedir que o modelo proponha a revisão de uma
Skill de projeto e execute a avaliação. Informe o pin `parent`, a
`version` candidata, `model_id`, `evidence` de uso e `scenarios`.
A proposta recebe a orientação original e a evidência. As respostas
esperadas entram na avaliação depois que o Core registra a proposta.

Use `skill_evolve_mission` com `mission_id`, `version`, `model_id` e
`scenarios` para tomar como evidência a execução real de uma missão com
Skill de projeto fixada. A ponte aguarda o resultado, consulta o estado e
os resultados de QA no Core e executa proposta e avaliação em sequência.
Para iniciar uma missão aprovada nessa mesma chamada, envie `execute: true`.

Para avaliar a generalização, informe `evaluation_scope` nos cenários
de projetos registrados. A ação `skill_global_promote` recebe o cursor
da proposta e o digest das instruções revisadas pelo operador. O Core
exige resultados sem regressão e aprovação de todos os casos em pelo
menos dois projetos externos. A Skill global aparece entre as sugestões
do Planner enquanto a revisão de origem estiver ativa.

Para o Core carregar e liberar modelos durante a inferência, inicie-o com
`SYNAPSE_MANAGE_LOCAL_MODELS=1` e registre a chave do modelo instalado no
LM Studio. O worker usa a API local de modelos, solicita até 32.768 tokens de
contexto e mantém modelos carregados pelo operador. Se outra instância já
ocupa o servidor, a solicitação devolve `model_capacity_busy`. A configuração
é opcional para instalações que gerenciam a residência no próprio LM Studio.

No endpoint padrão `http://127.0.0.1:1234/v1`, configure também
`SYNAPSE_LMS_EXECUTABLE` com o caminho absoluto para `lms.exe` para
carregar as instâncias do Core com identificadores exclusivos. O Core
solicita a liberação ao fim do trabalho. O LM Studio aplica um limite
de 180 segundos de inatividade às instâncias criadas por esse caminho.

Use `skill_benchmark_receipt` com o cursor da proposta para consultar a
última decisão registrada e as evidências que a sustentam após reiniciar.
