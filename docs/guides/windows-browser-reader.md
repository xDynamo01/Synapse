# Navegador interno em modo leitura

Na aba **Navegador**, informe um endereço HTTPS público e clique em **Abrir**.
O leitor usa o Python local configurado em `SYNAPSE_PYTHON_EXECUTABLE`.

Cada abertura busca o documento principal. Redirecionamentos são limitados
à mesma origem e verificados a cada salto. O leitor verifica os endereços
retornados pelo DNS e conecta diretamente a um endereço validado com TLS.
O desktop exibe texto selecionável em Rust nativo. Scripts, CSS, iframes e
outros subrecursos ficam fora do fluxo. Anexos são recusados.

## Imagens sob demanda

Use **Carregar imagem** para solicitar uma imagem listada da mesma origem.
O leitor aceita PNG e JPEG estáticos de até 2 MiB e 1024 pixels por lado.
O executável `synapse-image-decoder.exe` precisa estar ao lado do desktop
(`cargo build --locked -p synapse-core -p synapse-desktop`). O Windows executa
o decodificador em LPAC sem capacidades de rede e com limite de memória e
prazo. O Core valida dimensões e comprimento exato do RGBA antes de entregar
os pixels à interface. Imagens de outras origens ficam fora desta versão.

Na ponte, `browser_load_image` recebe `url` listada pela página aberta.
O estado retorna as dimensões depois da validação. A exibição é local.

Este fluxo é de leitura pública acionada pelo proprietário. Perfis com
login e ações de missão pertencem aos critérios restantes da [etapa 14](../specs/2026-11-13-browser-threat-model.md).

## Estrutura da página

No Windows, abra **Estrutura da página** para ver contagens de títulos,
tabelas, links, formulários e referências CSS. O `synapse-page-analyzer.exe`,
compilado junto do Core, roda em LPAC e devolve somente essas contagens.
O CSS embutido é analisado ao abrir a página. Em **Folhas CSS da página**,
use **Analisar folha CSS** para buscar uma referência da mesma origem, com
limite de 256 KiB. O resultado conta `@import` e URLs sem buscar seus destinos.
Na ponte, `browser_analyze_css` recebe a `url` listada e o estado publica o
resumo em `stylesheet`. O painel mostra uma falha se o analisador isolado
estiver indisponível.

## Leitura pública por missão

A ponte local aceita `browser_mission_read` com `mission_id` e `url` para
uma missão aprovada com a ação `browser_read`. A operação aguarda uma
decisão no Workspace quando encontra uma origem inédita. Uma origem diferente
em um redirecionamento passa pela mesma autorização antes da conexão.
O resultado contém a origem e o texto. O leitor valida DNS e TLS e
continua limitado a documentos públicos.

No Workspace, preencha projeto, identificador e objetivo e selecione
**Propor pesquisa na web**. Depois de aprovar o contrato, abra **Pesquisa na
web** e selecione **Pesquisar**. Se a URL inicial estiver vazia, o modelo
local sugere uma fonte. Pedidos de novas origens aparecem no Workspace.

A ação `browser_mission_research` recebe `mission_id`, `url` inicial opcional,
`question` e `model_id` local. Com o Chromium habilitado, o modelo pode
escolher um dos links extraídos e resumir as páginas coletadas. O cliente
recebe as URLs efetivamente consultadas em `browser_research.sources`.

### Renderização com Chromium dedicado

Use um diretório exclusivo para o Chromium do Synapse. Na raiz do
projeto, com o Python configurado, prepare o motor no PowerShell.

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $env:LOCALAPPDATA 'Synapse\browser\runtime'
& $env:SYNAPSE_PYTHON_EXECUTABLE -m pip install './backend/python[browser]'
& $env:SYNAPSE_PYTHON_EXECUTABLE -m playwright install --only-shell chromium
Get-ChildItem -LiteralPath $env:PLAYWRIGHT_BROWSERS_PATH -Recurse -Filter chrome-headless-shell.exe |
    ForEach-Object {
        icacls $_.DirectoryName /grant '*S-1-15-2-1:(OI)(CI)(RX)' '*S-1-15-2-2:(OI)(CI)(RX)'
    }
$env:SYNAPSE_BROWSER_ENGINE = 'playwright'
```

Abra o Synapse ou a ponte no mesmo terminal. As permissões concedem
leitura e execução ao AppContainer apenas nos arquivos do motor.
O Synapse confirma pelo Windows que o renderer usa AppContainer e
possui zero capacidades antes de fornecer conteúdo à página.

Na leitura de missão, o leitor HTTPS busca o documento depois da autorização
da origem. Um analisador Rust recebe o HTML bruto em um AppContainer de
privilégio reduzido, sem capacidades de rede e com limite de processo. Ele
devolve uma projeção com texto, links e campos de formulários. O Chromium
dedicado opera sobre essa projeção, com scripts de página, rede, WebSockets,
service workers e downloads desativados. Cada origem nova passa pelo Core
antes de o leitor HTTPS abrir a conexão.

Mantenha `synapse-page-analyzer.exe` junto do executável do desktop. Se o
analisador ou seu isolamento não estiverem disponíveis, a renderização
falha antes de entregar conteúdo ao Chromium.

## Sessões autenticadas

No Workspace, abra **Sites autenticados**, informe a origem HTTPS e use
**Guardar credencial local**. O cofre do Windows cifra a credencial e devolve
uma referência. Para preparar o login, informe a URL do formulário, a URL
exata de envio, a página de confirmação e um trecho que só aparece nessa
página após o login. Selecione **Propor Login**, revise o contrato e, depois
de aprová-lo, selecione **Executar Login**. O Workspace pede a autorização
da origem quando necessário.

Para reutilizar a sessão, selecione sua referência no cofre, informe a URL
a coletar e proponha **Leitura autenticada** em uma nova missão. O cofre
mantém os cookies por origem e os atualiza quando o site os renova. A ação
**Revogar sessão** remove a referência local. Se o site mantém a sessão no
servidor, o encerramento remoto depende do próprio serviço.

A credencial e os cookies ficam no processo local que envia HTTPS. O
Chromium dedicado recebe os formulários e os textos, o Core recebe
referências e recibos, e o modelo recebe apenas trechos da pesquisa pública.
A operação suporta formulários HTTPS de usuário e senha enviados diretamente
pelo site e verificados pela página indicada. Fluxos que dependem de
JavaScript, autenticação federada, CAPTCHA ou MFA precisam de suporte próprio.

## Quarentena de texto

No Windows, informe a URL pública em **Navegador** e use **Guardar endereço
como texto em quarentena**. O leitor aceita `text/plain` UTF-8 de até 256 KiB,
valida o conteúdo e grava uma cópia cifrada com DPAPI sob a pasta de dados do
Synapse. O aplicativo mostra tipo, tamanho e SHA-256. A ação é manual e a
quarentena mantém o conteúdo sem abrir o arquivo ou executar comandos.

Na ponte local, use `browser_quarantine_text` com a `url` e consulte `state`
até `browser.quarantine_loading` terminar. O recibo aparece em
`browser.quarantine_receipt`.

No Workspace, **Downloads da missão** permite propor, aprovar e guardar um
arquivo de texto pelo endereço HTTPS final. A ponte usa
`browser_mission_download` com `mission_id` e `url`. A operação exige
`browser_read`, `browser_download` e a URL exata nos recursos aprovados.
Redirecionamentos exigem um contrato com o endereço final. A resposta inclui
os metadados da quarentena e o recibo do Core.
