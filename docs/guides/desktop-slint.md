# Synapse Workspace · fundação desktop

## Modelos

A aba usa cartões compactos de provedores e uma grade de seletores MoM.
O Core atual implementa LM Studio como provedor de inferência. A lista
`model_slots` de `capabilities_list` determina a quantidade de cartões.
Os slots atuais são Conversa, Tarefas (planejamento e geração), Revisão e
Tradução. Memória herda o modelo da conversa. Conversa, Tarefas e Revisão
alteram os modelos enviados nos contratos correspondentes. Tradução fica
desativada na configuração visual até a migração desse controle ao Slint.
As atribuições de Conversa, Tarefas e Revisão, a escolha automática/manual e
as políticas de recursos são persistidas pelo Core e revalidadas contra o
catálogo ao reconectar. Uma escolha manual compatível prevalece sobre a
seleção automática.

## Conversas e tarefas

O chat usa a identidade ARTEMIS definida pelo Core. Para executar um objetivo,
escreva no campo de mensagem e abra o ícone de tarefa ao lado dele. No
Workspace, confira a pasta, clique em **Planejar tarefa**, revise a proposta,
aprove e execute. O resultado mostra os recibos de geração, verificações,
revisão e integração do Core. O fluxo atual suporta criação de artefatos em
Workspace sem Git. A pasta padrão fica em `%LOCALAPPDATA%/Synapse/workspace`.

O iniciador procura o runtime dedicado de verificações em `check-runtime`
próximo ao executável ou em `target/check-runtime`, com `runtime-manifest.json`.
`SYNAPSE_CHECK_PYTHON_EXECUTABLE` permite selecionar um pacote verificado.
[Validação e limites atuais](../evidence/backend/2026-11-21-slint-agent-integration.md).

Execute `cargo run --locked -p synapse-desktop-slint` a partir da raiz.
`-- --smoke` abre a janela e encerra o loop após uma breve espera.

O Synapse abre na Presence da ARTEMIS, com o loop da esfera de circuitos
modelada e renderizada no Blender, incorporado ao app. O ícone superior da barra lateral abre o Workspace
em tela própria, com prompt e saída monoespaçados. A Presence é desmontada
durante essa navegação. Use o ícone **Voltar à ARTEMIS** na barra superior.
Configurações fica na base da barra lateral. A mesma barra superior reúne
estado da conexão à esquerda e notificações e controles de janela à direita.
O chat inicia recolhido, com a entrada em uma cápsula centralizada. Usa bolhas em duas superfícies e alterna os ícones
de voz e envio conforme o rascunho. Configurações têm Personalização,
Modelos (Provedores, MoM e API Keys), Áudio e Biblioteca (Histórico e Projetos).
Abra `Synapse.exe` na raiz para iniciar automaticamente o Core local no
Windows. Ele procura `synapse-backend.exe` ao lado do app ou em
`target/release` e `target/debug`. O estado e o Workspace padrão ficam em
`%LOCALAPPDATA%\Synapse`. O app usa Python 3.14 para executar os workers.
Quando o LM Studio está instalado, inicia seu servidor em loopback se
necessário e pode cadastrar um modelo local compatível se o Core ainda
não tiver modelo de conversa. Prefere um modelo já residente; na ausência
dele, sugere o Qwen2.5 Coder instalado; sem esse modelo, usa o menor modelo
local disponível. A sugestão não substitui uma atribuição manual persistida. O Core carrega o
modelo sob demanda.

Passe um endpoint explícito como primeiro argumento para conectar a um
Core gerenciado separadamente. Para outro ambiente local, configure
`SYNAPSE_CORE_EXECUTABLE`, `SYNAPSE_PYTHON_EXECUTABLE`,
`SYNAPSE_STATE_DIR` ou `SYNAPSE_WORKSPACE_DIR`.

## Etapas integradas

1. **Conexão e observabilidade.** `health` confirma o estado do Core.
   O console aceita `status` e `eventos`. `events_read` carrega páginas e
   mantém as últimas 18 linhas na tela.
2. **Modelos e Biblioteca.** `models_list` carrega o inventário registrado.
   O Core verifica o modelo quando a conversa é enviada. Eventos identificam
   projetos e conversas. `project_get` e `chat_get` consultam os detalhes.
3. **Conversa e entrada única.** `chat_create` cria uma conversa em
   `project:desktop` quando não há seleção. `input_submit` encaminha texto
   para conversa, especialização ou proposta de missão; voz comum usa a
   mesma decisão no Core. `job_get` acompanha o resultado e `chat_get`
   recupera o histórico. Uma saudação não aciona planejamento.
