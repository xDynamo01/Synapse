// Checks the shipped page, without the legacy E2E harness or backend mutations.
const { app, BrowserWindow } = require('electron');
const path = require('node:path');
const fs = require('node:fs/promises');
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1320, height: 840, show: false, webPreferences: { offscreen: true, backgroundThrottling: false, sandbox: true, contextIsolation: true } });
  const report = path.resolve(__dirname, '../../../artifacts/reports/workshop');
  try {
    await fs.mkdir(report, { recursive: true });
    await win.loadFile(path.resolve(__dirname, '../dist/renderer/index.html'));
    const result = await win.webContents.executeJavaScript(`(async () => {
      const wait = ms => new Promise(r => setTimeout(r, ms));
      for (let n=0;n<100 && !document.querySelector('.synapse-core-atmosphere-canvas');n++) await wait(100);
      const canvas = document.querySelector('.synapse-core-atmosphere-canvas');
      const image = document.querySelector('.synapse-core-atmosphere-image');
      if (!canvas || !image) throw Error('Workshop missing');
      await image.decode();
      const sample = () => {
        const left = document.createElement('canvas');
        left.width = Math.floor(canvas.width / 2); left.height = canvas.height;
        left.getContext('2d').drawImage(canvas, 0, 0);
        return left.toDataURL();
      };
      const first = sample(); await wait(1200); const second = sample();
      if (first === second) throw Error('Left workshop effects are static');
      return { animated: true, focused: document.hasFocus(), hidden: document.hidden, imageWidth: image.naturalWidth, imageHeight: image.naturalHeight, canvasWidth: canvas.width, canvasHeight: canvas.height, pointerEvents: getComputedStyle(canvas).pointerEvents };
    })()`);
    await fs.writeFile(path.join(report, 'wide.png'), (await win.webContents.capturePage()).toPNG());
    win.setSize(1000, 700);
    await new Promise(r => setTimeout(r, 600));
    await fs.writeFile(path.join(report, 'compact.png'), (await win.webContents.capturePage()).toPNG());
    await fs.writeFile(path.join(report, 'result.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
    app.exit(0);
  } catch (error) { console.error(error); app.exit(1); }
});
