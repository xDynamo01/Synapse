# Etapa 13 — Presence por voz e tradução

- [x] Capturar e reproduzir áudio pelo desktop Rust, com seleção de dispositivo,
  mute, interrupção e suspensão quando a sessão estiver bloqueada.
- [x] Usar um detector dedicado antes da ativação. Reconhecer a fala em PT-BR e
  inglês dos EUA após a ativação e usar a mesma voz feminina nos dois idiomas.
- [x] Ligar o Presence e a animação aos estados e níveis medidos de áudio.
- [x] Integrar Tradutor bidirecional ao Core. Preservar a escolha do modo entre
  turnos, encerrar por comando ou controle e separar as direções pela língua.
- [x] Validar a ponte, os dispositivos e o modo de segundo plano explícito no
  Windows. Registrar o que foi comprovado em hardware e em testes controlados.

O [Documento de Decisões](../../specs/2026-11-06-synapse-0.3-decision-charter.md)
rege PX-003, VO-001 a VO-006 e PL-004 a PL-006. Áudio transitório fica na memória
do desktop e do adaptador local. O Core recebe texto após ativação, preserva o
histórico no Presence e controla a sessão de tradução.

A [evidência dos testes](../../evidence/backend/2026-11-12-presence-voice.md)
registra a execução automatizada, os dispositivos e a validação humana.
