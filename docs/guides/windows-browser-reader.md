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
login, ações de missão e quarentena de downloads pertencem aos critérios
restantes da [etapa 14](../specs/2026-11-13-browser-threat-model.md).

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

## Login experimental na Wikipedia de testes

Abra `https://auth.wikimedia.org/testwiki/wiki/Special:UserLogin` e confirme
esse mesmo endereço como destino do formulário, com os campos `wpName` e
`wpPassword`. A exceção de retorno se aplica a esse fluxo de login e permite
seguir para `test.wikipedia.org` depois do envio. Redirecionamentos que
repetiriam o POST são recusados. O Synapse só indica sessão confirmada se a
API da wiki devolver a identidade da conta esperada. Se a conta for confirmada, os cookies ficam cifrados com DPAPI no Windows.
Use **Verificar sessão da Wikipedia** após reabrir o aplicativo para consultar
a sessão armazenada. A senha não é armazenada.
