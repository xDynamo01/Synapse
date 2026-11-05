// Electron integration smoke: bundled theme presentation only, isolated user data.
const { app, BrowserWindow } = require('electron');
const path = require('node:path');
const fs = require('node:fs/promises');
const output = path.resolve(__dirname, '../../../.cache/synapse/theme-engine-qa');
app.setPath('userData', path.join(output, 'profile'));
app.whenReady().then(async () => {
  let window;
  try {
    const { build } = await import('vite');
    await build({ configFile:false, root:path.join(__dirname,'theme-engine'), base:'./',
      plugins:[{name:'isolate-theme-settings',enforce:'pre',transform(source,id){
        if(!id.replaceAll('\\','/').endsWith('/src/renderer/main.tsx')) return;
        const mount=source.lastIndexOf('createRoot(document.getElementById');
        if(mount<0) throw new Error('QA mount marker missing');
        return source.slice(0,mount)+'\nexport { SettingsPanel };';
      }}],build:{outDir:output,emptyOutDir:false},logLevel:'warn'});
    window=new BrowserWindow({width:1280,height:900,show:false,webPreferences:{sandbox:true,contextIsolation:true,nodeIntegration:false,offscreen:true,backgroundThrottling:false}});
    const errors=[];
    window.webContents.on('console-message',(_event,...args)=>{if(args[0]===3) errors.push(args[1]);});
    await window.loadFile(path.join(output,'index.html'));
    const result=await window.webContents.executeJavaScript(`(async()=>{
      const wait=async(check,label='unknown')=>{for(let i=0;i<100;i++){if(check())return;await new Promise(r=>setTimeout(r,30));}throw new Error('UI timeout: '+label);};
      document.querySelector('#settings').click();
      await wait(()=>document.querySelector('[data-pack="synapse"]'),'initial settings');
      if(document.documentElement.dataset.themeReduced==='true')document.querySelector('#reduce').click();
      await wait(()=>document.documentElement.dataset.themeReduced==='false','motion baseline');
      const values=[];
      for(const id of ['synapse','cyberpunk']){
        document.querySelector('[data-pack="'+id+'"]').click();
        await wait(()=>document.documentElement.dataset.theme===id,'theme '+id);
        const css=getComputedStyle(document.querySelector('.center-surface'),'::after');
        values.push({id,pattern:document.documentElement.dataset.themeBackground,background:css.backgroundImage});
      }
      if(new Set(values.map(v=>v.pattern)).size!==2)throw new Error('Background variants missing');
      document.querySelector('[data-pack="cyberpunk"]').click();
      await wait(()=>document.querySelector('.cyberpunk-atmosphere-canvas')?.dataset!==undefined,'cyberpunk atmosphere');
      const atmosphere=document.querySelector('.cyberpunk-atmosphere-canvas');
      const firstFrame=atmosphere.toDataURL();
      await new Promise(r=>setTimeout(r,180));
      const secondFrame=atmosphere.toDataURL();
      if(firstFrame===secondFrame)throw new Error('Cyberpunk atmosphere did not animate');
      if(document.querySelector('.cyberpunk-atmosphere')?.dataset.motion!=='running')throw new Error('Cyberpunk atmosphere motion state missing');
      document.querySelector('[data-pack="synapse"]').click();
      await wait(()=>document.documentElement.dataset.theme==='synapse','core selected');
      await wait(()=>document.querySelector('.synapse-core-atmosphere-canvas'),'core atmosphere');
      const coreAtmosphere=document.querySelector('.synapse-core-atmosphere-canvas');
      const coreFirstFrame=coreAtmosphere.toDataURL();
      await new Promise(r=>setTimeout(r,180));
      const coreSecondFrame=coreAtmosphere.toDataURL();
      if(coreFirstFrame===coreSecondFrame)throw new Error('Synapse Core atmosphere did not animate');
      if(document.querySelector('.synapse-core-atmosphere')?.dataset.motion!=='running')throw new Error('Synapse Core atmosphere motion state missing');
      document.querySelector('#focus').click();
      await wait(()=>document.querySelector('.synapse-core-atmosphere')?.dataset.motion==='paused','focus pause');
      document.querySelector('#focus').click();
      document.querySelector('#reduce').click();
      await wait(()=>document.documentElement.dataset.themeReduced==='true','reduced motion');
      await wait(()=>document.querySelector('.synapse-core-atmosphere')?.dataset.motion==='paused','reduced motion atmosphere pause');
      document.querySelector('#reduce').click();
      await wait(()=>document.querySelectorAll('.theme-sample').length===2,'theme card count');
      document.querySelectorAll('.theme-sample')[1].click();
      await wait(()=>document.documentElement.dataset.theme==='cyberpunk','cyberpunk save preview');
      const save=[...document.querySelectorAll('.settings-footer button')].find(b=>/save|salvar/i.test(b.textContent));
      if(!save||save.disabled)throw new Error('Theme save unavailable without backend');
      save.click();
      await wait(()=>JSON.parse(localStorage.getItem('synapse.frontend-v2.settings')).theme==='cyberpunk','saved preference');
      return {packs:values,coreAtmosphere:true,animation:true,cyberpunkAtmosphere:true,pause:true,reducedMotion:true,saved:true};
    })()`);
    window.reload();
    await window.webContents.executeJavaScript(`new Promise((resolve,reject)=>{let n=0;const timer=setInterval(()=>{if(document.documentElement.dataset.theme==='cyberpunk'){clearInterval(timer);resolve(true);}else if(++n>100){clearInterval(timer);reject(new Error('Theme was not restored'));}},30);})`);
    const reports=path.resolve(__dirname,'../../../artifacts/reports/theme-engine');
    await fs.mkdir(reports,{recursive:true});
    for(const id of ['synapse','cyberpunk']){
      await window.webContents.executeJavaScript(`document.querySelector('[data-pack="${id}"]').click()`);
      await new Promise(r=>setTimeout(r,250));
      await fs.writeFile(path.join(reports,id+'.png'),(await window.webContents.capturePage()).toPNG());
    }
    await window.webContents.executeJavaScript(`document.querySelector('[data-pack="synapse"]').click()`);
    await new Promise(r=>setTimeout(r,250));
    await fs.writeFile(path.join(reports,'synapse-core-presence.png'),(await window.webContents.capturePage()).toPNG());
    await window.webContents.executeJavaScript(`document.querySelector('[data-pack="cyberpunk"]').click()`);
    await new Promise(r=>setTimeout(r,250));
    await fs.writeFile(path.join(reports,'cyberpunk-presence.png'),(await window.webContents.capturePage()).toPNG());
    await window.webContents.executeJavaScript(`document.querySelector('[data-pack="synapse"]').click()`);
    await new Promise(r=>setTimeout(r,150));
    await window.webContents.executeJavaScript(`document.querySelector('#workspace').click()`);
    await new Promise(r=>setTimeout(r,200));
    const workspace=await window.webContents.executeJavaScript(`({count:document.querySelectorAll('.workspace-terminal-window').length,radius:getComputedStyle(document.querySelector('.workspace-terminal-window')).borderRadius,theme:document.documentElement.dataset.theme,background:getComputedStyle(document.querySelector('.workspace-panel')).backgroundImage})`);
    if(workspace.count!==2||workspace.radius!=='5px 14px'||workspace.theme!=='synapse'||!workspace.background.includes('linear-gradient'))throw new Error('Synapse Core Workspace theme not applied: '+JSON.stringify(workspace));
    await fs.writeFile(path.join(reports,'synapse-core-workspace.png'),(await window.webContents.capturePage()).toPNG());
    if(errors.length)throw new Error(errors.join('\n'));
    console.log(JSON.stringify({...result,restart:true,workspace,reports}));
    app.exit(0);
  }catch(error){console.error(error);app.exit(1);}
});
