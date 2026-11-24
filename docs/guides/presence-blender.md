# Presence da ARTEMIS no Blender

## Animação atual — JARVIS

O Presence atual usa a adaptação nativa de `ethanplusai/jarvis`, commit
`16e37bd801eb797798e02540665f8b3804b0fe14`, em
`backend/desktop-slint/src/presence.rs`. A nuvem de 2.000 partículas usa
profundidade, conexões por proximidade e transições entre Idle, Ouvindo,
Pensando e Falando. O nível do TTS alimenta a reação durante a reprodução.
A simulação avança a 60 passos por segundo e a imagem é atualizada a 30 fps.
O rasterizador nativo usa pontos suavizados e linhas com antialiasing.

Código original, licença e atribuição estão em
`backend/desktop-slint/third_party/jarvis/`. A licença do autor permite uso
pessoal e não comercial. Uso comercial requer licença do autor.

As cenas Blender e os renders descritos abaixo são versões anteriores
preservadas para referência.

A versão de alta resolução do cliente Slint carrega os ciclos Idle, Pensando
e Ouvindo com a mesma fase de rotação, a 24 quadros por segundo. Gere os
quadros nativos de 800 × 800 com `tools/presence/render-desktop-hd.py`, passando
`idle`, `thinking` ou `listening` e `--eevee` após `--` na linha de comando
do Blender. `tools/presence/pack-desktop-hd.ps1` gera os arquivos `.frames`
incorporados ao executável. Cada quadro é decodificado separadamente.
Falando aplica expansão e uma onda radial à pose de Idle com o nível medido
na reprodução do TTS.
A frase usada na prévia do Blender não é reproduzida no aplicativo.

No Windows, abra uma conversa com um modelo local, clique no microfone e
diga “Artemis”. Os estados Ouvindo e Falando usam o serviço local descrito
em [Presence por voz](windows-presence-voice.md), inclusive as variáveis
`SYNAPSE_VOICE_PYTHON` e `SYNAPSE_VOICE_MODELS`. A captura inicia desativada.

## Faixas holográficas — estudo estático

`tools/presence/bands-study.py` abre o núcleo aprovado de `core-study-v2`
e acrescenta quatro faixas de placas curvas, em coleções e eixos independentes.
Raios: 1,45 / 1,93 / 2,43 / 2,96 (núcleo de raio 1). A segunda e a quarta
faixas ocupam 180 graus; a primeira e a terceira completam 360 graus,
com pequenas juntas entre placas. Os circuitos e contatos ficam nas placas;
os intervalos entre faixas ficam vazios. Não há animação nesta etapa.

Execute com Blender em segundo plano, usando `--python tools/presence/bands-study.py`.
Requer `target/presence-blender/core-study-v2/synapse-core.blend`, gerado
por `core-study.py`. Saídas em `target/presence-blender/bands-study-v1/`:
`synapse-core-bands.blend`, `bands-front.png`, `bands-angle.png` e
`validation.json`. O aplicativo e seus recursos não são alterados.

A revisão atual escreve em `bands-study-v2`: placas recortadas com larguras
variadas, sete barramentos por faixa, trilhas curvas gravadas, módulos e
contatos impressos. As superfícies ficam em profundidades ligeiramente
diferentes para compor a aparência de holograma tecnológico. Os quatro eixos,
dois semicírculos e objetos do núcleo aprovado são preservados. A revisão v1
permanece disponível para comparação. A semelhança visual requer avaliação
do usuário; não representa reprodução exata da referência.

A revisão v3 (`bands-study-v3`) altera a estrutura: lâminas com abertura
radial e profundidade axial, comprimentos desiguais, sobreposições escalonadas
e agrupamentos locais de circuitos. Três barramentos fragmentados substituem
os sete trilhos regulares. Novos eixos reduzem a silhueta oval da vista frontal.
Os raios passam a 1,40 / 1,96 / 2,55 / 3,12. Permanecem quatro faixas e dois
semicírculos, sem animações, texturas da referência ou elementos entre faixas.
O núcleo aprovado continua vindo do mesmo arquivo v2, sem mudanças de material
ou geometria. As revisões anteriores e o aplicativo permanecem intactos.

A revisão v4 (`bands-study-v4`), por pedido posterior do usuário, reduz o
núcleo para 58% do tamanho anterior e a emissão de sua borda de 0,55 para
0,065. As faixas ficam aproximadamente 60% mais estreitas. Quatro volumes
esféricos translúcidos de raios 0,95 / 1,65 / 2,24 / 2,82 preenchem os
intervalos, com contornos parciais de baixa intensidade em superfícies 3D.
Não há partículas nem animação. A referência dourada orienta a estrutura;
a paleta continua ciano/violeta. O arquivo original do núcleo não é alterado.

