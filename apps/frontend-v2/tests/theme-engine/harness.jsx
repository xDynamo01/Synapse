// Real presentation components; isolated fixture data, no backend or model calls.
import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { SettingsPanel } from '../../src/renderer/main';
import { Presence } from '../../src/renderer/Presence';
import { SynapseCoreAtmosphere } from '../../src/renderer/SynapseCoreAtmosphere';
import { CyberpunkAtmosphere } from '../../src/renderer/CyberpunkAtmosphere';
import { WorkspacePanel } from '../../src/renderer/WorkspacePanel';
import { applyTheme, themePacks } from '../../src/shared/themeEngine';
import { assetsForTheme } from '../../src/shared/themeAssets';
import { derivePresenceState } from '../../src/shared/presenceAdapter';
import { loadFrontendSettingsPreferences, saveFrontendSettingsPreferences } from '../../src/shared/settingsPreferences';
const noop = () => {};
function Harness() {
  const [prefs, setPrefs] = useState(loadFrontendSettingsPreferences);
  const [settings, setSettings] = useState(false);
  const [workspace, setWorkspace] = useState(false);
  const [focused, setFocused] = useState(true);
  const reduced = prefs.reducedMotion === 'reduce';
  useEffect(() => { applyTheme(document.documentElement, prefs.theme, reduced, focused); }, [prefs, reduced, focused]);
  const scene = derivePresenceState({ backendState:'ready', conversationStatus:'idle', manualVoiceState:'idle',
    conversationModeState:'inactive', audioAmplitude:0, reducedMotion:reduced, focused });
  return <div className="app-shell log-minimized">
    <header className="title-bar" style={{display:'flex',gap:12,padding:'0 12px',fontSize:12}}><span style={{whiteSpace:'nowrap'}}>Theme Engine · prévia isolada</span>
      {themePacks.map(p => <button key={p.id} data-pack={p.id} onClick={() => setPrefs({...prefs, theme:p.id})}>{p.label}</button>)}
      <button id="reduce" onClick={() => setPrefs({...prefs,reducedMotion:reduced?'system':'reduce'})}>Reduzir</button>
      <button id="focus" onClick={() => setFocused(!focused)}>Foco</button>
    </header>
    <nav className="side-rail"><button id="workspace" onClick={() => setWorkspace(!workspace)}>CLI</button>
      <button id="settings" onClick={() => setSettings(!settings)}>⚙</button>
      <img alt="Biblioteca" src={assetsForTheme(prefs.theme).navigation.history} width="40" />
    </nav>
    <div className="center-surface">
      <SynapseCoreAtmosphere active={prefs.theme === 'synapse'} reducedMotion={reduced} focused={focused} state={scene.state} amplitude={scene.amplitude}/>
      <CyberpunkAtmosphere active={prefs.theme === 'cyberpunk'} reducedMotion={reduced} focused={focused}/>
      <main className="main-area log-closed">
      <div className="visual-stage presence log-closed"><Presence scene={scene} theme={prefs.theme} reducedMotion={reduced} focused={focused}/></div>
      <div className="composer" style={{display:'block'}}><span>Mensagem para o Synapse…</span></div>
      </main>
    </div>
    {workspace && <WorkspacePanel projects={[]} showProjects={false} swarms={[]} activeProjectId={null} loading={false}
      error={null} onClose={() => setWorkspace(false)} onRefresh={noop} onSelectProject={noop} onOpenFiles={noop}
      onSwarmAction={noop} selectedSwarmId="demo" swarmDetail={{status:'running'}} swarmTrace={{events:[]}}
      onSelectSwarm={noop} swarmAgents={[{agent_id:'orion',name:'Orion',status:'running',model:'Modelo simulado'}]}
      swarmTools={{}} onSubmitWork={noop} onExecuteCommand={async () => ({status:'completed'})}
      commandOutput={[]} agentName="Artemis" primaryAgentId="artemis" modelName="Modelo simulado"
      swarmResult={null} demoActive={true} swarmConfirmation={null} swarmConfirmationBusy={false} onResolveSwarmConfirmation={noop}/>} 
    {settings && <SettingsPanel status="ready" snapshot={null} frontendSettings={prefs} error={null} activeSection="themes"
      primaryAgent={null} insightStatus="idle" insightReport={null} insightError={null} onClose={() => setSettings(false)}
      onSelectSection={noop} onRefresh={noop} onRefreshInsight={noop} onSave={changes => setPrefs(saveFrontendSettingsPreferences(changes))}
      onPreviewFrontendSettings={setPrefs} onLaunchSwarmDemo={noop}/>} 
  </div>;
}
createRoot(document.getElementById('root')).render(<Harness/>);
