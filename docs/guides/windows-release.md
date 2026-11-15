# Synapse 0.3 no Windows

Use PowerShell 7, Python 3.14 e uma pasta de Workspace local. O Core associa
o banco de estado à pasta escolhida. Reutilize os mesmos caminhos para
reabrir o histórico após uma atualização.

## Instalar e iniciar

1. Obtenha o ZIP Windows e seu arquivo SHA-256 na release da plataforma.
2. Compare o hash do ZIP com o publicado antes de extrair o instalador.
3. Execute o script do pacote com o caminho do ZIP e o hash publicado.

   ```powershell
   Get-FileHash -Algorithm SHA256 -LiteralPath $zip
   & $installer -Package $zip -Sha256 $publishedSha256
   ```

4. Abra a versão instalada com o script `start-windows.ps1`. Ele inicia o
   Core local, aguarda o canal Windows e abre o desktop. O script encerra
   o Core ao sair. Os parâmetros `-InstallRoot`, `-StateRoot`,
   `-Workspace` e `-Python` permitem indicar caminhos locais.

   ```powershell
   $distribution = Join-Path $env:LOCALAPPDATA 'Synapse\distribution'
   $active = (Get-Content (Join-Path $distribution 'active.json') -Raw |
       ConvertFrom-Json).current
   $programs = Join-Path (Join-Path $distribution 'versions') $active
   & (Join-Path $programs 'start-windows.ps1')
   ```

O ZIP inclui o Core, o desktop, os analisadores e os módulos Python. O
interpretador, o provedor local de modelos, os pesos de voz, o Chromium e
os runtimes de QA são instalados ou configurados na máquina. Nenhum
estado de usuário é incluído no pacote.

## Configuração das capacidades

- **Conversa e Workspace.** Configure o LM Studio em loopback e registre
  no Synapse o identificador exato do modelo carregado. Use o histórico
  para retomar um chat e uma referência explícita para consultar memória.
- **Voz e tradução.** Crie um ambiente Python de voz, instale
  `python/requirements-voice.txt` e provisione os modelos com
  `python/provision_voice.py`. Configure `SYNAPSE_VOICE_PYTHON` e
  `SYNAPSE_VOICE_MODELS` antes de iniciar o aplicativo.
- **Navegador.** Use o [guia do Chromium dedicado](windows-browser-reader.md).
  Nos comandos de instalação, substitua `backend/python` por `python`
  no diretório da versão instalada.
- **QA de projetos.** Configure e preserve o manifesto do
  [runtime de verificação](windows-mission-recovery.md).
  As receitas autorizadas precisam das ferramentas correspondentes.

## Atualização e reversão

Feche o Synapse antes de trocar a versão. Faça uma cópia do diretório de
estado com o Core encerrado. Execute o mesmo instalador com o novo ZIP e
o respectivo SHA-256. O instalador muda a versão ativa após verificar o
pacote, e o Core migra o banco ao reabrir o estado.

```powershell
& $installer -Rollback
```

A reversão troca os arquivos de programa ativos. O estado continua no
diretório local. Se a versão anterior exigir um esquema antigo, preserve
a cópia atual e inicie a versão anterior com a cópia de estado feita antes
da atualização, usando o mesmo Workspace.

Use os recibos e o [guia de recuperação](windows-mission-recovery.md) para
resolver uma publicação interrompida. O Core distingue gravações que
foram aplicadas daquelas que ficaram preparadas.
