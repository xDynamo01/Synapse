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
