import type {
  OperationalEntity,
  OperationalFact,
  OperationalRelation,
  OperationalStatus,
  ProjectActivitySnapshot
} from "./types.js";

export type ActivityViewStatus = "ready" | "empty" | "degraded" | "resyncing" | "disconnected" | "unknown";
export type ActivityNodeCategory =
  | "primary"
  | "agent"
  | "worker"
  | "task"
  | "tool"
  | "resource"
  | "evaluation"
  | "provider"
  | "aggregate"
  | "neutral";
export type ActivitySemanticColor = "teal" | "blue" | "purple" | "orange" | "yellow" | "neutral";
export type ActivityMotion = "active" | "quiet" | "stable" | "attention" | "error" | "unknown";

export interface ActivitySceneState {
  projectId: string | null;
  revision: number;
  cursor: string | null;
  status: ActivityViewStatus;
  label: string;
  nodes: ActivitySceneNode[];
  edges: ActivitySceneEdge[];
  flows: ActivitySceneFlow[];
  selectedNodeId: string | null;
  degradationReasons: string[];
  reducedMotion: boolean;
  focused: boolean;
  budget: ActivityPerformanceBudget;
}

export interface ActivitySceneNode {
  id: string;
  label: string;
  category: ActivityNodeCategory;
  color: ActivitySemanticColor;
  status: OperationalStatus | "aggregate";
  motion: ActivityMotion;
  halo: "none" | "attention" | "error" | "degraded";
  x: number;
  y: number;
  radius: number;
  metadata: ActivityNodeMetadata;
  aggregateCount?: number;
}

export interface ActivitySceneEdge {
  id: string;
  sourceId: string;
  targetId: string;
  kind: string;
  active: boolean;
  motion: ActivityMotion;
}

export interface ActivitySceneFlow {
  id: string;
  edgeId: string;
  occurredAtRevision: number;
}

export interface ActivityNodeMetadata {
  title: string;
  subtitle: string | null;
  currentTask: string | null;
  currentOperation: string | null;
  resourceSummary: string | null;
}

export interface ActivityPerformanceBudget {
  maxNodes: number;
  maxEdges: number;
  maxFlows: number;
  focusedFps: number;
  unfocusedFps: number;
}

export interface ActivityGraphState {
  projectId: string | null;
  revision: number;
  cursor: string | null;
  entities: Map<string, OperationalEntity>;
  relations: Map<string, OperationalRelation>;
  degraded: boolean;
  degradationReasons: string[];
  lastEventIds: Set<string>;
  flows: ActivitySceneFlow[];
  resyncing: boolean;
  disconnected: boolean;
}

export const activityPerformanceBudget = {
  normal: { maxNodes: 54, maxEdges: 76, maxFlows: 18, focusedFps: 36, unfocusedFps: 10 },
  reduced: { maxNodes: 28, maxEdges: 40, maxFlows: 0, focusedFps: 18, unfocusedFps: 6 }
} as const;

export function createEmptyActivityState(projectId: string | null): ActivityGraphState {
  return {
    projectId,
    revision: 0,
    cursor: null,
    entities: new Map(),
    relations: new Map(),
    degraded: false,
    // A healthy conversation without a selected project is an idle/empty
    // activity scope, not an unavailable projection. Project-scoped streams
    // are connected separately when a project exists.
    degradationReasons: [],
    lastEventIds: new Set(),
    flows: [],
    resyncing: false,
    disconnected: false
  };
}

/** Baseline keeps the factual primary agent visible before any turn events. */
export function createBaselineActivityState(
  projectId: string | null,
  agent: { agent_id: string; name: string } | null
): ActivityGraphState {
  const state = createEmptyActivityState(projectId);
  if (!agent) return state;
  state.entities.set(agent.agent_id, {
    entityId: agent.agent_id,
    kind: "agent",
    role: "primary",
    status: "idle",
    label: agent.name,
    currentTask: null,
    currentOperation: "Ready",
    startedAt: null,
    parentEntityId: null,
    missionId: null,
    resources: { files: 0, memories: 0, toolResults: 0 },
    metadata: {}
  });
  return state;
}

