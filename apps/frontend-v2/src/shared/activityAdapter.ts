import type {
  OperationalEntity,
  OperationalFact,
  OperationalRelation,
  OperationalStatus,
  ProviderModelOption,
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
  modelSummary: string | null;
  workLog: string[];
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
  agent: { agent_id: string; name: string } | null,
  model?: ProviderModelOption | null
): ActivityGraphState {
  const state = createEmptyActivityState(projectId);
  return withBaselineActivityState(state, agent, model);
}

/** Keep the factual idle runtime visible even when the activity snapshot is empty. */
export function withBaselineActivityState(
  state: ActivityGraphState,
  agent: { agent_id: string; name: string } | null,
  model?: ProviderModelOption | null
): ActivityGraphState {
  if (!agent) return state;
  const entities = new Map(state.entities);
  const relations = new Map(state.relations);
  // The operational projection namespaces agent identities; bootstrap returns registry IDs.
  const agentId = agent.agent_id.startsWith("agent:") ? agent.agent_id : `agent:${agent.agent_id}`;
  if (!entities.has(agentId)) {
    entities.set(agentId, {
      entityId: agentId,
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
  }
  const primary = entities.get(agentId)!;
  entities.set(agentId, { ...primary, role: "primary", label: agent.name });
  const defaultModel = model;
  if (defaultModel) {
    const runtimeId = `runtime:${defaultModel.provider_id}:${defaultModel.model_id}`;
    for (const [id, entity] of entities) {
      if (entity.kind === "runtime" && entity.metadata.selected_runtime === true) {
        entities.set(id, { ...entity, metadata: { ...entity.metadata, selected_runtime: false } });
      }
    }
    if (!entities.has(runtimeId)) {
      entities.set(runtimeId, {
        entityId: runtimeId,
        kind: "runtime",
        role: defaultModel.runtime,
        status: modelRuntimeIsAvailable(defaultModel) ? "idle" : "unavailable",
        label: defaultModel.model_id || defaultModel.provider_id,
        currentTask: null,
        currentOperation: defaultModel.provider_id,
        startedAt: null,
        parentEntityId: agentId,
        missionId: null,
        resources: { files: 0, memories: 0, toolResults: 0 },
        metadata: {
          providerId: defaultModel.provider_id,
          runtime: defaultModel.runtime,
          availability: defaultModel.availability_state
        }
      });
    }
    const runtime = entities.get(runtimeId)!;
    entities.set(runtimeId, { ...runtime, parentEntityId: agentId,
      metadata: { ...runtime.metadata, selected_runtime: true } });
  }
  return {
    ...state,
    entities,
    relations
  };
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
    if (event.relation.active && event.relation.kind !== "parent") {
      flows.push({ id: `${event.eventId}:flow`, edgeId: event.relation.relationId, occurredAtRevision: event.revision });
    }
  } else if (event.kind === "remove-relation" && event.relationId) {
    relations.delete(event.relationId);
  } else if (event.kind === "mark-degraded") {
    degraded = true;
    degradationReasons = mergeReason(degradationReasons, event.degradationReason ?? "activity degraded");
  } else if (event.kind === "clear-degraded") {
    degraded = false;
    degradationReasons = [];
  }

  const source = event.metadata.transfer_source;
  const target = event.metadata.transfer_target;
  if (typeof source === "string" && source && typeof target === "string" && target
    && (event.metadata.transfer_kind === "request" || event.metadata.transfer_kind === "response")) {
    const edgeId = `transfer:${source}:${target}`;
    // This relation is a factual observed transfer, not an indefinitely active connection.
    relations.set(edgeId, { relationId: edgeId, sourceEntityId: source, targetEntityId: target, kind: "communication", active: false });
    flows.push({ id: `${event.eventId}:transfer`, edgeId, occurredAtRevision: event.revision });
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
    flows: flows.slice(-activityPerformanceBudget.normal.maxFlows),
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
  options: { selectedNodeId: string | null; reducedMotion: boolean; focused: boolean; modelTelemetry?: string[] }
): ActivitySceneState {
  const budget = options.reducedMotion ? activityPerformanceBudget.reduced : activityPerformanceBudget.normal;
  const participating = new Set(Array.from(state.relations.values()).filter((relation) => relation.active && relation.kind !== "parent")
    .flatMap((relation) => [relation.sourceEntityId, relation.targetEntityId]));
  const activityModules = activityModulesFromEntities(Array.from(state.entities.values()), options.modelTelemetry ?? [], participating);
  const visibleEntities = activityModules.slice(0, budget.maxNodes);
  const overflow = Math.max(0, activityModules.length - visibleEntities.length);
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
      kind: "parent",
      active: false,
      motion: "quiet"
    }));
  const edges = [
    ...Array.from(state.relations.values())
    .filter((relation) => nodeIds.has(relation.sourceEntityId) && nodeIds.has(relation.targetEntityId))
    .slice(0, budget.maxEdges)
      .map(edgeFromRelation),
    ...parentEdges.filter((parent) => !Array.from(state.relations.values()).some((relation) =>
      (relation.sourceEntityId === parent.sourceId && relation.targetEntityId === parent.targetId)
      || (relation.sourceEntityId === parent.targetId && relation.targetEntityId === parent.sourceId)))
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

function activityModulesFromEntities(entities: OperationalEntity[], modelTelemetry: string[], participating: Set<string>): OperationalEntity[] {
  const primary = primaryAgentModule(entities);
  const runtime = runtimeModule(entities, primary?.entityId ?? null, modelTelemetry);
  const visibleKinds = new Set(["agent", "worker", "runtime", "tool-execution", "memory-source", "context-source"]);
  return entities.filter((entity) => visibleKinds.has(entity.kind)
    && (entity.entityId === primary?.entityId || entity.entityId === runtime?.entityId
      || participating.has(entity.entityId)
      || ["running", "processing", "listening", "speaking", "waiting", "approval-needed"].includes(entity.status))).map((entity) => {
    if (entity.entityId === primary?.entityId) return primary;
    if (entity.entityId === runtime?.entityId) return runtime;
    return entity;
  });
}

function primaryAgentModule(entities: OperationalEntity[]): OperationalEntity | null {
  const primary = entities.find((entity) => entity.kind === "agent" && entity.role === "primary")
    ?? entities.find((entity) => entity.kind === "agent" && entity.entityId === "agent:artemis")
    ?? entities.find((entity) => entity.kind === "agent");
  if (!primary) return null;
  const related = entities.filter((entity) => entity.entityId !== primary.entityId && entity.kind !== "runtime"
    && (entity.parentEntityId === primary.entityId
      || (!entity.parentEntityId && ["task", "communication", "context-source"].includes(entity.kind)
        && entities.filter((item) => item.kind === "agent").length === 1)));
  const activeRelated = related.find((entity) => motionFor(entity.status) === "active");
  const completedRelated = related.find((entity) => entity.status === "completed");
  const activitySource = activeRelated ?? completedRelated ?? related[0] ?? primary;
  const workEntries = agentWorkEntries(primary, related);
  return {
    ...primary,
    entityId: primary.entityId,
    role: "primary",
    status: activeRelated?.status ?? primary.status,
    label: primary.label || "Artemis",
    currentTask: activitySource.currentTask ?? primary.currentTask ?? null,
    currentOperation: activitySource.currentOperation ?? primary.currentOperation ?? null,
    metadata: {
      ...primary.metadata,
      visual_module: "primary_agent",
      auxiliary_count: related.length,
      work_log: workEntries.join("\n")
    }
  };
}

function runtimeModule(entities: OperationalEntity[], primaryId: string | null, modelTelemetry: string[]): OperationalEntity | null {
  const runtime = entities.find((entity) => entity.kind === "runtime" && entity.metadata.selected_runtime === true)
    ?? entities.find((entity) => entity.kind === "runtime" && entity.parentEntityId === primaryId)
    ?? entities.find((entity) => entity.kind === "runtime");
  if (!runtime) return null;
  return {
    ...runtime,
    parentEntityId: runtime.parentEntityId ?? null,
    metadata: {
      ...runtime.metadata,
      visual_module: "model_runtime",
      telemetry_log: modelTelemetry.join("\n")
    }
  };
}

function agentWorkEntries(primary: OperationalEntity, related: OperationalEntity[]): string[] {
  const entries = [];
  const current = primary.currentTask ?? primary.currentOperation;
  if (current) entries.push(current);
  for (const entity of related) {
    const title = displayTitle(entity);
    const detail = entity.currentOperation ?? entity.currentTask ?? entity.status;
    entries.push(`${title}: ${detail}`);
  }
  return Array.from(new Set(entries)).slice(0, 8);
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
    ...positionFor(entity, index, total),
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
      resourceSummary: null,
      modelSummary: null,
      workLog: []
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
  const base = entity.kind === "agent" && entity.role === "primary" ? 28
    : entity.kind === "agent" ? 22
      : entity.kind === "runtime" ? 18
        : entity.kind === "task" || entity.kind === "mission" || entity.kind === "swarm" ? 15
          : entity.kind === "memory-source" || entity.kind === "context-source" ? 14
            : entity.kind === "worker" ? 16
              : 13;
  return Math.min(32, base + Math.log2(resourceWeight + 1) * 2);
}

function positionFor(entity: OperationalEntity, index: number, total: number): { x: number; y: number } {
  if (entity.kind === "agent" && entity.role === "primary") {
    return { x: 0.5, y: 0.5 };
  }
  if (entity.kind === "runtime" && entity.parentEntityId) {
    return { x: 0.64, y: 0.42 };
  }
  if (total <= 2 && entity.kind === "runtime") {
    return { x: 0.64, y: 0.42 };
  }
  if (entity.kind === "communication") {
    return { x: 0.62, y: 0.58 };
  }
  if (entity.kind === "voice-session") {
    return { x: 0.39, y: 0.58 };
  }
  if (entity.kind === "task" || entity.kind === "mission" || entity.kind === "swarm") {
    return orbitalPosition(entity.entityId, index, 0.23, 0.18);
  }
  if (entity.kind === "context-source" || entity.kind === "memory-source") {
    return orbitalPosition(entity.entityId, index, 0.30, 0.20);
  }
  if (entity.kind === "tool-execution") {
    return orbitalPosition(entity.entityId, index, 0.30, 0.22);
  }
  if (entity.kind === "worker") {
    return orbitalPosition(entity.entityId, index, 0.34, 0.25);
  }
  return stablePosition(entity.entityId, index, total);
}

function orbitalPosition(id: string, index: number, radiusX: number, radiusY: number): { x: number; y: number } {
  const a = hash(id);
  const angle = ((a % 360) / 360) * Math.PI * 2 + index * 0.53;
  const jitter = (((a >> 10) % 17) - 8) / 1000;
  return {
    x: clamp(0.5 + Math.cos(angle) * (radiusX + jitter), 0.22, 0.78),
    y: clamp(0.5 + Math.sin(angle) * (radiusY + jitter), 0.24, 0.76)
  };
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
    x: clamp(0.5 + Math.cos(angle) * (spread + crowding) * asymmetry, 0.18, 0.82),
    y: clamp(0.5 + Math.sin(angle) * (spread * 0.72 + crowding) * (1.18 - asymmetry / 3), 0.20, 0.80)
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
    title: displayTitle(entity),
    subtitle: `${entity.kind} · ${entity.status}`,
    currentTask: entity.currentTask ?? null,
    currentOperation: entity.currentOperation ?? null,
    resourceSummary: resources.length > 0 ? resources.join(" · ") : null,
    modelSummary: modelSummary(entity),
    workLog: workLog(entity)
  };
}