## Núcleo isolado — estudo estático

`tools/presence/core-study.py` gera somente a região central da referência:
membrana óptica translúcida, luz branca rosada e filamentos violetas internos.
Na revisão v2, os arcos orbitais foram removidos a pedido do usuário.
A referência orienta a modelagem; não é aplicada
como textura. Sem animação, sem alteração do executável ou dos atlas.

Execute o script com os mesmos argumentos de Blender em segundo plano
usados abaixo, trocando `layered-model.py` por `core-study.py`.
Saídas em `target/presence-blender/core-study-v2/`: `synapse-core.blend`,
`core-front.png`, `core-angle.png` e `validation.json`.

## Estudo estático por camadas — 17/11/2026

O estudo `tools/presence/layered-model.py` modela geometria independente,
sem textura da referência, partículas ou animação. Quatro coleções separam
núcleo de vidro, anéis internos, arcos externos e painéis curvos com circuitos.
O objetivo desta etapa é avaliar forma, transparência e espaços vazios antes
de detalhar ou integrar novamente ao aplicativo.

```powershell
& 'F:/SteamLibrary/steamapps/common/Blender/blender.exe' --background --factory-startup --disable-autoexec --python-exit-code 3 --python tools/presence/layered-model.py
```

Saída: `target/presence-blender/layered-model-v1/`, contendo o `.blend`
editável, `model-front.png`, `model-angle.png` e `validation.json`.
As duas perspectivas foram renderizadas e inspecionadas. O gerador verifica
ausência de animações e texturas de imagem. Este estudo não substitui atlas
do frontend nem o executável do Synapse. A aprovação visual ainda está pendente.

A ponte local executa o gerador `tools/presence/presence.py` no Blender
em segundo plano. O script PowerShell controla resolução, semente e tipo
de render. Cada configuração escreve em uma pasta própria de
`target/presence-blender`.

```powershell
./tools/presence/render.ps1 -Mode still -Size 540
./tools/presence/render.ps1 -Mode loop -Size 720
```

O Blender 5.3 é a versão validada. Passe `-Blender caminho\blender.exe`
se a instalação não estiver na Steam Library usada por padrão. O modo
loop também requer FFmpeg. O render gera um `.blend` editável, um PNG
de referência e, no modo loop, os quadros e o MP4.

Use `-Artwork caminho\referencia.png` para usar a arte como base e gerar
a variante `reference`. A imagem é incorporada ao `.blend`. As trajetórias
dos pulsos foram alinhadas para a referência quadrada enviada para a ARTEMIS.

Use `-Circuits -Mode loop -Size 720` para gerar a malha 3D com módulos de
coleta e transformação, saltos entre anéis e a esfera translúcida.

Use `-Relief -Artwork caminho\referencia.png -Mode loop -Size 720` para
projetar a segunda referência sobre uma malha curva em profundidade. A
câmera e a esfera de vidro são objetos 3D. O desenho externo permanece uma
textura incorporada ao arquivo. A máscara central e as rotas dos pulsos são
específicas para a referência com o símbolo em S.

Use `-Sphere -Mode loop -Size 720` para a versão construída com trilhas
esféricas em vários planos, vidro no centro e pulsos entre camadas.
A câmera percorre a geometria em perspectiva ao longo do ciclo.

Use `-Wrap -Artwork caminho\referencia.png -Mode loop -Size 720` para
aplicar a imagem original a uma esfera fechada. A projeção frontal se
repete no hemisfério traseiro, com as mesmas coordenadas no equador. O
loop gira a esfera e pulsa sua escala.

A animação tem 144 quadros a 24 fps. O quadro 145 repete a pose inicial
para fechar as curvas de animação e fica fora do vídeo exportado. O
arquivo também serve como fonte para a prévia dentro do Synapse. Para
exportar a cena de circuitos esféricos para o frontend:

```powershell
./tools/presence/render.ps1 -Sphere -Mode loop -Size 720 -Seed 2421
./tools/presence/export-slint.ps1 -Frames ./target/presence-blender/sphere-loop-720-2421/frames
```

O script gera dois atlas com 96 quadros ao todo, amostrados a 16 fps.
O executável carrega esses atlas como recursos próprios. Ao abrir o
Workspace ou Configurações, o componente de reprodução sai da tela
e seu temporizador é encerrado.
