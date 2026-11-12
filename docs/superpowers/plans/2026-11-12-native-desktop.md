# Etapa 11 — Cliente nativo do Synapse

1. Criar o cliente Rust em `backend/desktop`, com interface egui nativa e um
   canal em segundo plano para o protocolo v1. Separar a interface do
   transporte e manter armazenamento, autoridade e execução no Core.
2. Ligar Presence a chats, histórico paginado, seleção de modelo e referências
   explícitas. Resolver referências naturais somente entre contextos que o
   usuário seleciona ou menciona, com confirmação de ambiguidades.
3. Ligar o terminal do Workspace à proposta selada, aprovação, execução,
   progresso, QA e recuperação. O Context Rail recolhível devolve a largura
   ao terminal. A interface pede confirmação da operação de recuperação.
4. Desacoplar o ciclo de vida do host da janela, mantendo acesso local pelo
   proprietário. Na reconexão, reler os registros e percorrer eventos com
   cursor. Testar fechamento e reabertura durante uma missão e conferir os
   artefatos e recibos reais antes de marcar a etapa.

O [Documento de Decisões](../../specs/2026-11-06-synapse-0.3-decision-charter.md)
rege o desenho. PX-002 a PX-004 cobrem Presence e Workspace. ME-002 e ME-003
regem histórico e contexto canônico. PL-001, PL-004 e PL-006 regem o Core
único, validação por plataforma e a interface Rust. MI-002, MI-003 e MI-006
regem a autoridade de missão, a aprovação e a recuperação.