function modelRuntimeIsAvailable(model: ProviderModelOption): boolean {
  return model.provider_active && availabilityLooksReady(model.provider_status) && availabilityLooksReady(model.model_status);
}

function availabilityLooksReady(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  return normalized === "ready" || normalized === "available" || normalized === "configured" || normalized === "active";
}

function modelSummary(entity: OperationalEntity): string | null {
  const parts = [];
  const inputTokens = safeNumber(entity.metadata.input_count);
  const outputTokens = safeNumber(entity.metadata.output_count);
  const totalTokens = safeNumber(entity.metadata.total_count);
  const latencyMs = safeNumber(entity.metadata.latency_ms);
  const firstOutputMs = safeNumber(entity.metadata.first_output_ms);
  const outputRate = safeNumber(entity.metadata.output_rate);
  const finishReason = safeText(entity.metadata.finish_reason);
  if (inputTokens !== null) parts.push(`prompt ${inputTokens} tok`);
  if (outputTokens !== null) parts.push(`output ${outputTokens} tok`);
  if (totalTokens !== null) parts.push(`total ${totalTokens} tok`);
  if (latencyMs !== null) parts.push(`${(latencyMs / 1000).toFixed(1)}s`);
  if (firstOutputMs !== null) parts.push(`${firstOutputMs}ms first`);
  if (outputRate !== null) parts.push(`${outputRate.toFixed(1)}/s`);
  if (finishReason) parts.push(finishReason);
  return parts.length > 0 ? parts.join(" · ") : null;
}

