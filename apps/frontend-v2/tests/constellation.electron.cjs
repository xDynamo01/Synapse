// Build/run this fixture outside the governed application bundle; no backend writes.
const { app, BrowserWindow } = require('electron');
const path = require('node:path');
const fs = require('node:fs/promises');
app.whenReady().then(async () => {
  let window;
  try {
    const { build } = await import('vite');
    const output = path.resolve(__dirname, '../../..', '.cache/synapse/constellation-qa');
    await build({ configFile: false, root: path.join(__dirname, 'constellation'), base: './',
      build: { outDir: output, emptyOutDir: false }, logLevel: 'warn' });
    window = new BrowserWindow({ width: 1150, height: 800, show: false,
      webPreferences: { sandbox: true, contextIsolation: true, nodeIntegration: false, backgroundThrottling: false, offscreen: true } });
    await window.loadFile(path.join(output, 'index.html'));
    await window.webContents.executeJavaScript('window.ready');
    const results = [];
    for (const count of [2, 20, 54]) results.push(await window.webContents.executeJavaScript(`window.measure(${count})`));
    await fs.writeFile(path.join(output, '54-nodes-test.png'), (await window.webContents.capturePage()).toPNG());
    const assertions = await window.webContents.executeJavaScript(`(async () => {
      const e = window.engine;
      e.update(window.sceneFor(2), 'violet');
      await new Promise(r => setTimeout(r, 3800));
      const reclaimed = e.clusters.size === 2;
      const camera = JSON.stringify(e.target);
      const host = document.getElementById('surface');
      host.dispatchEvent(new WheelEvent('wheel', {deltaY: 400, bubbles: true}));
      for (const key of ['+', '-', 'f']) host.dispatchEvent(new KeyboardEvent('keydown', {key, bubbles:true}));
      e.pointer = {x: 20, y: 20, moved:false, id:1};
      host.dispatchEvent(new PointerEvent('pointermove', {clientX:120, clientY:90}));
      e.cancel();
      e.update(window.sceneFor(2), 'violet');
      const preserved = JSON.stringify(e.target) === camera;
      const scene = window.sceneFor(3);
      scene.flows = [{id:'test-flow', edgeId:'edge:2', occurredAtRevision:4}];
      e.update(scene, 'violet'); const first = e.flights.size;
      e.update(scene, 'violet'); const deduped = e.flights.size === first && first === 1;
      await new Promise(r => setTimeout(r, 2000));
      const expired = e.flights.size === 0;
      e.update(window.sceneFor(2), 'synapse'); e.fit();
      await new Promise(r => setTimeout(r, 3800));
      const work = window.sceneFor(2);
      work.nodes = work.nodes.map(n => ({...n,motion:'active'}));
      e.update(work,'synapse');
      await new Promise(r => setTimeout(r,500));
      const activeEnergy = [...e.clusters.values()].every(c => c.energy > 0.9);
      e.update({...work,reducedMotion:true},'synapse');
      await new Promise(r => setTimeout(r,150));
      const staticReduced = [...e.clusters.values()].every(c => c.body.scale.x === 1);
      e.update({...work,status:'resyncing',reducedMotion:false},'synapse');
      await new Promise(r => setTimeout(r,700));
      const staleSuppressed = [...e.clusters.values()].every(c => c.energy < 0.05);
      e.update(window.sceneFor(2),'synapse');
      return {reclaimed,preserved,deduped,expired,activeEnergy,staticReduced,staleSuppressed};
    })()`);
    await fs.writeFile(path.join(output, '2-nodes-test.png'), (await window.webContents.capturePage()).toPNG());
    console.log(JSON.stringify({ results, assertions }));
    if (Object.values(assertions).some(v => v !== true)) throw new Error(JSON.stringify(assertions));
    if (results.some(result => result.fps < 25)) throw new Error('FPS below local QA floor: ' + JSON.stringify(results));
    console.log(JSON.stringify({ results, assertions, output }, null, 2));
    app.exit(0);
  } catch (error) { console.error(error); app.exit(1); }
});
