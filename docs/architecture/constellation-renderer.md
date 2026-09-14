# Constelação por atividade — 2026-09-05

## Escopo e fonte da verdade

Perfil `bounded-context-change`: Activity/Constellation. Presence, Settings, voz,
Conversation Log, composer e shell permanecem fora deste slice. Sem mudança de
versão, stage, commit ou push.

As referências fornecidas orientam apenas a estética. A cena de produção não
importa fixtures, não cria ferramentas fictícias e não declara Swarm em execução
com base no número de pontos decorativos.

Dois participantes são fixos quando configurados: primary agent e modelo
selecionado. Agentes adicionais, workers, ferramentas e fontes de contexto/memória
aparecem durante uso factual (estado ativo ou relação ativa). Ao saírem da cena,
seus recursos gráficos e conexões desaparecem em até 3,5 segundos. Tarefas e eventos
de comunicação não são transformados em agentes visuais.

## Projeção mínima de direção

O contrato operacional já tem relações com origem e destino, mas o adaptador de
eventos de chat emitia apenas atualizações de entidades. O adaptador agora projeta
nos metadados seguros, sem expor prompts:

| Evento existente | Origem | Destino |
| --- | --- | --- |
| `local_chat.thinking` | agente identificado | runtime/modelo identificado |
| `local_chat.completed` | runtime/modelo identificado | agente identificado |

Os campos são `transfer_source`, `transfer_target` e `transfer_kind`. Sem identidade
do agente, não há direção inventada. Falha não vira retorno bem-sucedido. A projeção
não altera a execução do modelo, schema persistente ou autoridade de ferramentas.

O frontend usa esses campos para um pulso transitório. Uma associação `parent`
continua silenciosa: vínculo não prova envio de dados. Relações explícitas de outras
operações preservam os source/target originais. Eventos duplicados não repetem
pulsos, e snapshots não reproduzem tráfego histórico. Recursos cujo produtor não
fornece relações/direção não ganham trajetos fictícios.

## Renderização e ciclo de vida

- PixiJS em módulo lazy, com suporte CSP sem habilitar `unsafe-eval` na política.
- Geometria por identidade: 220 partículas em agentes, 125 em modelos/workers e
  46 em recursos menores. Partículas são decoração interna, não entidades.
- Cores determinísticas por identidade, com variação por tema; Neutral desatura.
- Layout incremental: participantes existentes permanecem ancorados; novos
  participantes se acomodam próximos de relações reais, com repulsão local.
- Curvas quadráticas; até três pontos viajantes por conexão/evento, com expiração.
- Posição da câmera manual não é sobrescrita por novos dados; Enquadrar restaura
  ajuste automático. Arrastar, roda do mouse, +/−, F e Escape são suportados.
- Seleção pelo canvas e lista de participantes acessível por teclado. Registro
  continua sob demanda, com altura limitada e scroll.
- Renderização limitada a 36 FPS em foco, 10 em segundo plano; reduced motion
  elimina pulsos e micro movimento. Documento oculto interrompe o ticker.
- Limites existentes de nós/arestas/fluxos continuam valendo. Overflow informa
  a quantidade agregada sem se apresentar como um agente adicional.
- GPU, labels, handlers e observadores são liberados ao desmontar. Rastros e
  deduplicação são limitados em memória; não há novo arquivo de log permanente.

## Verificação

`npm test`: 109 testes passaram. `npm run build`: passou, incluindo higiene do
entrypoint atual (zero artefatos antigos encontrados para remover).
Testes de projeção operacional: 21 passaram; boundaries desse contexto: 3 passaram.
Ruff e Mypy locais do adaptador: passaram.

Harness Electron separado em `tests/constellation` (nunca importado pela aplicação):
2, 20 e 54 participantes sintéticos, aproximadamente 35 FPS no ambiente local,
com teto configurado de 36. Verifica expiração dos pulsos, deduplicação, preservação
da câmera e liberação dos nódulos temporários. Capturas ficam em `.cache/synapse/constellation-qa`.
Isso valida o renderer, não prova execução de Swarm real nem disponibilidade de
todas as ferramentas.

