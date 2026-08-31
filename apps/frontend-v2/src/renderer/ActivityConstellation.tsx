import type { ActivitySceneState } from "../shared/activityAdapter.js";

interface ActivityConstellationProps {
  scene: ActivitySceneState;
  onSelectNode(nodeId: string | null): void;
}

export function ActivityConstellation({ scene, onSelectNode }: ActivityConstellationProps): React.ReactElement {
  return (
    <section className={`activity-view svg ${scene.status}`} aria-label={scene.label}>
      <div className="activity-preview-card" role="status">
        <span className="activity-preview-kicker">Activity</span>
        <strong>Constellation arrives in the next version</strong>
        <span>
          Conversation, history and runtime state remain available now. The graph surface is intentionally parked for v0.02.
        </span>
      </div>
      <button type="button" className="activity-preview-clear-selection" onClick={() => onSelectNode(null)}>
        Graph preview paused
      </button>
      <p className="activity-state">{activityStatus(scene)}</p>
      {scene.degradationReasons.length > 0 ? <p className="activity-degraded">{scene.degradationReasons[0]}</p> : null}
    </section>
  );
}

function activityStatus(scene: ActivitySceneState): string {
  if (scene.status === "disconnected") return "Activity data disconnected";
  if (scene.status === "degraded") return "Activity data degraded";
  if (scene.status === "resyncing") return "Activity data resyncing";
  if (scene.nodes.length === 0) return "No activity data yet";
  return `Activity data available: ${scene.nodes.length} node${scene.nodes.length === 1 ? "" : "s"}`;
}
