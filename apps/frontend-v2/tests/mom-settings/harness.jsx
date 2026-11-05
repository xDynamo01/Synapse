import React from 'react';
import { createRoot } from 'react-dom/client';
// The QA-only Vite transform exports the real panel without mounting the app.
import { SettingsPanel } from '../../src/renderer/main';
import { MoMToggle } from '../../src/renderer/MoMToggle';
import { SynapseFrontendClient } from '../../src/shared/frontendClient';
let stored = { workspace_id: 'default', primary_agent_id: 'artemis', enabled: false, revision: 0, routes: [] };
window.resourceRegime = 'SWARM';
window.requests = [];
window.failSave = false;
window.fetch = async (url, init) => {
  window.requests.push({ url: String(url), method: init?.method || 'GET' });
  if (String(url).includes('/primary/mom/resources')) return new Response(JSON.stringify({
    selected_policy: stored.resource_policy ?? 'RESPONSIVE', resource_policy: stored.resource_policy ?? 'RESPONSIVE',
    execution_regime: window.resourceRegime, transition_status: 'STABLE', policy_effects_deferred: true,
    models: [{model: 'DeepSeek', state: 'READY', owners: ['swarm-qa']}, {model: 'Qwen', state: 'BUSY', owners: ['swarm-qa']}],
    reservations: [{owner:'swarm-qa',models:['DeepSeek','Qwen'],ram_bytes:2048,vram_bytes:1024}],
    missions: [{mission_id:'mission-qa',status:'running'}]
  }), {status:200});
  if (init?.method === 'PUT') {
    if (window.failSave) return new Response('{}', {status: 500});
    const payload = JSON.parse(init.body);
    if (payload.expected_revision !== stored.revision) return new Response('{}', {status: 500});
    stored = { ...stored, ...payload, revision: stored.revision + 1 };
  }
  return new Response(JSON.stringify(stored), {status: 200});
};
window.stored = () => stored;
const snapshot = { models: { defaults: {}, provider_settings: [{provider_id: 'synapse_local', enabled: true}],
  providers: [{provider_id: 'synapse_local', display_name: 'Synapse Local Models', status: 'available'}],
  catalog: ['DeepSeek-R1-0528-Qwen3-8B-Q4_K_M', 'Qwen-Coder'].map(name => ({name, provider: 'synapse_local', chat_usable: true, status: 'available'})) },
  voice: {settings: {}, providers: [], voices: [], packs: []} };
const root = createRoot(document.getElementById('root'));
const client = new SynapseFrontendClient('http://localhost:1234');
window.showToggle = () => root.render(<form className="composer"><MoMToggle client={client} workspaceId="default" onBusy={busy=>{window.momBusy=busy;}} /></form>);
let key = 0;
window.remount = () => root.render(<SettingsPanel key={++key} client={client} status="ready" snapshot={snapshot}
  frontendSettings={{theme:'synapse', reducedMotion:'system'}} error={null} activeSection="models"
  primaryAgent={{agent_id:'artemis',name:'Artemis'}} insightStatus="idle" insightReport={null} insightError={null}
  onClose={()=>{}} onSelectSection={()=>{}} onRefresh={()=>{}} onRefreshInsight={()=>{}}
  onSave={()=>{throw new Error('MoM must not save default settings');}} onPreviewFrontendSettings={()=>{}} />);
window.remount();
