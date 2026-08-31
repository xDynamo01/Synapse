import { describe, expect, it } from "vitest";
import {
  activityPerformanceBudget,
  applyActivityEvent,
  applyActivitySnapshot,
  createEmptyActivityState,
  deriveActivityScene,
  markActivityDisconnected
} from "../src/shared/activityAdapter";
import type { OperationalEntity, OperationalFact, OperationalRelation, ProjectActivitySnapshot } from "../src/shared/types";

const projectId = "project-a";

function entity(id: string, overrides: Partial<OperationalEntity> = {}): OperationalEntity {
  return {
    entityId: id,
    kind: "agent",
    role: "primary",
    status: "idle",
    label: id,
    currentTask: null,
    currentOperation: null,
    startedAt: null,
    parentEntityId: null,
    missionId: null,
    resources: { files: 0, memories: 0, toolResults: 0 },
    metadata: {},
    ...overrides
  };
}

function relation(id: string, sourceEntityId: string, targetEntityId: string, kind = "delegation"): OperationalRelation {
  return { relationId: id, sourceEntityId, targetEntityId, kind: kind as OperationalRelation["kind"], active: true };
}

function snapshot(entities: OperationalEntity[], relations: OperationalRelation[] = []): ProjectActivitySnapshot {
  return {
    format: "project-activity-snapshot-v1",
    projectId,
    revision: 3,
    observedAt: "2026-08-24T18:00:00+00:00",
    entities,
    relations,
    degraded: false,
    degradationReasons: [],
    lastEventId: "event-3"
  };
}

function event(revision: number, overrides: Partial<OperationalFact>): OperationalFact {
  return {
    formatVersion: "project-activity-event-v1",
    eventId: `event-${revision}`,
    projectId,
    revision,
    occurredAt: "2026-08-24T18:00:01+00:00",
    kind: "upsert-entity",
    sourceReference: "test",
    entity: entity(`agent:${revision}`),
    entityId: null,
    relation: null,
    relationId: null,
    degradationReason: null,
    correlationReference: null,
    metadata: {},
    ...overrides
  };
}

