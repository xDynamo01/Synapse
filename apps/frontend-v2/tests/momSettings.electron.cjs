// Isolated UI QA. No real backend, models, settings or application user data.
const { app, BrowserWindow } = require('electron');
const path = require('node:path');
const fs = require('node:fs/promises');
app.whenReady().then(async () => {
  let window;
  try {
    const { build } = await import('vite');
    const output = path.resolve(__dirname, '../../../.cache/synapse/mom-settings-qa');
    await build({ configFile: false, root: path.join(__dirname, 'mom-settings'), base: './',
      plugins: [{ name: 'isolate-settings-panel', enforce: 'pre', transform(source, id) {
        if (!id.replaceAll('\\', '/').endsWith('/src/renderer/main.tsx')) return;
        const mount = source.lastIndexOf('createRoot(document.getElementById');
        if (mount < 0) throw new Error('QA mount marker not found');
        return source.slice(0, mount) + '\nexport { SettingsPanel };';
      }}], build: { outDir: output, emptyOutDir: false }, logLevel: 'warn' });
    window = new BrowserWindow({width:1280,height:900,show:false,webPreferences:{sandbox:true,contextIsolation:true,nodeIntegration:false,offscreen:true,backgroundThrottling:false}});
    await window.loadFile(path.join(output,'index.html'));
    const result = await window.webContents.executeJavaScript(`(async () => {
      const wait = async (check) => { for(let i=0;i<100;i++){ if(check()) return; await new Promise(r=>setTimeout(r,30)); } throw new Error('UI wait timeout'); };
      const button = text => [...document.querySelectorAll('button')].find(b=>b.textContent.trim()===text);
      await wait(()=>button('Salvar MoM') && !button('Salvar MoM').disabled);
      if(document.querySelectorAll('.mom-operation').length!==5) throw new Error('Missing specialist roles');
      if(document.querySelector('.mom-settings input[type=checkbox]')) throw new Error('Legacy activation control remains');
      const choose = async (index, model) => {
        document.querySelectorAll('.mom-operation .themed-select-trigger')[index].click();
        await wait(()=>document.querySelector('[role=option]'));
        [...document.querySelectorAll('[role=option]')].find(b=>b.textContent.startsWith(model)).click();
        await new Promise(r=>setTimeout(r,30));
      };
      await choose(1,'DeepSeek'); await choose(2,'Qwen');
      button('Salvar MoM').click();
      await wait(()=>document.body.textContent.includes('Configuração do MoM salva.'));
      if(window.stored().routes.length!==2 || window.stored().revision!==1) throw new Error('Wrong persisted routes');
      const previousSave=button('Salvar MoM');
      window.remount();
      await wait(()=>!previousSave.isConnected && button('Salvar MoM') && !button('Salvar MoM').disabled);
      if(!document.querySelectorAll('.mom-operation .themed-select-trigger')[2].textContent.includes('Qwen')) throw new Error('Lost persisted choice');
      window.failSave=true; button('Salvar MoM').click();
      await wait(()=>document.body.textContent.includes('Não foi possível confirmar'));
      if(!button('Salvar MoM').disabled) throw new Error('Unconfirmed save permits retry');
      window.failSave=false;
      const previousReads=window.requests.filter(r=>r.method==='GET').length;
      button('Recarregar MoM').click();
      await wait(()=>window.requests.filter(r=>r.method==='GET').length>previousReads && button('Salvar MoM') && !button('Salvar MoM').disabled);
      if(!document.querySelectorAll('.mom-operation .themed-select-trigger')[2].textContent.includes('Qwen')) throw new Error('Reload lost choices');
      const panel=document.querySelector('.settings-content');
      if(panel.scrollHeight<=panel.clientHeight) throw new Error('Expected bounded scrolling');
      if(window.requests.some(r=>!r.url.includes('/primary/mom/configuration'))) throw new Error('Unrelated endpoint used');
      panel.scrollTop=0;
      await new Promise(r=>setTimeout(r,150));
      window.showToggle();
      const policy = name => document.querySelector('button[aria-label="Política '+name+'"]');
      await wait(()=>policy('Responsivo'));
      await wait(()=>document.querySelector('.execution-resources summary')?.textContent==='SWARM');
      policy('Responsivo').click();
      await wait(()=>policy('Econômico') && !window.momBusy);
      if(window.stored().resource_policy!=='ECONOMICAL') throw new Error('Policy did not persist');
      if(window.resourceRegime!=='SWARM') throw new Error('Policy altered Swarm');
      document.querySelector('.execution-resources summary').click();
      if(!document.body.textContent.includes('mission-qa') || !document.body.textContent.includes('reservado')) throw new Error('Missing resource facts');
      document.querySelector('.execution-resources summary').click();
      policy('Econômico').click();
      await wait(()=>policy('Responsivo') && !window.momBusy);
      window.failSave=true;
      policy('Responsivo').click();
      await wait(()=>document.querySelector('button[aria-label="Recarregar política"]') && !window.momBusy);
      if(window.stored().resource_policy!=='RESPONSIVE') throw new Error('Failed save changed policy');
      window.failSave=false;
      document.querySelector('button[aria-label="Recarregar política"]').click();
      await wait(()=>policy('Responsivo') && !window.momBusy);
      const rect=policy('Responsivo').getBoundingClientRect();
      if(rect.top<0 || rect.bottom>window.innerHeight) throw new Error('Policy control outside viewport');
      return {roles:5,policy:true,swarmPreserved:true,persisted:true,failedSaveProtected:true,scrollable:true,requests:window.requests.length};
    })()`);
    await window.webContents.executeJavaScript(`new Promise(resolve => {
      document.querySelector('.execution-resources').open = true;
      requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(resolve, 250)));
    })`);
    await fs.writeFile(path.join(output,'settings-mom.png'),(await window.webContents.capturePage()).toPNG());
    console.log(JSON.stringify({result,output}));
    app.exit(0);
  } catch(error) {
    if(window) console.error(await window.webContents.executeJavaScript('document.body.innerText'));
    console.error(error);app.exit(1);
  }
});
