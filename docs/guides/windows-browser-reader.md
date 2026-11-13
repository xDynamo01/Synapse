# Navegador interno em modo leitura

Na aba **Navegador**, informe um endereço HTTPS público e clique em **Abrir**.
O leitor usa o Python local configurado em `SYNAPSE_PYTHON_EXECUTABLE`.

Cada abertura busca o documento principal. Redirecionamentos são limitados
à mesma origem e verificados a cada salto. O leitor verifica os endereços
retornados pelo DNS e conecta diretamente a um endereço validado com TLS.
O desktop exibe texto selecionável em Rust nativo. Scripts, imagens, CSS,
iframes e outros subrecursos ficam fora do fluxo. Anexos são recusados.

Este fluxo é de leitura pública acionada pelo proprietário. Perfis com
login, ações de missão e quarentena de downloads pertencem aos critérios
restantes da [etapa 14](../specs/2026-11-13-browser-threat-model.md).
