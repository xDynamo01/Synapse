# Presence por voz e Tradutor no Windows

A escuta começa desativada. Abra uma conversa e selecione o modelo local. Em
**Presence**, use **Ativar microfone** e diga “Artemis”. Aguarde o estado
**Ouvindo** para falar. Após cada resposta, o Presence volta a ouvir. Depois
de 30 segundos sem fala, volta a aguardar o nome de ativação. O tempo é
ajustável em **Áudio**, entre 5 e 120 segundos. O controle **Interromper** cancela a resposta em curso.
Em **Áudio**, selecione a entrada, a saída e o nome de ativação. A mudança de
nome fica disponível com o microfone desativado.

## Preparar os modelos locais

Em um ambiente Python 3.12 dedicado, instale as dependências de voz e use o
provisionador para baixar e verificar os arquivos dos modelos. As variáveis
abaixo devem estar presentes no processo que inicia o desktop.

```powershell
uv venv --python 3.12 $voiceVenv
uv pip install --python (Join-Path $voiceVenv 'Scripts/python.exe') -r backend/python/requirements-voice.txt
py -3.14 backend/python/provision_voice.py $voiceModels
$env:SYNAPSE_VOICE_PYTHON = (Resolve-Path (Join-Path $voiceVenv 'Scripts/python.exe')).Path
$env:SYNAPSE_VOICE_MODELS = (Resolve-Path $voiceModels).Path
```

Use o [guia do aplicativo](windows-native-desktop.md) para iniciar o Core, o
cliente e o modelo conversacional local. O detector PocketSphinx recebe o
áudio antes da ativação. A transcrição Faster Whisper ocorre depois da
ativação. O Supertonic-3 usa o perfil feminino original F1 nas duas línguas.
O modelo de síntese expõe `pt` e `en`. Sua seleção de idioma não distingue
variantes regionais. [PocketSphinx](https://pocketsphinx.readthedocs.io/en/stable/pocketsphinx.html) ·
[Faster Whisper Base](https://huggingface.co/Systran/faster-whisper-base) ·
[Supertonic-3](https://huggingface.co/Supertone/supertonic-3)

## Tradução e áudio em segundo plano

Escolha a língua do proprietário e inicie o Tradutor pelo controle do Presence.
Também é possível dizer “Traduza para inglês” ou “Translate to Portuguese”
depois da ativação. Os turnos em português e inglês alternam a direção
pelo idioma detectado. Fale um de cada vez e aguarde a reprodução terminar.
O aplicativo descarta a entrada durante a reprodução e o intervalo de eco.
Falas com detecção ambígua pedem repetição. O microfone único não identifica
duas pessoas que falem simultaneamente no mesmo idioma.

O modo fica ativo entre turnos. Diga “Pare a tradução” ou “Stop translating”,
ou use **Encerrar tradução**. A conversa normal pode guardar a transcrição
no chat selecionado. O áudio fica em memória e os turnos do Tradutor não
entram no histórico ou na memória canônica.

Para continuar ouvindo após fechar a janela, habilite **Manter áudio ativo na
bandeja ao fechar**. A bandeja oferece abrir, silenciar e sair. A captura para
quando a sessão bloqueia, desconecta ou não pode ser verificada. Reative o
microfone após desbloquear. O modo de segundo plano começa desligado.

## Ponte de diagnóstico

Use `voice_devices`, `voice_configure`, `voice_enable`, `voice_disable`,
`voice_interrupt`, `translator_start` e `translator_stop` pelo `--bridge`.
`voice_enable` aceita `model` e `diagnostic`. Com `diagnostic:true`, a captura
física fica desligada. `voice_feed_pcm` aceita `pcm` em Base64, mono PCM16
little-endian a 16 kHz, em quadros de até meio segundo. O mesmo detector,
transcritor, Core e sintetizador processam o áudio fornecido. A saída usa o
dispositivo escolhido. A ponte devolve estados e níveis de áudio em `voice`.