export function applyActivitySnapshot(
  current: ActivityGraphState,
  snapshot: ProjectActivitySnapshot,
  cursor: string | null,
  resyncing = false
): ActivityGraphState {
  const entities = new Map(snapshot.entities
    .filter((entity) => typeof entity.entityId === "string" && entity.entityId.length > 0)
    .map((entity) => [entity.entityId, entity]));
  const relations = new Map(snapshot.relations
    .filter((relation) => typeof relation.relationId === "string" && relation.relationId.length > 0)
    .map((relation) => [relation.relationId, relation]));
  return {
    ...current,
    projectId: snapshot.projectId,
    revision: snapshot.revision,
    cursor,
    entities,
    relations,
    degraded: snapshot.degraded,
    degradationReasons: snapshot.degradationReasons,
    lastEventIds: new Set(snapshot.lastEventId ? [snapshot.lastEventId] : []),
    resyncing,
    disconnected: false
  };
}

export function applyActivityEvent(
  current: ActivityGraphState,
  event: OperationalFact,
  cursor: string | null
): ActivityGraphState {
  if (current.projectId !== null && event.projectId !== current.projectId) {
    return current;
  }
  if (event.revision <= current.revision || current.lastEventIds.has(event.eventId)) {
    return current;
  }
  if (event.revision > current.revision + 1) {
    return {
      ...current,
      degraded: true,
      degradationReasons: mergeReason(current.degradationReasons, "activity resync required"),
      resyncing: true
    };
  }

  const entities = new Map(current.entities);
  const relations = new Map(current.relations);
  let degraded = current.degraded;
  let degradationReasons = current.degradationReasons;
  const flows = current.flows.slice(-activityPerformanceBudget.normal.maxFlows + 1);

  if (event.kind === "upsert-entity" && event.entity && typeof event.entity.entityId === "string" && event.entity.entityId.length > 0) {
    entities.set(event.entity.entityId, event.entity);
  } else if (event.kind === "remove-entity" && event.entityId) {
    entities.delete(event.entityId);
  } else if (event.kind === "upsert-relation" && event.relation) {
    relations.set(event.relation.relationId, event.relation);
    flows.push({ id: `${event.eventId}:flow`, edgeId: event.relation.relationId, occurredAtRevision: event.revision });
  } else if (event.kind === "remove-relation" && event.relationId) {
    relations.delete(event.relationId);
  } else if (event.kind === "mark-degraded") {
    degraded = true;
    degradationReasons = mergeReason(degradationReasons, event.degradationReason ?? "activity degraded");
  } else if (event.kind === "clear-degraded") {
    degraded = false;
    degradationReasons = [];
  }

  return {
    ...current,
    projectId: event.projectId,
    revision: event.revision,
    cursor,
    entities,
    relations,
    degraded,
    degradationReasons,
    lastEventIds: new Set([...current.lastEventIds, event.eventId].slice(-32)),
    flows,
    resyncing: false,
    disconnected: false
  };
}

export function markActivityDisconnected(current: ActivityGraphState): ActivityGraphState {
  return {
    ...current,
    disconnected: true,
    degraded: true,
    degradationReasons: mergeReason(current.degradationReasons, "activity stream disconnected")
  };
}

