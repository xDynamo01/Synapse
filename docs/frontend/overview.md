# Synapse Frontend

Status: **NOT IMPLEMENTED**.

Este documento resume o estado atual após a remoção autorizada do Electron ADE.
[ADR 0119](../adr/0119-retire-electron-ade.md) é a decisão vigente para a retirada.

## Removed Electron ADE baseline

O baseline Electron ADE anterior foi **REMOVED / RETIRED**. A estrutura abaixo é
histórica e não representa uma implementação ativa:

- Activity Bar;
- Sidebar contextual;
- workspace Dockview;
- Bottom Panel;
- Status Bar;
- renderer em TypeScript/HTML/CSS;
- context isolation ativado e Node integration desativado;
- backend acessado por módulos de API tipados, sem `fetch` direto em componentes.

A Sidebar contextual faz parte da decisão vigente. A proposta anterior de remover
toda sidebar esquerda não é o baseline aceito.

## Historical product and UX direction

Sem substituir a decisão vigente, estes itens ficam preservados apenas como histórico
de produto da implementação removida:

- chat como pane central importante, sem transformar toda a aplicação em uma
  landing page de chatbot;
- Swarm visível sob demanda em pane ou painel colapsável;
- comandos `/` apresentados contextualmente;
- identificação clara do projeto no workspace;
- panes ou janelas de agentes abertas sob demanda;
- voice visualizer central com círculo responsivo à fala, partículas e tratamento
  etéreo, em vez de uma waveform convencional como elemento principal.

Esses itens não constituem implementação ativa nem baseline aprovado para o próximo
frontend.

## Backend boundary

Voice, Audio e Perception pertencem ao backend. O frontend apenas representa seus
estados e eventos. Visualização, animação e presença visual não justificam criar
`Avatar` ou `Embodiment` como bounded context.

Frontend permanece fora do workflow `$continue-backend`. Qualquer novo frontend ou
mudança futura de contrato compartilhado deve receber escopo e governança próprios; não
há exceção genérica para implementar compatibilidade frontend durante slices de backend.
