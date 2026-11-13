# Presence por voz e Tradutor no Windows x64

O Qwen no LM Studio foi carregado com contexto de 32.768 tokens. A ponte
executou o fluxo com amostras sintéticas locais de PT-BR e inglês. A saída
foi enviada a um dispositivo de áudio real e o callback informou nível acima
de zero. O teste observou a rejeição de entrada de diagnóstico durante a
reprodução.

- Uma fala sem a palavra de ativação permaneceu no detector. O clipe
  “Ártemis” abriu a escuta e uma pergunta em português recebeu resposta
  em português. O histórico guardou a pergunta e a resposta.
- O Tradutor produziu e reproduziu saídas PT→EN e EN→PT com o mesmo perfil
  feminino Supertonic-3 F1. A tradução de “fechada” como “locked” introduziu
  uma nuance ausente no original. O teste verifica o fluxo, as direções e
  termos selecionados da frase, com a variação semântica registrada.
- Um novo processo cliente reencontrou o Tradutor ativo. “Stop translating”
  e o comando manual encerraram o modo. Os testes do Core também cobriram
  cancelamento em andamento, sessão persistente e texto fora do armazenamento.
- Os testes do dispositivo Windows abriram a captura padrão e a entrada
  selecionada, validaram reprodução, interrupção e drenagem. O teste Win32
  instalou a bandeja e exercitou seus eventos. A política WTS usou casos
  controlados de bloqueio, desconexão e sessão indisponível.
- A execução local dos adaptadores confirmou a mesma voz F1 para `pt` e `en`,
  três pronúncias sintéticas da ativação e rejeição de três falas sem a palavra.
  O transcritor identificou um clipe misto como ambíguo. Esse resultado não mede
  sobreposição física de dois falantes no mesmo idioma.

No teste humano com o microfone do Windows, o Core registrou duas conversas
concluídas. O usuário confirmou que ouviu as duas respostas, em português e
em inglês, e percebeu a mesma voz. A avaliação não certifica sotaques
regionais. A interface usa níveis medidos de entrada e saída. O registro da
bandeja e a política de sessão foram testados separadamente, sem bloquear a
sessão real do usuário. Logs locais em `.superpowers/voice-stage13/`.

A suíte Rust passou com 82 testes regulares, e dois testes adicionais de
hardware e bandeja passaram quando executados explicitamente. A suíte Python
passou com 14 testes. O fluxo da ponte foi repetido com o binário final.

[Guia de Presence e Tradutor](../../guides/windows-presence-voice.md).
