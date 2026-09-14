# Conversação: entrega progressiva de texto e voz

## Escopo

Texto e voz usam ChatRuntime e AgentRuntime existentes como donos de histórico,
memória e execução autorizada de ferramentas. A reconstrução da entrega não
apaga conversas nem substitui autorização por instruções para o modelo.

O histórico enviado ao modelo mantém mensagens user/assistant separadas. Seu
orçamento é limitado, mensagens system vindas do histórico são descartadas e
o turno atual permanece por último.

## Transporte

O adaptador OpenAI-compatible lê SSE incrementalmente quando existe um consumidor
do turno. Conteúdo de resposta é entregue progressivamente; raciocínio e fragmentos
de chamadas de ferramenta são montados separadamente. Um stream sem finish_reason
não é tratado como sucesso.

ChatRuntime faz a ponte entre execução síncrona e transporte com uma fila limitada
a 64 eventos e callback local à requisição. Nenhum log durável novo foi criado.
O endpoint de voz progressivo reutiliza o fluxo de voz e transmite o resultado
estruturado de áudio somente no evento final, nunca como texto da resposta.
Voz encaminha a seleção efetiva de provider/modelo usada pela interface.

Interromper ou desmontar a conversa aborta a requisição da interface. Resultados
tardios não iniciam reprodução após a interrupção. Fechar o consumidor interrompe
a publicação seguinte no backend; isso não garante interrupção imediata de uma
operação bloqueada de inferência, transcrição ou síntese. Interrupção por fala
durante a reprodução (barge-in) ainda não está implementada neste fluxo.

## Evidência de 2026-09-12

- Chat, mensagens, streaming e ferramentas: 44 testes passaram.
- Voz no boundary: 4 testes passaram com provider de teste explicitamente selecionado.
- Conversation runtime e architecture routing: 23 testes passaram.
- Cliente da interface e captura de voz: 23 testes passaram, incluindo UTF-8
  fragmentado e rejeição de resposta de voz incompleta.
- Ruff e Mypy: aprovados nos nove módulos Python deste fluxo.
- Frontend lint e build: aprovados.
- Electron: renderer compilado reproduziu WAV sintético até ended (0,1 segundo).
  Isso não comprova transcrição, qualidade audível ou uma conversa completa.
- Typecheck global da interface não aprovado na verificação anterior; build não
  substitui esse gate. Conversação falada completa com modelo local permanece pendente.

Não declarar equivalência à experiência de voz do ChatGPT a partir destes testes.

## Transcrição incerta

VoiceRuntime recusa escores de confiança fornecidos abaixo de 0,2 antes de
submit_turn. Esse limite é uma heurística conservadora, não uma probabilidade
calibrada; escore ausente continua desconhecido. A resposta `needs_repetition`
preserva a transcrição para diagnóstico, mas não cria mensagem de usuário,
não chama o modelo e não sintetiza resposta. A interface mostra a transcrição
como incerta em área limitada com scroll e volta a escutar. A retenção de
diagnóstico continua obedecendo às configurações existentes de Voice.

Verificação: cinco testes de voice conversation passaram, incluindo o escore
0,10407962094303848 observado no incidente; sete gates de routing passaram.
Ruff, Mypy dos dois módulos alterados, frontend lint/build e diff-check passaram.
