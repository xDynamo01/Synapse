# Ordem de execução das pendências da Synapse v0.01

Este documento organiza as pendências restantes em uma sequência automatizável. A regra principal é resolver primeiro itens pequenos e persistentes que limpam o estado do produto, depois atacar fluxos mais complexos como Conversation Mode/TTS.

Não alterar versão, não implementar v0.02 e não considerar build/teste isolado como validação final quando o requisito envolver comportamento no runtime real.

## Princípio de execução

Para cada item:

```text
reproduzir
→ localizar primeira fronteira ausente
→ corrigir causa raiz mínima
→ adicionar regressão proporcional
→ rebuild afetado
→ validar no runtime local real
→ registrar evidência
→ avançar para o próximo item
```

Se uma etapa falhar por defeito técnico, corrigir e repetir. Falha técnica investigável não é blocker humano.

## 1. History delete real

Prioridade: alta.

Objetivo: apagar conversas de forma persistente, não apenas remover visualmente da lista.

Escopo:

- Backend/persistência de conversas.
- Rota ou fronteira frontend-safe para deletar conversa.
- Botão de lixeira em cada card do History.
- Botão `Clear` para limpar conversas elegíveis.
- Refresh e restart não podem trazer conversas apagadas de volta.

Gate:

- Criar ou usar conversas existentes.
- Deletar uma conversa.
- Apertar Refresh.
- Fechar e reabrir o app.
- Confirmar que a conversa apagada não retorna.

Condição de saída:

```text
History delete persistente validado.
```

## 2. Conversation Mode lifecycle

Prioridade: alta.

Objetivo: o modo conversa deve continuar funcionando depois da primeira fala, sem travar em loop e sem impedir o STT manual depois de sair.

Escopo:

- Estados de sessão de voz.
- Transições `idle`, `listening`, `recording`, `processing`, `thinking`, `speaking`, `cooldown`, `error`.
- Reutilização segura de `voice_session_id`.
- Encerramento limpo do modo conversa.
- Liberação de microfone/tracks.

Gate:

- Ativar Conversation Mode.
- Falar primeira frase curta.
- Receber resposta.
- Falar segunda frase curta.
- Receber segunda resposta.
- Desativar Conversation Mode.
- Usar STT manual depois disso.

Condição de saída:

```text
Conversation Mode não trava após primeira mensagem e libera o microfone ao sair.
```

## 3. TTS e playback real

Prioridade: alta.

Objetivo: a Synapse deve falar a resposta por áudio enquanto o texto aparece no Conversation Log.

Escopo:

- Provider TTS selecionado.
- Voice id canônico.
- Voice-pack pt-BR.
- Síntese Piper.
- Resolução de `audio_reference`.
- Envio de `audio_base64` ou áudio reproduzível ao renderer.
- Playback no Electron.
- Tratamento de `TTS playback failed`.
- Tratamento de `UnicodeEncodeError`.

Gate:

- Enviar fala pelo Conversation Mode.
- Confirmar resposta textual no Conversation Log.
- Confirmar áudio audível.
- Confirmar que falha de áudio não apaga nem bloqueia a resposta textual.

Condição de saída:

```text
Resposta textual + áudio TTS funcionam no modo conversa.
```

## 4. Proteção contra eco da própria Synapse

Prioridade: alta.

Objetivo: impedir que o microfone capture a fala da Synapse e gere nova pergunta falsa.

Escopo:

- Cooldown entre `speaking` e `listening`.
- Bloqueio de captura enquanto TTS toca.
- Detecção de transcript repetitivo.
- Ignorar eco antes de salvar histórico ou chamar LM.
- Não exibir erro falso ao ignorar eco.

Gate:

- Fazer a Synapse responder por áudio.
- Manter Conversation Mode ativo.
- Confirmar que o áudio da própria Synapse não vira nova mensagem do usuário.
- Confirmar ausência de loops tipo “o que é o que é...”.

Condição de saída:

```text
Eco/repetição não entra no chat nem no histórico.
```

## 5. Calibração STT pt-BR

Prioridade: média.

Objetivo: melhorar reconhecimento de português sem bloquear a estabilização do modo conversa.

Escopo:

- Idioma enviado ao STT.
- Modelo STT adequado para pt-BR.
- VAD.
- Tempo mínimo/máximo de gravação.
- Normalização de transcript.
- Ruído ambiente.

Gate:

- Frases curtas:
  - “alô testando”
  - “qual é o seu nome”
  - “me diga uma frase curta”
- Confirmar que o texto reconhecido é aceitável para conversa básica.

Condição de saída:

```text
STT pt-BR aceitável para comandos e frases curtas.
```

## 6. Presence / orb state sync

Prioridade: média.

