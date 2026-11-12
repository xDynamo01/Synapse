# Cliente nativo e ponte local do Synapse no Windows

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
específica.

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