function workLog(entity: OperationalEntity): string[] {
  if (entity.kind !== "runtime") {
    const metadataLog = safeText(entity.metadata.work_log);
    const entries = metadataLog ? metadataLog.split("\n").map((entry) => entry.trim()).filter(Boolean) : [];
    if (entity.currentTask) entries.unshift(entity.currentTask);
    return Array.from(new Set(entries)).slice(0, 8);
  }
  const telemetryLog = safeText(entity.metadata.telemetry_log);
  if (telemetryLog) {
    return telemetryLog.split("\n").map((entry) => entry.trim()).filter(Boolean).slice(-80);
  }
  const entries = [];
  const provider = safeText(entity.metadata.provider_id) ?? safeText(entity.metadata.providerId);
  const phase = safeText(entity.metadata.phase);
  const latencyMs = safeNumber(entity.metadata.latency_ms);
  const firstOutputMs = safeNumber(entity.metadata.first_output_ms);
  const outputRate = safeNumber(entity.metadata.output_rate);
  const inputCount = safeNumber(entity.metadata.input_count);
  const outputCount = safeNumber(entity.metadata.output_count);
  const totalCount = safeNumber(entity.metadata.total_count);
  const finishReason = safeText(entity.metadata.finish_reason);
  if (phase) entries.push(`Phase: ${phase.replace(/_/g, " ")}`);
  if (!phase && provider) {
    const label = provider === "synapse_local" ? "Synapse local runtime" : provider;
    entries.push(`Waiting for native telemetry from ${label}`);
  }
  if (entity.status === "processing") {
    entries.push("Status: thinking");
  } else if (entity.status === "completed") {
    entries.push("Status: response generated");
  } else if (entity.status !== "idle") {
    entries.push(`Status: ${entity.status}`);
  }
  if (phase && entity.currentTask) entries.push(entity.currentTask);
  if (phase && entity.currentOperation) entries.push(entity.currentOperation);
  if (inputCount !== null || outputCount !== null || totalCount !== null) {
    entries.push(`Tokens: input ${inputCount ?? "?"} · output ${outputCount ?? "?"} · total ${totalCount ?? "?"}`);
  }
  if (latencyMs !== null) entries.push(`Latency: ${(latencyMs / 1000).toFixed(1)}s`);
  if (firstOutputMs !== null) entries.push(`First output: ${firstOutputMs}ms`);
  if (outputRate !== null) entries.push(`Output rate: ${outputRate.toFixed(1)}/s`);
  if (finishReason) entries.push(`Finish: ${finishReason}`);
  if (entries.length === 0) entries.push("No native model telemetry received yet.");
  return Array.from(new Set(entries)).slice(0, 16);
}

function safeNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function safeText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function displayTitle(entity: OperationalEntity): string {
  if (!isOpaqueIdentifier(entity.label)) {
    return entity.label;
  }
  if (entity.kind === "communication") return "Conversation";
  if (entity.kind === "runtime") return "Model / Runtime";
  if (entity.kind === "voice-session") return "Voice Session";
  return entity.kind;
}

function isOpaqueIdentifier(value: string): boolean {
  return /^[0-9a-f]{6,}-[0-9a-f-]{8,}$/i.test(value.trim());
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