describe("activity adapter", () => {
  it("reports missing project scope as healthy empty activity", () => {
    const scene = deriveActivityScene(createEmptyActivityState(null), { selectedNodeId: null, reducedMotion: false, focused: true });
    expect(scene.status).toBe("empty");
    expect(scene.degradationReasons).toEqual([]);
  });
  it("derives an empty factual scene without synthetic nodes", () => {
    const scene = deriveActivityScene(createEmptyActivityState(projectId), {
      selectedNodeId: null,
      reducedMotion: false,
      focused: true
    });

    expect(scene.status).toBe("empty");
    expect(scene.nodes).toHaveLength(0);
    expect(scene.edges).toHaveLength(0);
  });

  it("maps snapshot entities and factual relations into scene nodes and edges", () => {
    const graph = applyActivitySnapshot(
      createEmptyActivityState(projectId),
      snapshot([
        entity("agent:primary", { role: "primary" }),
        entity("worker:1", { kind: "worker", role: "coding", status: "running" }),
        entity("tool:tests", { kind: "tool-execution", role: "execution", status: "processing" }),
        entity("memory:ctx", { kind: "memory-source", role: "context", status: "completed" })
      ], [
        relation("edge-1", "agent:primary", "worker:1", "delegation"),
        relation("edge-2", "worker:1", "tool:tests", "tool-use"),
        relation("edge-3", "memory:ctx", "agent:primary", "context-use")
      ]),
      "cursor-3"
    );
    const scene = deriveActivityScene(graph, { selectedNodeId: "worker:1", reducedMotion: false, focused: true });

    expect(scene.status).toBe("ready");
    expect(scene.nodes.find((node) => node.id === "agent:primary")?.color).toBe("teal");
    expect(scene.nodes.find((node) => node.id === "worker:1")?.color).toBe("orange");
    expect(scene.nodes.find((node) => node.id === "tool:tests")?.category).toBe("tool");
    expect(scene.nodes.find((node) => node.id === "memory:ctx")?.color).toBe("neutral");
    expect(scene.edges).toHaveLength(3);
    expect(scene.selectedNodeId).toBe("worker:1");
  });

  it("rejects stale and cross-project events", () => {
    const base = applyActivitySnapshot(createEmptyActivityState(projectId), snapshot([entity("agent:primary")]), "cursor-3");
    const stale = applyActivityEvent(base, event(2, { eventId: "old" }), "old-cursor");
    const crossProject = applyActivityEvent(base, event(4, { projectId: "project-b" }), "other-cursor");

    expect(stale.revision).toBe(3);
    expect(crossProject.revision).toBe(3);
    expect(crossProject.projectId).toBe(projectId);
  });

  it("marks revision gaps as resync required", () => {
    const base = applyActivitySnapshot(createEmptyActivityState(projectId), snapshot([entity("agent:primary")]), "cursor-3");
    const graph = applyActivityEvent(base, event(8, {}), "cursor-8");
    const scene = deriveActivityScene(graph, { selectedNodeId: null, reducedMotion: false, focused: true });

    expect(scene.status).toBe("resyncing");
    expect(scene.degradationReasons).toContain("activity resync required");
  });

  it("tracks live relation events as bounded flows", () => {
    const base = applyActivitySnapshot(
      createEmptyActivityState(projectId),
      snapshot([entity("agent:primary"), entity("worker:1", { kind: "worker", role: "coding" })]),
      "cursor-3"
    );
    const graph = applyActivityEvent(
      base,
      event(4, { kind: "upsert-relation", relation: relation("edge-1", "agent:primary", "worker:1", "communication") }),
      "cursor-4"
    );
    const scene = deriveActivityScene(graph, { selectedNodeId: null, reducedMotion: false, focused: true });

    expect(scene.edges[0]?.kind).toBe("communication");
    expect(scene.flows).toHaveLength(1);
  });

  it("derives factual parent edges from entity parent ids", () => {
    const graph = applyActivitySnapshot(
      createEmptyActivityState(projectId),
      snapshot([
        entity("agent:artemis", { role: "primary", status: "processing", label: "Primary Agent" }),
        entity("runtime:lmstudio:model", {
          kind: "runtime",
          role: "chat",
          status: "completed",
          label: "LM Studio",
          parentEntityId: "agent:artemis"
        })
      ]),
      "cursor-3"
    );
    const scene = deriveActivityScene(graph, { selectedNodeId: null, reducedMotion: false, focused: true });

    expect(scene.status).toBe("ready");
    expect(scene.nodes.map((node) => node.id)).toContain("agent:artemis");
    expect(scene.nodes.map((node) => node.id)).toContain("runtime:lmstudio:model");
    expect(scene.edges).toEqual([
      expect.objectContaining({
        sourceId: "agent:artemis",
        targetId: "runtime:lmstudio:model",
        kind: "communication"
      })
    ]);
  });

  it("aggregates large swarms and reduces budget under reduced motion", () => {
    const many = Array.from({ length: activityPerformanceBudget.normal.maxNodes + 7 }, (_, index) =>
      entity(`worker:${index}`, { kind: "worker", role: "coding", status: "running" })
    );
    const graph = applyActivitySnapshot(createEmptyActivityState(projectId), snapshot(many), "cursor-3");
    const scene = deriveActivityScene(graph, { selectedNodeId: null, reducedMotion: true, focused: false });

    expect(scene.nodes.length).toBe(activityPerformanceBudget.reduced.maxNodes + 1);
    expect(scene.nodes.at(-1)?.category).toBe("aggregate");
    expect(scene.flows).toHaveLength(0);
    expect(scene.budget.focusedFps).toBe(18);
  });

  it("represents degraded and disconnected states explicitly", () => {
    const degradedSnapshot = { ...snapshot([entity("agent:primary")]), degraded: true, degradationReasons: ["provider degraded"] };
    const graph = markActivityDisconnected(
      applyActivitySnapshot(createEmptyActivityState(projectId), degradedSnapshot, "cursor-3")
    );
    const scene = deriveActivityScene(graph, { selectedNodeId: null, reducedMotion: false, focused: true });

    expect(scene.status).toBe("disconnected");
    expect(scene.degradationReasons).toContain("provider degraded");
    expect(scene.degradationReasons).toContain("activity stream disconnected");
  });

  it("ignores malformed projection entities without crashing scene layout", () => {
    const graph = applyActivitySnapshot(
      createEmptyActivityState(projectId),
      { ...snapshot([entity("agent:primary")]), entities: [{ ...entity("agent:primary"), entityId: undefined } as never] },
      "cursor-malformed"
    );
    expect(() => deriveActivityScene(graph, { selectedNodeId: null, reducedMotion: false, focused: true })).not.toThrow();
    expect(graph.entities.size).toBe(0);
  });
});
