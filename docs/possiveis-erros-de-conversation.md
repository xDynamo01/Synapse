# Possíveis erros de Conversation

Este documento lista causas prováveis para falhas no modo de conversação da Synapse v0.01. Ele não define novas features; serve como checklist de diagnóstico para o fluxo:

```text
microfone → gravação → STT → transcript → chat/LM → resposta textual → TTS → playback → próximo ciclo de escuta
```

## 1. Captura de áudio

- O microfone permanece preso por uma sessão anterior do Conversation Mode.
- Tracks de áudio não são liberadas após erro, cancelamento ou fechamento do modo.
- O modo manual de speech-to-text e o Conversation Mode disputam o mesmo microfone.
- A janela de escuta é curta demais e corta frases em português.
- O detector de silêncio/VAD encerra a gravação antes da fala real terminar.
- O app volta a gravar enquanto ainda há áudio da resposta sendo reproduzido.

## 2. Estado da sessão de voz

- A sessão tenta fazer uma transição inválida, por exemplo `error -> recording`.
- Uma sessão antiga em estado `error`, `processing`, `thinking` ou `speaking` é reutilizada como se estivesse pronta.
- O estado visual do frontend não acompanha o estado real do backend.
- O modo conversa fica ativo no frontend, mas a sessão backend já foi encerrada.
- O modo entra em loop entre `listening` e `processing` sem finalizar o turno anterior.

## 3. STT / transcrição

- O modelo STT está calibrado para inglês e interpreta mal fala em português.
- O idioma enviado para o provider não está como `pt-BR`.
- O VAD remove partes importantes da fala.
- Ruído ambiente, eco do alto-falante ou áudio do próprio TTS entra na próxima gravação.
- A transcrição retorna texto repetitivo, como “o que é o que é...”, e isso é enviado ao chat como se fosse fala real.
- A primeira fala funciona, mas o próximo ciclo captura sobra de áudio da resposta anterior.

## 4. Fronteira Conversation Mode → Chat

- A transcrição é concluída, mas não cria um turno de conversa.
- O `conversation_id` usado pela voz não corresponde à conversa aberta no frontend.
- O idempotency key reaproveitado impede a criação de um novo turno.
- Um erro de TTS aborta o retorno da resposta textual, mesmo quando o chat já respondeu.
- O backend salva o turno, mas o frontend só atualiza o log depois de outra ação manual.

## 5. LM / geração da resposta

- O provider/modelo configurado para chat não está disponível no runtime atual.
- A resposta textual demora mais que a janela esperada pelo modo conversa.
- O modo conversa inicia nova escuta antes de receber a resposta final.
- Erro do LM é tratado como erro genérico de voz, dificultando o diagnóstico.
- A resposta é gerada, mas não é persistida no histórico antes da etapa de áudio.

## 6. TTS / síntese de voz

- O provider de TTS salvo nas configurações aponta para uma voz/modelo removido.
- O modelo Piper existe no manifest, mas o arquivo `.onnx` ou `.onnx.json` não está acessível.
- O voice id frontend/backend diverge do id real do voice-pack.
- O texto enviado ao TTS contém caracteres que disparam erro de encoding.
- O TTS falha e a API retorna erro total, em vez de degradar apenas o áudio.
- A síntese conclui, mas o `audio_reference` não pode ser resolvido pela fronteira frontend.

## 7. Playback de áudio

- O renderer tenta tocar `audio_base64` vazio ou nulo.
- O formato informado não corresponde ao áudio real.
- O Electron bloqueia autoplay ou reprodução sem gesto do usuário.
- O Blob URL é revogado cedo demais.
- O elemento de áudio falha e deixa o modo conversa em estado inconsistente.
- O playback falha, mas o modo continua tentando alternar para escuta automaticamente.

## 8. Loop de conversa

- O app começa a escutar antes do fim da fala da assistente.
- O microfone captura a própria voz sintetizada da Synapse.
- Não existe cooldown suficiente entre `speaking` e `listening`.
- O estado `cooldown` não impede captura manual ou automática.
- O mesmo trecho de áudio é reenviado por erro de lifecycle.
- O filtro de eco acontece tarde demais, depois que o texto já foi salvo no histórico.

## 9. Frontend / UI

- O Conversation Log não atualiza imediatamente após o turno de voz.
- O estado visual mostra “pensando” ou “escutando” mesmo após erro recuperável.
- A animação central apaga/reinicia em vez de pulsar durante fala.
- O botão de Conversation Mode não desativa corretamente.
- Após usar Conversation Mode, o STT manual continua bloqueado por estado antigo.
- Erros técnicos são exibidos como falha total mesmo quando texto ou áudio degradado ainda funcionam.

## 10. Persistência e histórico

- Mensagens de voz ignoradas por eco são salvas indevidamente no histórico.
- Resposta textual gerada pelo LM não é persistida quando TTS falha.
- O frontend mantém uma visão antiga do histórico até refresh/manual action.
- O histórico restaurado usa conversa antiga enquanto o Conversation Mode aponta para nova conversa.
- Idempotency ou cache local reapresenta mensagens removidas.

## 11. Configuração empacotada/runtime

- O runtime local carrega build antigo do renderer.
- O sidecar usa voice-pack antigo ou configuração stale.
- Configuração salva aponta para provider removido.
- Recursos de voz existem no source, mas não entram no bundle/runtime usado.
- O app aberto não é o executável/build esperado.

## Checklist de investigação recomendado

1. Confirmar se o microfone está liberado antes de iniciar Conversation Mode.
2. Confirmar `voice_session_id`, estado inicial e transições reais.
3. Confirmar idioma enviado ao STT.
4. Capturar transcript bruto, duração e status.
5. Verificar se transcript repetitivo/eco foi ignorado antes do chat.
6. Confirmar se o turno chegou ao chat/LM.
7. Confirmar se a resposta textual foi salva no histórico antes do TTS.
8. Confirmar provider/voice id final usado pelo TTS.
9. Confirmar se existe áudio real retornado para o frontend.
10. Confirmar se o playback iniciou, terminou ou falhou.
11. Confirmar se o modo volta para `listening` somente após fala/cooldown.
12. Confirmar se STT manual volta a funcionar depois de encerrar Conversation Mode.
