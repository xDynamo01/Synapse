import { useEffect, useRef, useState } from "react";
import type { ActivitySceneState } from "../shared/activityAdapter.js";
import type { FrontendThemePreference } from "../shared/settingsPreferences.js";
import { ConstellationCanvas } from "./constellationCanvas";

interface ActivityConstellationProps {
  scene: ActivitySceneState;
  theme?: FrontendThemePreference;
  onSelectNode(nodeId: string | null): void;
}

export function ActivityConstellation({ scene, theme = "synapse", onSelectNode }: ActivityConstellationProps): React.ReactElement {
  const host = useRef<HTMLDivElement>(null);
  const engine = useRef<ConstellationCanvas | null>(null);
  const select = useRef(onSelectNode);
  const latest = useRef({ scene, theme });
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { select.current = onSelectNode; }, [onSelectNode]);
  useEffect(() => {
    latest.current = { scene, theme };
    engine.current?.update(scene, theme);
  }, [scene, theme]);
  useEffect(() => {
    if (!host.current) return;
    let mounted = true;
    const canvas = new ConstellationCanvas(host.current, (id) => select.current(id));
    engine.current = canvas;
    void canvas.init().then(() => {
      if (mounted) canvas.update(latest.current.scene, latest.current.theme);
    }).catch((reason: unknown) => {
      if (mounted) setError(`Não foi possível iniciar a constelação: ${reason instanceof Error ? reason.message : String(reason)}`);
    });
    return () => { mounted = false; engine.current = null; canvas.destroy(); };
  }, []);
  const selectedNode = scene.nodes.find((node) => node.id === scene.selectedNodeId);
  return (
    <section className={`activity-view constellation ${scene.status}`} aria-label={scene.label}>
      <div ref={host} className="constellation-canvas" tabIndex={0} role="group"
        aria-label="Atividade dos agentes. Selecione um nódulo para ver o registro; Escape limpa a seleção." />
      <header className="constellation-heading"><small>{activityStatus(scene)}</small></header>
      <nav className="constellation-controls" aria-label="Nódulos de atividade">
        <details className="constellation-accessible-nodes"><summary>Nódulos ({scene.nodes.length})</summary>
          {scene.nodes.map((node) => <button key={node.id} type="button"
            aria-pressed={node.id === scene.selectedNodeId} onClick={() => onSelectNode(node.id)}>{node.metadata.title}</button>)}
        </details>
      </nav>
      {error ? <p className="activity-degraded" role="alert">{error}</p> : null}
      {selectedNode ? (
        <aside className={`activity-node-details ${selectedNode.category === "provider" ? "model-log" : ""}`}>
          <strong>{selectedNode.metadata.title}</strong>
          {selectedNode.category !== "provider" && selectedNode.metadata.subtitle ? <small>{selectedNode.metadata.subtitle}</small> : null}
          {selectedNode.category !== "provider" && selectedNode.metadata.currentOperation ? <p>{selectedNode.metadata.currentOperation}</p> : null}
          {selectedNode.category !== "provider" && selectedNode.metadata.modelSummary ? <span>{selectedNode.metadata.modelSummary}</span> : null}
          {selectedNode.category !== "provider" && selectedNode.metadata.resourceSummary ? <span>{selectedNode.metadata.resourceSummary}</span> : null}
          {selectedNode.metadata.workLog.length > 0 ? <ol className="activity-work-log" aria-label="Registro de atividade">
            {selectedNode.metadata.workLog.map((entry, index) => <li key={`${index}:${entry}`}>{entry}</li>)}
          </ol> : <p>Nenhum registro disponível.</p>}
          <button type="button" onClick={() => onSelectNode(null)}>Fechar registro</button>
        </aside>
      ) : null}
      {scene.degradationReasons.length > 0 ? <p className="activity-degraded">{scene.degradationReasons[0]}</p> : null}
    </section>
  );
}

function activityStatus(scene: ActivitySceneState): string {
  if (scene.status === "disconnected") return "Atividade desconectada";
  if (scene.status === "degraded") return "Dados de atividade incompletos";
  if (scene.status === "resyncing") return "Sincronizando atividade";
  if (scene.nodes.length === 0) return "Nenhuma atividade disponível";
  return scene.nodes.some((node) => node.motion === "active") ? "Execução em andamento" : "Aguardando atividade";
}