export function deriveActivityScene(
  state: ActivityGraphState,
  options: { selectedNodeId: string | null; reducedMotion: boolean; focused: boolean }
): ActivitySceneState {
  const budget = options.reducedMotion ? activityPerformanceBudget.reduced : activityPerformanceBudget.normal;
  const visibleEntities = Array.from(state.entities.values()).slice(0, budget.maxNodes);
  const overflow = Math.max(0, state.entities.size - visibleEntities.length);
  const nodes = visibleEntities.map((entity, index) => nodeFromEntity(entity, index, state.entities.size));
  if (overflow > 0) {
    nodes.push(aggregateNode(overflow, visibleEntities.length));
  }
  const nodeIds = new Set(nodes.map((node) => node.id));
  const parentEdges = visibleEntities
    .filter((entity) => entity.parentEntityId && nodeIds.has(entity.parentEntityId) && nodeIds.has(entity.entityId))
    .map((entity): ActivitySceneEdge => ({
      id: `parent:${entity.parentEntityId}:${entity.entityId}`,
      sourceId: entity.parentEntityId ?? "",
      targetId: entity.entityId,
      kind: "communication",
      active: entity.status === "running" || entity.status === "processing" || entity.status === "listening" || entity.status === "speaking",
      motion: motionFor(entity.status)
    }));
  const edges = [
    ...Array.from(state.relations.values())
    .filter((relation) => nodeIds.has(relation.sourceEntityId) && nodeIds.has(relation.targetEntityId))
    .slice(0, budget.maxEdges)
      .map(edgeFromRelation),
    ...parentEdges
  ].slice(0, budget.maxEdges);
  const edgeIds = new Set(edges.map((edge) => edge.id));
  const flows = options.reducedMotion ? [] : state.flows.filter((flow) => edgeIds.has(flow.edgeId)).slice(-budget.maxFlows);
  const status = sceneStatus(state);
  return {
    projectId: state.projectId,
    revision: state.revision,
    cursor: state.cursor,
    status,
    label: activityLabel(status, nodes.length, state.revision),
    nodes,
    edges,
    flows,
    selectedNodeId: options.selectedNodeId && nodeIds.has(options.selectedNodeId) ? options.selectedNodeId : null,
    degradationReasons: state.degradationReasons,
    reducedMotion: options.reducedMotion,
    focused: options.focused,
    budget
  };
}

function nodeFromEntity(entity: OperationalEntity, index: number, total: number): ActivitySceneNode {
  const category = categoryFor(entity);
  return {
    id: entity.entityId,
    label: entity.label,
    category,
    color: semanticColor(entity, category),
    status: entity.status,
    motion: motionFor(entity.status),
    halo: haloFor(entity.status),
    ...stablePosition(entity.entityId, index, total),
    radius: radiusFor(entity),
    metadata: metadataFor(entity)
  };
}

function edgeFromRelation(relation: OperationalRelation): ActivitySceneEdge {
  return {
    id: relation.relationId,
    sourceId: relation.sourceEntityId,
    targetId: relation.targetEntityId,
    kind: relation.kind,
    active: relation.active,
    motion: relation.kind === "communication" || relation.kind === "tool-use" ? "active" : "quiet"
  };
}

function aggregateNode(count: number, index: number): ActivitySceneNode {
  return {
    id: "aggregate:overflow",
    label: `+${count}`,
    category: "aggregate",
    color: "neutral",
    status: "aggregate",
    motion: "quiet",
    halo: "degraded",
    ...stablePosition("aggregate:overflow", index, count + index),
    radius: 28,
    aggregateCount: count,
    metadata: {
      title: `+${count} aggregated entities`,
      subtitle: "Large activity set",
      currentTask: null,
      currentOperation: "Reduced detail to preserve visual stability",
      resourceSummary: null
    }
  };
}

function categoryFor(entity: OperationalEntity): ActivityNodeCategory {
  if (entity.kind === "agent" && entity.role === "primary") return "primary";
  if (entity.kind === "agent") return "agent";
  if (entity.kind === "worker") return "worker";
  if (entity.kind === "task" || entity.kind === "mission" || entity.kind === "swarm") return "task";
  if (entity.kind === "tool-execution") return "tool";
  if (entity.kind === "memory-source" || entity.kind === "context-source") return "resource";
  if (entity.kind === "evaluation" || entity.kind === "approval") return "evaluation";
  if (entity.kind === "runtime" || entity.kind === "voice-session" || entity.kind === "communication") return "provider";
  return "neutral";
}

