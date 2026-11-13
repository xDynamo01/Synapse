# Etapa 14 — Modelo de ameaças do navegador interno

Escopo Windows do Synapse 0.3, base `d61edf1`. O Core autoriza missões e grava
recibos. O desktop e a ponte falam com ele por canal nomeado local da conta
proprietária. A inferência local usa o adaptador de modelos. O navegador,
o cofre de sessões e o broker de rede descritos abaixo são componentes a
implementar. O [Documento de Decisões](2026-11-06-synapse-0.3-decision-charter.md)
fixa os requisitos SE-001 a SE-006.

## Limites de confiança

- **Core.** Resolve a aprovação vigente e limita o efeito ao contrato selado.
  Recebe identificadores opacos de sessão. O conteúdo das páginas entra como
  dado e não pode criar autorização.
- **Processo do navegador.** Renderiza conteúdo não confiável em isolamento
  do sistema operacional. Perfis têm diretórios separados e cofre protegido
  pela conta do sistema. A interface do produto permanece em Rust nativo.
- **Broker de rede.** Aplica a política antes da conexão e em cada salto de
  redirecionamento. Navegação automatizada tem origem, destino, ação e efeito
  definidos pela missão. Subrecursos, pop-ups, conexões persistentes e
  protocolos alternativos precisam passar pela mesma política.
- **Uso manual.** O usuário pode navegar e iniciar sessão no perfil protegido.
  A passagem para automação depende de autorização no Core para aquele perfil.
  Credenciais, cookies e cabeçalhos de autenticação ficam no limite do navegador.

## Ameaças e critérios de aceite

| Ameaça | Controle previsto | Evidência exigida |
| --- | --- | --- |
| Página tenta comandar o agente ou acessar arquivos, memória, clipboard ou ferramentas | Nenhuma ponte privilegiada no conteúdo renderizado. Retorno de leitura tratado como dado, sem despacho de comandos | Página de teste maliciosa não obtém acesso a recursos locais e não produz efeitos |
| Destino indireto alcança serviço local, rede privada ou metadados | Origens HTTPS normalizadas. Validar DNS e endereço conectado. Recusar endereços locais, privados e reservados e reavaliar cada redirecionamento. Exceções de teste ficam fora da configuração de produção | Testes de redirecionamento, IPv4/IPv6, DNS mutável e subrecursos com política efetiva |
| Sessão de outro perfil ou cookie em prompt, log ou memória | Perfil persistente isolado por identidade, credenciais cifradas pela plataforma e projeção de dados sem cookies ou tokens | Dois perfis com sessões diferentes, reinício, inspeção de logs e tentativa de uso cruzado |
| Clique ou envio causa efeito externo, inclusive via GET | Cada ação automatizada exige operação, destino e efeito aprovados. O broker revalida a autorização antes do envio. Registrar tentativa, resultado e incerteza com recibo durável | Ação fora do contrato falha. Revogação impede novos envios. Falha após despacho fica pendente de verificação antes de qualquer repetição |
| Download executável, arquivo disfarçado ou extração fora do destino | Quarentena separada, limites de tamanho, hash, classificação e varredura. Sem execução ou promoção automática. Exportação segue o broker de arquivos | Testes de conteúdo incompatível, tamanho, arquivo compactado e interrupção |
| Renderer comprometido ou política aplicada só ao comando inicial | Isolamento de processo e egress do sistema. Bloquear acesso direto ao canal do Core, perfis alheios e áreas privadas | Verificar a fronteira no Windows real e os fluxos indiretos antes de liberar ações autenticadas |

A autorização é concedida uma vez por missão para efeitos declarados. Uma
revogação cancela trabalhos pendentes e impede novos efeitos. Um efeito remoto
já recebido pelo servidor pode precisar de reconciliação pelo proprietário.
O sistema protege perfis de páginas, renderers e modelos não confiáveis. Um
processo com os privilégios da conta proprietária ou de administrador pertence
a outra fronteira. A avaliação acima descreve riscos e testes de aceite, sem
atribuir vulnerabilidades observadas a um navegador que ainda não foi instalado.

## Ordem de entrega

1. Escolher e validar um motor separado no Windows, com perfil descartável,
   política de rede aplicada ao processo e leitura pública de origem aprovada.
2. Ligar o broker ao contrato de missão, adicionar recibos e validar revogação
   e isolamento de navegação e downloads em ambiente de teste local.
3. Adicionar perfil autenticado persistente com cofre do sistema e ação de
   teste de efeito explícito. Validar isolamento, reinício e falhas ambíguas
   antes de marcar a etapa como concluída.

O primeiro componente de código é `backend/core/src/browser_policy.rs`. Ele
valida destinos HTTPS, redirecionamentos de mesma origem, respostas DNS e o
endereço do par. A validação é determinística e não abre conexões. O
transporte ainda precisa aplicar a política na resolução e na conexão TLS,
e provar que o motor também respeita a política em requisições indiretas.
