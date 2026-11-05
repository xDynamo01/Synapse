# ChatTTS opcional

O Synapse agora possui um adaptador isolado para ChatTTS. Ele não baixa pacotes,
modelos ou pesos automaticamente e não altera o provedor padrão de voz.

O adaptador exige um runtime Python separado com `ChatTTS` instalado e um diretório
local de modelos ChatTTS já validado. Crie `data/voice/chattts-runtime.json` com:

```json
{
  "python": "D:/runtimes/chattts/Scripts/python.exe",
  "model_path": "D:/models/ChatTTS",
  "device": "cuda"
}
```

Depois selecione `chattts` nas configurações de voz. O adaptador aceita somente
inglês e chinês conforme o projeto upstream. Para pt-BR, o caminho continua sendo
Kokoro/Piper.

O código do projeto ChatTTS é AGPLv3+ e os pesos publicados são CC BY-NC 4.0;
essa restrição impede ativá-lo como dependência padrão de um produto comercial.
