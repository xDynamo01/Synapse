// Synthetic scenes are confined to this test-only build, never imported by production.
import { ConstellationCanvas } from '../../src/renderer/constellationCanvas';
import { createBaselineActivityState, deriveActivityScene } from '../../src/shared/activityAdapter';
const base = deriveActivityScene(createBaselineActivityState('test', { agent_id: 'test:agent', name: 'Primary (test)' }, {
  provider_id: 'synapse_local', provider_status: 'ready', provider_active: true, model_id: 'LLM (test)',
  model_status: 'ready', runtime: 'local', origin: 'settings', availability_state: 'ready', is_default: true
}), { selectedNodeId: null, reducedMotion: false, focused: true });
const engine = new ConstellationCanvas(document.getElementById('surface'), (id) => { window.selection = id; });
window.engine = engine;
window.ready = engine.init().then(() => engine.update(base, 'synapse'));
window.sceneFor = (count) => {
  const nodes = [...base.nodes];
  const edges = [...base.edges];
  for (let i = 2; i < count; i++) {
    nodes.push({ ...base.nodes[0], id: 'test:' + i, label: 'Test ' + i,
      category: i % 3 === 0 ? 'agent' : i % 3 === 1 ? 'tool' : 'resource', motion: 'active', status: 'processing',
      metadata: { ...base.nodes[0].metadata, title: 'Test participant ' + i } });
    edges.push({ id: 'edge:' + i, sourceId: nodes[Math.floor((i - 1) / 2)].id, targetId: 'test:' + i,
      kind: 'communication', active: true, motion: 'active' });
  }
  return { ...base, nodes, edges };
};
window.measure = async (count) => {
  const scene = window.sceneFor(count);
  engine.update(scene, 'synapse'); engine.fit();
  await new Promise((resolve) => setTimeout(resolve, 1200));
  let frames = 0;
  const start = performance.now();
  const countFrame = () => frames++;
  engine.app.ticker.add(countFrame);
  await new Promise((resolve) => setTimeout(resolve, 2200));
  engine.app.ticker.remove(countFrame);
  return { nodes: count, frames, fps: frames * 1000 / (performance.now() - start), graphics: engine.clusters.size };
};