Gate global de tipos continua falhando no erro preexistente
`ConversationRecord.updated_at` em `main.tsx`. Lint tem o aviso preexistente da
dependência do callback de idioma de voz; nenhum novo erro de lint neste slice.

Na janela real, foram observados apenas Artemis e o DeepSeek selecionado. O aviso
preexistente `OPERATIONAL-EVENT-LOG-CORRUPT` permanece explícito. A incompletude do
histórico não reduz mais o brilho dos participantes nem impede a representação
de novos fatos válidos; resync/desconexão continuam suspendendo pulsos. A pedido
do usuário após inspeção visual, partículas, filamentos e rótulos receberam maior
contraste, preservando dimensões e fundo preto. O log continua montado pelo mesmo
bloco de detalhe, mas a abertura por clique na janela real não foi concluída nesta
verificação (a janela foi fechada durante o teste).

## Iluminação transferida do Presence

O renderer usa agora a mesma queda radial do Presence (centro luminoso, 38% da
intensidade a 42% do raio e zero nas bordas), numa textura branca compartilhada e
tingida por identidade. Sprites aditivos iluminam núcleo e partículas; a luz é
local ao nódulo, sem clareamento global, blur retangular ou mudança de dimensões.
Conexões recebem um traço luminoso difuso discreto. A textura é criada uma única
vez por montagem e liberada junto ao renderer. Tema, semântica, telemetria e logs
não mudaram nesta etapa.

Após nova comparação com Presence, a iluminação volumétrica local foi reforçada:
halo com queda suave e quatro lóbulos assimétricos entre as partículas, sem
alterar posições ou raios dos nódulos. O brilho mínimo do halo ocioso deixou de
ser atenuado a 55%; filamentos internos têm mais contraste. O objetivo é manter
luz perceptível no volume, e não apenas nos pontos isolados.

### Fundo alinhado a Settings

Por solicitação posterior do usuário, o fundo preto da constelação foi substituído
pelo mesmo background de Settings: gradiente dos tokens de painel e iluminação
discreta da cor primária. A regra é compartilhada, acompanha todos os temas e cobre
a área central inteira, não apenas o retângulo do canvas. Presence e iluminação
dos nódulos permanecem inalterados.

## Nebulosas — direção visual 3 (2026-09-13)

Esta revisão substitui os raios radiais por poeira distribuída em correntes e uma
textura compartilhada de gás assimétrico (`assets/media/nebula-stream.png`). A
luminância é convertida em alpha uma vez na inicialização, evitando retângulos
pretos; a textura é liberada ao desmontar. Não há textura individual por nó.
As conexões são filamentos em S; partículas em trânsito continuam dependentes
de eventos reais. Identidade, seleção, logs e participantes não foram alterados.

O repouso oscila aproximadamente ±1,4%; trabalho confirmado chega a ±9,9%, com
transição suavizada. Movimento reduzido mantém a escala em 1. Resync não autoriza
pulsação de trabalho. Atualizações recebidas durante o carregamento da textura
aguardam a inicialização completa. O par inicial primário/modelo é diagonal;
atualizações seguintes preservam posições e câmera.

Verificação focada: build e lint aprovados, 59 testes aprovados; harness Electron
com 2/20/54 nós em aproximadamente 35 FPS e sete invariantes aprovados. Evidência
visual e limites da prévia estão em `artifacts/reports/constellation-nebula/`.

### Enquadramento fixo

Por solicitação posterior, a navegação manual de câmera foi removida: sem zoom,
arraste, atalhos de câmera ou título visível. O enquadramento automático adapta-se
ao tamanho da janela e à entrada de participantes; snapshots de atividade não
deslocam a câmera. Seleção, Escape, lista acessível e registros permanecem.