4. **Missões com dependências.** O Planner pode propor um grafo com tarefas,
   entregas e verificações. A aprovação sela a revisão completa. Só tarefas
   cujas dependências tenham resultados verificados podem executar. O
   Workspace acompanha pausa, retomada, cancelamento e revisão do plano.
   Uma nova tentativa conserva a autorização e o contexto originais e
   exige aprovação da nova revisão.
5. **MoM e Swarm.** NORMAL/SWARM e RESPONSIVE/ECONOMICAL são estados distintos.
   O pedido de Swarm tem confirmação vinculada à missão. A interface mostra
   sua ativação depois do início real e o encerramento após publicação,
   cancelamento ou falha. Os papéis temporários reutilizam os contratos,
   reservas e verificações do Core.

A Biblioteca mostra identificadores publicados pelos eventos. O título salvo
aparece no detalhe e o Core v1 consultado não fornece a data da conversa.
Perfil, credenciais, anexos, notificações e sessões livres de terminal
continuam fora desta integração. Contexto e Skill são referências explícitas;
uma menção em conteúdo recuperado não concede acesso a outro projeto.

Valide o fluxo com um Core isolado no Windows usando
`pwsh -File tools/verify-desktop-slint.ps1` e Python 3.14.

## Migração e contratos

| Origem e fluxo | Destino e contrato |
| --- | --- |
| Electron/React no histórico Git anterior a `46177e3` | Referência visual e de fluxo. Shell, renderização web e preload foram sucedidos pela direção Rust nativa. |
| Electron `src/main/main.ts` e `src/preload/preload.ts` | Preservar ciclo de janela e seleção nativa de anexos por ações nomeadas no host Rust. Descoberta da URL HTTP e relato de bootstrap do renderer cedem lugar ao contrato local v1 e a um estado de conexão confirmado. |
| React `Presence.tsx`, `ActivityConstellation.tsx` e `MoMSettings.tsx` | Preservar sinal de atividade e configuração especializada. Substituir efeitos em canvas pela Presence Slint e extrair os dados de modelo do catálogo autorizado do Core. |
| eframe Presence, conversa e bridge | Preservar abertura, criação, envio e restauração pelo Core v1. Separar identidade da ARTEMIS do modelo selecionado. |
| eframe Workspace, missões, recuperação, Git e Skills | Preservar autorizações, digests e evidências do Core. O terminal precisa de sessões limitadas e saída paginada ou em lotes. |
| eframe áudio, tray e voz | Reusar integração Rust de dispositivos e ciclo de vida. Dictation, voz e preview exigem capabilities confirmadas. |
| Catálogo e configuração de modelos | Ler inventário real e persistir as quatro atribuições MoM através do owner. Credenciais passam pelo serviço seguro e retornam apenas estado. |
| Perfil, histórico, projetos e anexos | Conectar ao owner de cada operação. Ler histórico e projeto sem recuperação semântica automática. Títulos exigem metadados confiáveis. Associação não autoriza retrieval. |
| Temas de tela inteira e chat como tela principal | A interface usa base neutra, cor semântica e navegação centrada no Workspace. |

Presence recebe estados idle, listening, processing, speaking e error
do host. A animação leve só roda com Presence montada no Workspace.
O modelo de mensagens admite alimentação pelo host, com scroll sem barra.
A luz vermelha sinaliza conexão indisponível e a verde confirma a resposta
de saúde do Core. O shell não inicia workers nem abre armazenamento.

A marca e os ícones de interface ficam em `backend/desktop-slint/ui/assets`.
O build do Windows gera o ícone do Explorer em vários tamanhos a partir
do mesmo SVG usado na janela.


## Contexto entre etapas

O Core sela uma projeção com objetivo, histórico recente, referências canônicas
selecionadas, revisões, digests e resultados anteriores. Planejador, geração
e revisão recebem a mesma projeção como dados sem autoridade de execução.
Histórico abreviado contém marcadores explícitos de truncamento. A memória
não é carregada integralmente por associação ao chat ou à pasta.

Arquivos de tarefas predecessoras entram nos testes como dados somente para
leitura. Seus digests são vinculados aos recibos de pré e pós-validação.
Alterações posteriores nos bytes ou na identidade do arquivo invalidam a
aceitação da dependência.

As quatro pastas de Rust/VC/SDK validadas podem ser persistidas em `%LOCALAPPDATA%/Synapse/native-toolchain.json`, usando os mesmos nomes `SYNAPSE_RUNNER_*` aceitos pelo Core. Valores explícitos no ambiente prevalecem. O arquivo só aceita pastas absolutas existentes; pins e contenção continuam sendo verificados pelo runner.

[Aceite das oito prioridades e identificação do executável](../evidence/backend/2026-11-22-integracao-oito-prioridades.md).
