# ADR 0004 · Fundação desktop Rust + Slint

Status: aprovado para avaliação em paralelo. A promoção a cliente principal
depende de evidência de integração e dos critérios de plataforma do charter.

O pacote `synapse-desktop-slint` introduz uma interface nativa declarativa.
Slint apresenta estado e eventos de interação. O host Rust controla a janela
e traduz ações em chamadas ao contrato versionado quando integradas. A rota
alvo é Slint → host Rust → Core Rust v1 → workers Python. O Core mantém
autoridade e persistência. Python continua responsável pelas capacidades de IA.

Os ADRs 0001 e 0002 já registram Electron como premissa superada. Este ADR
complementa a decisão nativa e preserva o transporte v1 e seu escopo de
autoridade. O cliente eframe continua disponível durante a avaliação.
Slint, Winit e o renderer por software são a configuração inicial da
fundação. Build, smoke e testes locais não certificam outras plataformas.
