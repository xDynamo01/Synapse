// Real renderer components, isolated fixture data. No real backend writes or inference.
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { SettingsPanel, Composer } from '../../src/renderer/main';
import { Presence } from '../../src/renderer/Presence';
import { ActivityConstellation } from '../../src/renderer/ActivityConstellation';
import { derivePresenceState } from '../../src/shared/presenceAdapter';
import { createBaselineActivityState, deriveActivityScene } from '../../src/shared/activityAdapter';
import { SynapseFrontendClient } from '../../src/shared/frontendClient';

let stored = { workspace_id:'default', primary_agent_id:'artemis', enabled:false, revision:0,
  routes:[{operation:'coding', provider:'synapse_local', model:'Qwen-Coder'}] };
window.fetch = async (url, init) => {
  if (!String(url).includes('/primary/mom/configuration')) throw new Error('Unexpected QA request');
  if (init?.method === 'PUT') {
    const update = JSON.parse(init.body);
    if (update.expected_revision !== stored.revision) return new Response('{}', {status:409});
    stored = {...stored, ...update, revision:stored.revision+1};
  }
  return new Response(JSON.stringify(stored));
};
const client = new SynapseFrontendClient('http://127.0.0.1:5186');
const primary = {agent_id:'artemis',name:'Artemis'};
const model = {provider_id:'synapse_local',model_id:'DeepSeek',runtime:'synapse_local',availability_state:'available'};
const scene = derivePresenceState({backendState:'ready', conversationStatus:'idle', manualVoiceState:'idle',
  conversationModeState:'inactive', audioAmplitude:0, reducedMotion:true, focused:true});
const snapshot = {personalization:{agent_id:'artemis',display_name:'Artemis',system_prompt:'Responda com clareza e objetividade. Use as ferramentas disponíveis quando necessário.'},
  models:{defaults:{default_provider:'synapse_local',default_chat_model:'DeepSeek'},
    provider_settings:[{provider_id:'synapse_local',enabled:true}],
    providers:[{provider_id:'synapse_local',display_name:'Synapse Local Models',status:'available'}],
    catalog:['DeepSeek','Qwen-Coder'].map(name=>({name,provider:'synapse_local',chat_usable:true,status:'available'}))},
  voice:{settings:{enabled:true,language:'pt-BR'},providers:[],voices:[],packs:[]}};
const noop = () => {};
const unused = async () => { throw new Error('Audio and attachments disabled in visual QA'); };
function Preview() {
  const [settings,setSettings] = useState(false);
  const [section,setSection] = useState('personalization');
  const [activity,setActivity] = useState(false);
  const [selected,setSelected] = useState(null);
  const [working,setWorking] = useState(false);
  const [reduced,setReduced] = useState(false);
  const activityScene = deriveActivityScene(createBaselineActivityState(null,primary,model),
    {selectedNodeId:selected,reducedMotion:reduced,focused:true});
  activityScene.nodes = activityScene.nodes.map(node => ({...node, motion:working?'active':'quiet'}));
  return <div className="app-shell log-minimized">
    <header className="title-bar"><span>S</span><span>Prévia isolada · sem acesso aos seus dados</span></header>
    <nav className="side-rail">
      <button aria-label="Tela principal" onClick={()=>setActivity(false)}>S</button>
      <button aria-label="Constelação" onClick={()=>setActivity(true)}>C</button>
      <button aria-label="Configurações" onClick={()=>setSettings(true)}>A</button>
      <button aria-label="Simular trabalho" aria-pressed={working} onClick={()=>setWorking(!working)}>T</button>
      <button aria-label="Reduzir movimento" aria-pressed={reduced} onClick={()=>setReduced(!reduced)}>R</button>
    </nav>
    <section className="center-surface"><main className="main-area">
      <div className={`visual-stage ${activity?'activity':'presence'}`}>
        {activity ? <ActivityConstellation scene={activityScene} onSelectNode={setSelected}/> : <Presence scene={scene}/>}
      </div>
    </main></section>
    <Composer client={client} commands={[]} commandError={null} disabled={false} canCancel={false} failedDraft=""
      onSend={async()=>{}} onCancel={async()=>{}} onDiscoverCommands={async()=>{}} onExecuteCommand={unused}
      onStageAttachment={unused} onTranscribeVoice={unused} onConversationVoiceTurn={unused} onPresenceChange={noop}/>
    {settings ? <SettingsPanel client={client} status="ready" snapshot={snapshot}
      frontendSettings={{theme:'synapse',reducedMotion:'system'}} error={null} activeSection={section}
      primaryAgent={primary} insightStatus="idle" insightReport={null} insightError={null}
      onClose={()=>setSettings(false)} onSelectSection={setSection} onRefresh={noop} onRefreshInsight={noop}
      onSave={async()=>{}} onPreviewFrontendSettings={noop}/> : null}
  </div>;
}
createRoot(document.getElementById('root')).render(<Preview/>);
