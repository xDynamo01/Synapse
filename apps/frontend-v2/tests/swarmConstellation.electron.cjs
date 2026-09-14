// Visual smoke only: renders a simulated Swarm through the real constellation canvas.
const { app, BrowserWindow } = require('electron');
const path = require('node:path');
const fs = require('node:fs/promises');

app.whenReady().then(async () => {
  let window;
  try {
    const { build } = await import('vite');
    const output = path.resolve(__dirname, '../../.cache/synapse/swarm-constellation-qa');
    const screenshot = path.resolve(__dirname, '../../artifacts/visual-smoke/swarm-constellation.png');
    await build({
      configFile: false,
      root: path.join(__dirname, 'swarm-constellation'),
      base: './',
      build: { outDir: output, emptyOutDir: true },
      logLevel: 'warn'
    });
    window = new BrowserWindow({
      width: 1440,
      height: 900,
      show: false,
      webPreferences: {
        sandbox: true,
        contextIsolation: true,
        nodeIntegration: false,
        backgroundThrottling: false,
        offscreen: true
      }
    });
    await window.loadFile(path.join(output, 'index.html'));
    await window.webContents.executeJavaScript('window.ready');
    await new Promise((resolve) => setTimeout(resolve, 2200));
    const facts = await window.webContents.executeJavaScript(`({
      nodes: window.scene.nodes.length,
      agents: window.scene.nodes.filter((node) => node.category === 'primary' || node.category === 'agent').length,
      models: window.scene.nodes.filter((node) => node.category === 'provider').length,
      tools: window.scene.nodes.filter((node) => node.category === 'tool').length,
      activeEdges: window.scene.edges.filter((edge) => edge.active).length
    })`);
    await fs.mkdir(path.dirname(screenshot), { recursive: true });
    await fs.writeFile(screenshot, (await window.webContents.capturePage()).toPNG());
    console.log(JSON.stringify({ screenshot, facts }, null, 2));
    if (facts.agents !== 4 || facts.models !== 3 || facts.tools !== 3 || facts.activeEdges !== 9) {
      throw new Error(`Unexpected swarm visual facts: ${JSON.stringify(facts)}`);
    }
    app.exit(0);
  } catch (error) {
    console.error(error);
    if (window) {
      try { console.error(await window.webContents.executeJavaScript('document.body.innerText')); } catch {}
    }
    app.exit(1);
  }
});