Objetivo: a animação central deve refletir o estado real do app sem apagar/reiniciar de forma brusca.

Escopo:

- Estado `idle`.
- Estado `listening`.
- Estado `processing/thinking`.
- Estado `speaking`.
- Amplitude de microfone/playback.
- Pulso durante resposta falada.

Gate:

- Idle: animação sutil.
- Listening: indicação de escuta.
- Thinking: estado perceptível sem piscar.
- Speaking: pulso contínuo ligado ao áudio.
- Volta limpa ao idle.

Condição de saída:

```text
Presence acompanha Conversation Mode sem flicker visual.
```

## 7. Conversation Log polish

Prioridade: média.

Objetivo: simplificar o painel para reduzir ruído visual.

Escopo:

- Remover excesso de texto no header.
- Remover `IDLE` do Conversation Log.
- Substituir `New Chat` por botão `+` mais sutil.
- Remover lixeira do Conversation Log; lixeira deve ficar apenas em cards do History.
- Garantir espaçamento entre botões.
- Quando o log abrir, acomodar a Presence para não ficar coberta.

Gate:

- Abrir/fechar Conversation Log.
- Criar New Chat pelo `+`.
- Confirmar que mensagens continuam legíveis.
- Confirmar que a esfera permanece em foco visual.

Condição de saída:

```text
Conversation Log limpo e consistente com o visual atual.
```

## 8. Attachments

Prioridade: média.

Objetivo: anexos devem funcionar com ícone correto e fluxo real.

Escopo:

- Botão de anexar como clipe de papel.
- File picker allowlisted.
- Staging real.
- Chips de anexos no composer.
- Remoção de anexo antes do envio.
- Associação ao próximo turno textual.

Gate:

- Selecionar arquivo.
- Ver chip.
- Remover chip.
- Selecionar novamente.
- Enviar mensagem com anexo.
- Confirmar referência no histórico/conversa.

Condição de saída:

```text
Attachments reais funcionam no composer.
```

## 9. Activity / Constellation

Prioridade: baixa para v0.01, alta para v0.02.

Objetivo atual recomendado: não mostrar debug/código solto; exibir estado honesto de recurso futuro se a constelação factual ainda não estiver pronta.

Escopo v0.01:

- Remover IDs/debug visual da tela.
- Exibir faixa ou mensagem discreta: recurso visual completo em próxima versão.
- Manter Presence como visual principal.
- Não inventar nós, swarm ou workers fictícios.

Gate v0.01:

- Abrir Activity/Constellation.
- Confirmar que não aparece `activity unavailable` nem código solto.
- Confirmar mensagem de recurso futuro ou estado vazio factual.

Condição de saída v0.01:

```text
Constellation não quebra UX e não mostra estado técnico cru.
```

Escopo futuro:

- Renderização factual de Primary Agent, Model/Runtime e demais participantes reais.
- Nós/arestas orgânicos.
- Eventos operacionais reais.
- Sem simulação enganosa.

## 10. Runtime/build hygiene

Prioridade: contínua.

Objetivo: impedir que o app carregue bundle antigo ou documentação antiga como fluxo executável.

Escopo:

- Um entrypoint local governado.
- Remoção/aposentadoria de runtimes antigos executáveis.
- Documentação histórica fora do fluxo executável.
- Build provenance visível.
- Cache/runtime antigo não deve vencer o bundle atual.

Gate:

- Iniciar runtime local.
- Confirmar caminho executável.
- Confirmar build id/renderer id.
- Confirmar que features recém-alteradas aparecem.

Condição de saída:

```text
Runtime local abre somente a versão atual esperada.
```

## 11. Validação local final

Prioridade: final.

Objetivo: confirmar o fluxo de uso principal sem depender de fixture isolada.

Gate final:

1. Abrir app local atual.
2. Confirmar backend ready.
3. Criar New Chat.
4. Enviar mensagem textual.
5. Confirmar resposta real.
6. Usar STT manual.
7. Usar Conversation Mode por pelo menos duas falas.
8. Confirmar TTS audível.
9. Confirmar Conversation Log atualizado.
10. Deletar conversa no History.
11. Refresh não restaura conversa deletada.
12. Restart não restaura conversa deletada.
13. Confirmar Presence sem flicker.
14. Confirmar Activity sem debug cru.

Condição de saída:

```text
Synapse v0.01 fluxo local principal validado.
```

## Ordem recomendada resumida

```text
1. History delete real
2. Conversation Mode lifecycle
3. TTS/playback real
4. Proteção contra eco
5. STT pt-BR calibration
6. Presence/orb state sync
7. Conversation Log polish
8. Attachments
9. Activity/Constellation fallback honesto
10. Runtime/build hygiene contínuo
11. Validação local final
```
