// Isolated visual smoke for the real constellation renderer. No backend, model, or filesystem action.
import { ConstellationCanvas } from '../../src/renderer/constellationCanvas';

const now = 42;
const meta = (title, subtitle, currentOperation, workLog = [], resourceSummary = null, modelSummary = null) => ({
  title,
  subtitle,
  currentTask: null,
  currentOperation,
  resourceSummary,
  modelSummary,
  workLog
});

const nodes = [
  {
    id: 'agent:artemis',
    label: 'Artemis',
    category: 'primary',
    color: 'teal',
    status: 'processing',
    motion: 'active',
    halo: 'none',
    x: 0.5,
    y: 0.52,
    radius: 31,
    metadata: meta('Artemis', 'primary agent · processing', 'Coordenando o Swarm e consolidando resposta',
      ['Delegando análise para Lyra', 'Solicitando patch para Orion', 'Aguardando validação de Vega'])
  },
  {
    id: 'runtime:primary:deepseek',
    label: 'DeepSeek R1 Qwen 8B',
    category: 'provider',
    color: 'purple',
    status: 'processing',
    motion: 'active',
    halo: 'none',
    x: 0.64,
    y: 0.42,
    radius: 24,
    metadata: meta('DeepSeek R1 Qwen 8B', 'runtime · processing', null,
      ['llama.cpp slot 0: prompt eval', 'reasoning tokens streaming', 'generation in progress'],
      null, 'prompt 812 tok · output 128 tok · 23.4/s')
  },
  {
    id: 'agent:lyra',
    label: 'Lyra',
    category: 'agent',
    color: 'blue',
    status: 'running',
    motion: 'active',
    halo: 'none',
    x: 0.31,
    y: 0.34,
    radius: 24,
    metadata: meta('Lyra', 'research agent · running', 'Pesquisando contexto do projeto',
      ['Lendo arquivos anexados', 'Separando evidência útil'], '2 files · 1 memory')
  },
  {
    id: 'runtime:lyra:qwen',
    label: 'Qwen 3 4B',
    category: 'provider',
    color: 'neutral',
    status: 'running',
    motion: 'active',
    halo: 'none',
    x: 0.22,
    y: 0.27,
    radius: 18,
    metadata: meta('Qwen 3 4B', 'runtime · running', null,
      ['context window prepared', 'analysis chunk 2/4'], null, 'prompt 434 tok · output 72 tok')
  },
  {
    id: 'tool:project-files',
    label: 'Project Files',
    category: 'tool',
    color: 'orange',
    status: 'processing',
    motion: 'active',
    halo: 'none',
    x: 0.22,
    y: 0.46,
    radius: 16,
    metadata: meta('Project Files', 'tool · processing', 'Listando documentos do projeto',
      ['open_project_files', 'list_documents'])
  },
  {
    id: 'agent:orion',
    label: 'Orion',
    category: 'agent',
    color: 'orange',
    status: 'running',
    motion: 'active',
    halo: 'none',
    x: 0.72,
    y: 0.62,
    radius: 24,
    metadata: meta('Orion', 'coding agent · running', 'Preparando alteração de UI',
      ['Inspecionando renderer', 'Editando componente visual'])
  },
  {
    id: 'runtime:orion:coder',
    label: 'Qwen Coder 3B',
    category: 'provider',
    color: 'neutral',
    status: 'running',
    motion: 'active',
    halo: 'none',
    x: 0.82,
    y: 0.67,
    radius: 18,
    metadata: meta('Qwen Coder 3B', 'runtime · running', null,
      ['generating patch plan', 'tool-call candidate detected'])
  },
  {
    id: 'tool:editor',
    label: 'Editor',
    category: 'tool',
    color: 'orange',
    status: 'processing',
    motion: 'active',
    halo: 'none',
    x: 0.77,
    y: 0.48,
    radius: 16,
    metadata: meta('Editor', 'tool · processing', 'Aplicando alteração controlada',
      ['read_file', 'apply_patch'])
  },
  {
    id: 'agent:vega',
    label: 'Vega',
    category: 'agent',
    color: 'yellow',
    status: 'waiting',
    motion: 'quiet',
    halo: 'attention',
    x: 0.47,
    y: 0.78,
    radius: 22,
    metadata: meta('Vega', 'verification agent · waiting', 'Aguardando build para validar',
      ['Preparado para smoke Electron'])
  },
  {
    id: 'tool:electron-smoke',
    label: 'Electron Smoke',
    category: 'tool',
    color: 'yellow',
    status: 'running',
    motion: 'active',
    halo: 'none',
    x: 0.58,
    y: 0.79,
    radius: 16,
    metadata: meta('Electron Smoke', 'tool · running', 'Capturando print da constelação',
      ['capturePage', 'visual fixture'])
  }
];

const edges = [
  ['edge:artemis:deepseek', 'agent:artemis', 'runtime:primary:deepseek', 'communication'],
  ['edge:artemis:lyra', 'agent:artemis', 'agent:lyra', 'delegation'],
  ['edge:lyra:qwen', 'agent:lyra', 'runtime:lyra:qwen', 'communication'],
  ['edge:lyra:files', 'agent:lyra', 'tool:project-files', 'tool-use'],
  ['edge:artemis:orion', 'agent:artemis', 'agent:orion', 'delegation'],
  ['edge:orion:coder', 'agent:orion', 'runtime:orion:coder', 'communication'],
  ['edge:orion:editor', 'agent:orion', 'tool:editor', 'tool-use'],
  ['edge:artemis:vega', 'agent:artemis', 'agent:vega', 'delegation'],
  ['edge:vega:smoke', 'agent:vega', 'tool:electron-smoke', 'tool-use']
].map(([id, sourceId, targetId, kind]) => ({ id, sourceId, targetId, kind, active: true, motion: 'active' }));

const scene = {
  projectId: 'visual-smoke',
  revision: now,
  cursor: 'visual-smoke',
  status: 'ready',
  label: 'Swarm visual smoke with agents, models, and tools',
  nodes,
  edges,
  flows: edges.map((edge, index) => ({ id: `flow:${index}`, edgeId: edge.id, occurredAtRevision: now })),
  selectedNodeId: null,
  degradationReasons: [],
  reducedMotion: false,
  focused: true,
  budget: { maxNodes: 54, maxEdges: 76, maxFlows: 18, focusedFps: 36, unfocusedFps: 10 }
};

const engine = new ConstellationCanvas(document.getElementById('surface'), (id) => { window.selection = id; });
window.engine = engine;
window.scene = scene;
window.ready = engine.init().then(() => {
  engine.update(scene, 'synapse');
  engine.fit();
});