function semanticColor(entity: OperationalEntity, category: ActivityNodeCategory): ActivitySemanticColor {
  const role = entity.role.toLowerCase();
  if (category === "primary") return "teal";
  if (category === "resource" || category === "provider") return "neutral";
  if (category === "tool" || role === "coding" || role === "execution") return "orange";
  if (category === "evaluation" || role === "review" || role === "evaluation") return "yellow";
  if (role === "research") return "blue";
  if (role === "planning" || role === "reasoning") return "purple";
  if (category === "agent") return "teal";
  return "neutral";
}

function motionFor(status: OperationalStatus): ActivityMotion {
  if (status === "running" || status === "processing" || status === "listening" || status === "speaking") return "active";
  if (status === "waiting" || status === "idle") return "quiet";
  if (status === "completed") return "stable";
  if (status === "failed" || status === "unavailable") return "error";
  if (status === "approval-needed") return "attention";
  return "unknown";
}

function haloFor(status: OperationalStatus): ActivitySceneNode["halo"] {
  if (status === "failed" || status === "unavailable") return "error";
  if (status === "approval-needed") return "attention";
  if (status === "unknown") return "degraded";
  return "none";
}

function radiusFor(entity: OperationalEntity): number {
  const resourceWeight = entity.resources.files + entity.resources.memories + entity.resources.toolResults;
  const base = entity.kind === "agent" ? 22 : entity.kind === "worker" ? 16 : 13;
  return Math.min(32, base + Math.log2(resourceWeight + 1) * 2);
}

function stablePosition(id: string, index: number, total: number): { x: number; y: number } {
  const a = hash(id);
  const cluster = (a % 7) / 7;
  const spread = 0.22 + ((a >> 8) % 37) / 100;
  const angle = cluster * Math.PI * 2 + index * 0.37;
  const asymmetry = 0.76 + (((a >> 15) % 31) / 100);
  const crowding = Math.min(0.18, total / 420);
  return {
    // Keep every factual node inside the SVG viewport; the previous spread
    // could place labels/hit targets outside the workspace at normal sizes.
    x: clamp(0.5 + Math.cos(angle) * (spread + crowding) * asymmetry, 0.08, 0.92),
    y: clamp(0.5 + Math.sin(angle) * (spread * 0.72 + crowding) * (1.18 - asymmetry / 3), 0.10, 0.86)
  };
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value));
}

function metadataFor(entity: OperationalEntity): ActivityNodeMetadata {
  const resources = [];
  if (entity.resources.files > 0) resources.push(`${entity.resources.files} files`);
  if (entity.resources.memories > 0) resources.push(`${entity.resources.memories} memories`);
  if (entity.resources.toolResults > 0) resources.push(`${entity.resources.toolResults} tool results`);
  return {
    title: entity.label,
    subtitle: `${entity.kind} · ${entity.status}`,
    currentTask: entity.currentTask ?? null,
    currentOperation: entity.currentOperation ?? null,
    resourceSummary: resources.length > 0 ? resources.join(" · ") : null
  };
}

function sceneStatus(state: ActivityGraphState): ActivityViewStatus {
  if (state.disconnected) return "disconnected";
  if (state.resyncing) return "resyncing";
  if (state.degraded) return "degraded";
  if (state.entities.size === 0) return "empty";
  return "ready";
}

function activityLabel(status: ActivityViewStatus, nodeCount: number, revision: number): string {
  if (status === "empty") return "Synapse activity empty";
  if (status === "degraded") return "Synapse activity degraded";
  if (status === "resyncing") return "Synapse activity resyncing";
  if (status === "disconnected") return "Synapse activity disconnected";
  if (status === "unknown") return "Synapse activity unavailable";
  return `Synapse activity revision ${revision} with ${nodeCount} nodes`;
}

function mergeReason(reasons: string[], reason: string): string[] {
  return reasons.includes(reason) ? reasons : [...reasons, reason];
}

function hash(value: string): number {
  let result = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 16777619);
  }
  return result >>> 0;
}
