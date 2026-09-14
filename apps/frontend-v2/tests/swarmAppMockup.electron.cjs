// Presentation-only mockup: places the Swarm visual smoke inside a Synapse-style app frame.
const { app, BrowserWindow } = require('electron');
const path = require('node:path');
const fs = require('node:fs/promises');

const toFileUrl = (value) => `file:///${value.replace(/\\/g, '/')}`;

app.whenReady().then(async () => {
  let window;
  try {
    const source = path.resolve(__dirname, '../../artifacts/visual-smoke/swarm-constellation.png');
    const output = path.resolve(__dirname, '../../artifacts/visual-smoke/swarm-constellation-app-mockup.png');
    await fs.access(source);
    const html = `<!doctype html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    :root {
      --bg: #06181b;
      --panel: rgba(5, 22, 28, 0.82);
      --panel-strong: rgba(7, 31, 38, 0.94);
      --line: rgba(39, 231, 224, 0.26);
      --text: #e0fbff;
      --muted: rgba(224, 251, 255, 0.62);
      --accent: #1ff4e6;
    }
    * { box-sizing: border-box; }
    html, body {
      margin: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background:
        radial-gradient(circle at 38% 34%, rgba(35, 244, 230, 0.18), transparent 34%),
        radial-gradient(circle at 82% 20%, rgba(59, 148, 255, 0.10), transparent 28%),
        linear-gradient(135deg, #071a1e 0%, #031014 52%, #07131b 100%);
      color: var(--text);
      font-family: "Segoe UI", Arial, sans-serif;
    }
    .app {
      width: 100vw;
      height: 100vh;
      border: 1px solid rgba(45, 233, 225, 0.25);
      box-shadow: inset 0 0 90px rgba(0, 255, 240, 0.05);
      position: relative;
    }
    .top {
      height: 58px;
      display: flex;
      align-items: center;
      gap: 24px;
      padding: 0 28px;
      border-bottom: 1px solid var(--line);
      background: rgba(2, 12, 16, 0.72);
      backdrop-filter: blur(18px);
      letter-spacing: 0.35em;
      text-transform: uppercase;
    }
    .logo {
      width: 34px;
      height: 34px;
      border: 1px solid var(--accent);
      border-radius: 10px;
      display: grid;
      place-items: center;
      color: var(--accent);
      font-weight: 800;
      letter-spacing: 0;
      box-shadow: 0 0 22px rgba(31, 244, 230, 0.24);
    }
    .status {
      letter-spacing: 0.08em;
      font-size: 12px;
      padding: 7px 12px;
      border: 1px solid rgba(31, 244, 230, 0.22);
      border-radius: 999px;
      color: var(--muted);
      text-transform: none;
    }
    .status::before {
      content: "";
      display: inline-block;
      width: 8px;
      height: 8px;
      margin-right: 8px;
      border-radius: 99px;
      background: #26ff8e;
      box-shadow: 0 0 14px #26ff8e;
    }
    .window-actions {
      margin-left: auto;
      display: flex;
      gap: 22px;
      letter-spacing: 0;
      color: rgba(224, 251, 255, 0.78);
      font-size: 22px;
    }
    .rail {
      position: absolute;
      top: 58px;
      left: 0;
      bottom: 0;
      width: 74px;
      border-right: 1px solid var(--line);
      background: rgba(3, 13, 17, 0.66);
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 18px;
      padding-top: 28px;
    }
    .rail button {
      width: 48px;
      height: 48px;
      border: 1px solid rgba(31, 244, 230, 0.24);
      border-radius: 14px;
      background: rgba(10, 37, 45, 0.72);
      color: var(--accent);
      font-size: 20px;
      box-shadow: 0 0 18px rgba(31, 244, 230, 0.10);
    }
    .rail button.active {
      border-color: var(--accent);
      box-shadow: 0 0 28px rgba(31, 244, 230, 0.26);
    }
    .content {
      position: absolute;
      inset: 58px 0 0 74px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 370px;
      gap: 18px;
      padding: 20px 22px 22px;
    }
    .stage {
      position: relative;
      overflow: hidden;
      border: 1px solid rgba(31, 244, 230, 0.18);
      border-radius: 24px;
      background:
        radial-gradient(circle at 46% 36%, rgba(0, 255, 234, 0.10), transparent 38%),
        rgba(2, 10, 13, 0.42);
      box-shadow: inset 0 0 80px rgba(31, 244, 230, 0.05), 0 24px 80px rgba(0, 0, 0, 0.32);
    }
    .stage img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
      opacity: 0.98;
    }
    .caption {
      position: absolute;
      left: 30px;
      bottom: 28px;
      padding: 18px 22px;
      max-width: 560px;
      border: 1px solid rgba(31, 244, 230, 0.26);
      border-radius: 18px;
      background: rgba(3, 18, 23, 0.76);
      backdrop-filter: blur(16px);
      box-shadow: 0 0 38px rgba(31, 244, 230, 0.10);
    }
    .caption h1 {
      margin: 0 0 7px;
      font-size: 23px;
      letter-spacing: 0.01em;
    }
    .caption p {
      margin: 0;
      color: var(--muted);
      line-height: 1.4;
      font-size: 14px;
    }
    .chat {
      border: 1px solid rgba(31, 244, 230, 0.22);
      border-radius: 22px;
      background: var(--panel);
      box-shadow: inset 0 0 54px rgba(31, 244, 230, 0.04);
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .chat-top {
      display: flex;
      justify-content: flex-end;
      gap: 10px;
    }
    .round {
      width: 34px;
      height: 34px;
      border: 1px solid rgba(31, 244, 230, 0.24);
      border-radius: 10px;
      display: grid;
      place-items: center;
      color: var(--accent);
    }
    .bubble {
      margin-top: 68px;
      border: 1px solid rgba(31, 244, 230, 0.16);
      border-radius: 18px;
      padding: 18px;
      background: rgba(8, 29, 36, 0.78);
      color: rgba(224, 251, 255, 0.90);
      line-height: 1.45;
    }
    .bubble strong {
      color: var(--accent);
    }
    .composer {
      margin-top: auto;
      height: 54px;
      border: 1px solid rgba(31, 244, 230, 0.22);
      border-radius: 999px;
      display: flex;
      align-items: center;
      padding: 0 12px 0 18px;
      color: rgba(224, 251, 255, 0.38);
      background: rgba(3, 16, 21, 0.82);
    }
    .send {
      margin-left: auto;
      width: 38px;
      height: 38px;
      border-radius: 999px;
      display: grid;
      place-items: center;
      background: rgba(31, 244, 230, 0.22);
      color: var(--accent);
      box-shadow: 0 0 22px rgba(31, 244, 230, 0.24);
    }
  </style>
</head>
<body>
  <main class="app">
    <header class="top">
      <div class="logo">S</div>
      <div>SYNAPSE</div>
      <div class="status">visual smoke</div>
      <div class="window-actions"><span>−</span><span>□</span><span>×</span></div>
    </header>
    <nav class="rail">
      <button>▣</button>
      <button class="active">✦</button>
      <button>☷</button>
      <button style="margin-top:auto;margin-bottom:22px">⚙</button>
    </nav>
    <section class="content">
      <section class="stage">
        <img src="${toFileUrl(source)}" alt="Swarm visual smoke">
        <div class="caption">
          <h1>Swarm visual: agentes, modelos e ferramentas</h1>
          <p>Representação visual de uma tarefa simulada: Artemis coordena especialistas, modelos locais e ferramentas durante pesquisa, edição e validação.</p>
        </div>
      </section>
      <aside class="chat">
        <div class="chat-top"><div class="round">＋</div><div class="round">›</div></div>
        <div class="bubble">
          <strong>Artemis</strong><br>
          Smoke visual concluído. A constelação mostra agentes criados, modelos conectados e ferramentas em uso durante uma tarefa simulada de melhoria de UI.
        </div>
        <div class="composer">Mensagem para a Synapse... <div class="send">➤</div></div>
      </aside>
    </section>
  </main>
</body>
</html>`;
    window = new BrowserWindow({
      width: 1600,
      height: 1000,
      show: false,
      webPreferences: {
        sandbox: true,
        contextIsolation: true,
        nodeIntegration: false,
        webSecurity: false,
        offscreen: true
      }
    });
    await window.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`);
    await new Promise((resolve) => setTimeout(resolve, 1200));
    await fs.mkdir(path.dirname(output), { recursive: true });
    await fs.writeFile(output, (await window.webContents.capturePage()).toPNG());
    console.log(JSON.stringify({ output }, null, 2));
    app.exit(0);
  } catch (error) {
    console.error(error);
    app.exit(1);
  }
});
