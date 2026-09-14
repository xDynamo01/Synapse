import { describe, expect, it } from "vitest";
import {
  activityPerformanceBudget,
  applyActivityEvent,
  applyActivitySnapshot,
  createEmptyActivityState,
  createBaselineActivityState,
  deriveActivityScene,
  markActivityDisconnected,
  withBaselineActivityState
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
  it("keeps only primary and selected runtime fixed; resources enter only during real use", () => {
    const entities = [entity("agent"), entity("model", { kind: "runtime", parentEntityId: "agent" }),
      entity("tool", { kind: "tool-execution", status: "idle" }), entity("worker", { kind: "worker", status: "completed" })];
    const options = { selectedNodeId: null, reducedMotion: false, focused: true };
    let graph = applyActivitySnapshot(createEmptyActivityState(projectId), snapshot(entities), "3");
    expect(deriveActivityScene(graph, options).nodes.map((node) => node.id)).toEqual(["agent", "model"]);
    graph = applyActivityEvent(graph, event(4, { entity: { ...entities[2], status: "running" } }), "4");
    expect(deriveActivityScene(graph, options).nodes.map((node) => node.id)).toEqual(["agent", "model", "tool"]);
    graph = applyActivityEvent(graph, event(5, { entity: { ...entities[2], status: "completed" } }), "5");
    expect(deriveActivityScene(graph, options).nodes.map((node) => node.id)).toEqual(["agent", "model"]);
  });

  it("does not animate parent associations or inactive relation updates", () => {
    let graph = applyActivitySnapshot(createEmptyActivityState(projectId), snapshot([entity("a"), entity("b")]), "3");
    graph = applyActivityEvent(graph, event(4, { kind: "upsert-relation", relation: relation("parent", "a", "b", "parent") }), "4");
    graph = applyActivityEvent(graph, event(5, { kind: "upsert-relation", relation: { ...relation("done", "b", "a"), active: false } }), "5");
    expect(graph.flows).toEqual([]);
  });

  it("uses explicit projected request/response direction and rejects duplicate event replay", () => {
    let graph = applyActivitySnapshot(createEmptyActivityState(projectId), snapshot([
      entity("agent:artemis"), entity("runtime:local:model", { kind: "runtime", parentEntityId: "agent:artemis" })
    ]), "3");
    const request = event(4, { metadata: { transfer_source: "agent:artemis", transfer_target: "runtime:local:model", transfer_kind: "request" } });
    graph = applyActivityEvent(graph, request, "4");
    graph = applyActivityEvent(graph, request, "4");
    expect(graph.flows).toHaveLength(1);
    graph = applyActivityEvent(graph, event(5, { metadata: {
      transfer_source: "runtime:local:model", transfer_target: "agent:artemis", transfer_kind: "response"
    } }), "5");
    const scene = deriveActivityScene(graph, { selectedNodeId: null, reducedMotion: false, focused: true });
    expect(scene.edges.map((edge) => [edge.sourceId, edge.targetId])).toEqual([
      ["agent:artemis", "runtime:local:model"], ["runtime:local:model", "agent:artemis"]
    ]);
    expect(scene.flows).toHaveLength(2);
  });

  it("matches registry primary identity to projection identity without duplicate clusters", () => {
    const graph = applyActivitySnapshot(createEmptyActivityState(projectId), snapshot([
      entity("agent:artemis", { role: "presence", label: "Old label", status: "processing" })
    ]), "3");
    const scene = deriveActivityScene(withBaselineActivityState(graph, { agent_id: "artemis", name: "Artemis" }),
      { selectedNodeId: null, reducedMotion: false, focused: true });
    expect(scene.nodes).toHaveLength(1);
    expect(scene.nodes[0]).toMatchObject({ id: "agent:artemis", label: "Artemis", status: "processing" });
  });
  it("keeps the latest 80 model log lines in order, including repeated events", () => {
    const graph = applyActivitySnapshot(createEmptyActivityState(projectId), snapshot([
      entity("agent:primary"),
      entity("runtime:local", { kind: "runtime", label: "DeepSeek", parentEntityId: "agent:primary" })
    ]), "cursor-3");
    const lines = Array.from({ length: 90 }, (_, index) => `event ${index}`);
    lines.push("evaluating", "evaluating");
    const scene = deriveActivityScene(graph, {
      selectedNodeId: "runtime:local", reducedMotion: false, focused: true, modelTelemetry: lines
    });
    expect(scene.nodes.find((node) => node.id === "runtime:local")?.metadata.workLog).toEqual(lines.slice(-80));
  });

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

  it("keeps a factual baseline primary agent and model runtime when projections are empty", () => {
    const baseline = createBaselineActivityState(
      "conversation:abc",
      { agent_id: "agent:artemis", name: "Primary Agent" },
      {
        provider_id: "lmstudio",
        provider_status: "ready",
        provider_active: true,
        model_id: "qwen/qwen3-4b-thinking-2507",
        model_status: "ready",
        runtime: "local",
        origin: "settings",
        availability_state: "ready",
        is_default: true
      }
    );
    const emptiedBySnapshot = applyActivitySnapshot(baseline, snapshot([]), "cursor-empty");
    const scene = deriveActivityScene(
      withBaselineActivityState(
        emptiedBySnapshot,
        { agent_id: "agent:artemis", name: "Primary Agent" },
        {
          provider_id: "lmstudio",
          provider_status: "ready",
          provider_active: true,
          model_id: "qwen/qwen3-4b-thinking-2507",
          model_status: "ready",
          runtime: "local",
          origin: "settings",
          availability_state: "ready",
          is_default: true
        }
      ),
      { selectedNodeId: null, reducedMotion: false, focused: true }
    );

    expect(scene.status).toBe("ready");
    const primary = scene.nodes.find((node) => node.label === "Primary Agent");
    const runtime = scene.nodes.find((node) => node.label === "qwen/qwen3-4b-thinking-2507");
    expect(primary).toEqual(expect.objectContaining({ x: 0.5, y: 0.5, radius: 28 }));
    expect(runtime).toEqual(expect.objectContaining({ x: 0.64, y: 0.42 }));
    expect(scene.edges).toEqual([
      expect.objectContaining({
        sourceId: "agent:artemis",
        targetId: "runtime:lmstudio:qwen/qwen3-4b-thinking-2507",
        kind: "parent", active: false
      })
    ]);
  });

  it("keeps runtime fallback visible when the selected model is not marked default", () => {
    const scene = deriveActivityScene(
      createBaselineActivityState(
        projectId,
        { agent_id: "agent:artemis", name: "Artemis" },
        {
          provider_id: "lmstudio",
          provider_status: "ready",
          provider_active: true,
          model_id: "local-model",
          model_status: "ready",
          runtime: "local",
          origin: "settings",
          availability_state: "ready",
          is_default: false
        }
      ),
      { selectedNodeId: null, reducedMotion: false, focused: true }
    );

    expect(scene.nodes.map((node) => node.label)).toContain("local-model");
  });

  it("does not overwrite live runtime activity with the baseline model", () => {
    const graph = applyActivitySnapshot(
      createEmptyActivityState("conversation:abc"),
      snapshot([
        entity("runtime:lmstudio:deepseek/deepseek-r1-0528-qwen3-8b", {
          kind: "runtime",
          role: "local_chat",
          label: "deepseek/deepseek-r1-0528-qwen3-8b",
          status: "completed",
          currentTask: "Assistant response complete",
          currentOperation: "Response generated",
          parentEntityId: "agent:artemis",
          metadata: {
            provider_id: "lmstudio",
            phase: "completed",
            input_count: 353,
            output_count: 295,
            total_count: 648,
            latency_ms: 6457,
            first_output_ms: 686,
            output_rate: 48.97,
            finish_reason: "stop"
          }
        })
      ]),
      "cursor-live"
    );
    const scene = deriveActivityScene(
      withBaselineActivityState(
        graph,
        { agent_id: "agent:artemis", name: "Artemis" },
        {
          provider_id: "lmstudio",
          provider_status: "ready",
          provider_active: true,
          model_id: "deepseek/deepseek-r1-0528-qwen3-8b",
          model_status: "ready",
          runtime: "local",
          origin: "settings",
          availability_state: "ready",
          is_default: true
        }
      ),
      { selectedNodeId: null, reducedMotion: false, focused: true }
    );

    const runtime = scene.nodes.find((node) => node.id === "runtime:lmstudio:deepseek/deepseek-r1-0528-qwen3-8b");
    expect(runtime?.metadata.subtitle).toBe("runtime · completed");
    expect(runtime?.metadata.workLog).toContain("Status: response generated");
    expect(runtime?.metadata.workLog).toContain("Phase: completed");
    expect(runtime?.metadata.workLog).toContain("Tokens: input 353 · output 295 · total 648");
    expect(runtime?.metadata.workLog).toContain("Finish: stop");
    expect(runtime?.metadata.workLog).toContain("First output: 686ms");
    expect(runtime?.metadata.workLog).toContain("Output rate: 49.0/s");
  });

  it("uses native telemetry lines as the model runtime log when available", () => {
    const graph = applyActivitySnapshot(
      createEmptyActivityState("conversation:abc"),
      snapshot([
        entity("agent:artemis", { role: "primary", label: "Artemis" }),
        entity("runtime:lmstudio:deepseek/deepseek-r1-0528-qwen3-8b", {
          kind: "runtime",
          role: "local_chat",
          label: "deepseek/deepseek-r1-0528-qwen3-8b",
          status: "idle",
          parentEntityId: "agent:artemis",
          currentOperation: "lmstudio",
          metadata: { provider_id: "lmstudio" }
        })
      ]),
      "cursor-live"
    );
    const scene = deriveActivityScene(graph, {
      selectedNodeId: null,
      reducedMotion: false,
      focused: true,
      modelTelemetry: ["2026-09-03 10:19:39 [DEBUG] [deepseek] reasoning | Model reasoning in progress"]
    });

    const runtime = scene.nodes.find((node) => node.id === "runtime:lmstudio:deepseek/deepseek-r1-0528-qwen3-8b");
    expect(runtime?.metadata.workLog).toEqual([
      "2026-09-03 10:19:39 [DEBUG] [deepseek] reasoning | Model reasoning in progress"
    ]);
  });

  it("treats available model hub status as an operational idle runtime", () => {
    const scene = deriveActivityScene(
      createBaselineActivityState(
        projectId,
        { agent_id: "agent:artemis", name: "Artemis" },
        {
          provider_id: "lmstudio",
          provider_status: "available",
          provider_active: true,
          model_id: "deepseek/deepseek-r1",
          model_status: "available",
          runtime: "local",
          origin: "settings",
          availability_state: "available",
          is_default: true
        }
      ),
      { selectedNodeId: null, reducedMotion: false, focused: true }
    );

    const runtime = scene.nodes.find((node) => node.category === "provider");
    expect(runtime?.status).toBe("idle");
    expect(runtime?.metadata.subtitle).toBe("runtime · idle");
  });

  it("aggregates opaque conversation activity into the primary agent module", () => {
    const graph = applyActivitySnapshot(
      createEmptyActivityState(projectId),
      snapshot([
        entity("agent:artemis", { role: "primary", label: "Artemis" }),
        entity("632ac174-e805-4183-abcd-123456789abc", {
          kind: "communication",
          role: "conversation",
          label: "632ac174-e805-4183-abcd-123456789abc",
          status: "processing"
        })
      ]),
      "cursor-3"
    );
    const scene = deriveActivityScene(graph, { selectedNodeId: null, reducedMotion: false, focused: true });

    expect(scene.nodes).toHaveLength(1);
    expect(scene.nodes[0]?.metadata.title).toBe("Artemis");
    expect(scene.nodes[0]?.metadata.workLog).toContain("Conversation: processing");
  });

  it("formats model runtime metrics for the constellation details", () => {
    const graph = applyActivitySnapshot(
      createEmptyActivityState(projectId),
      snapshot([
        entity("runtime:lmstudio:deepseek", {
          kind: "runtime",
          role: "local",
          label: "deepseek/deepseek-r1",
          status: "completed",
          metadata: {
            input_count: 353,
            output_count: 295,
            total_count: 648,
            latency_ms: 6457,
            finish_reason: "stop"
          }
        })
      ]),
      "cursor-3"
    );
    const scene = deriveActivityScene(graph, { selectedNodeId: null, reducedMotion: false, focused: true });

    expect(scene.nodes[0]?.metadata.modelSummary).toBe("prompt 353 tok · output 295 tok · total 648 tok · 6.5s · stop");
    expect(scene.nodes[0]?.metadata.workLog).toContain("Status: response generated");
    expect(scene.nodes[0]?.metadata.workLog).toContain("Tokens: input 353 · output 295 · total 648");
    expect(scene.nodes[0]?.metadata.workLog).toContain("Latency: 6.5s");
  });

  it("folds task and context entities into the primary agent module instead of rendering extra nodes", () => {
    const graph = applyActivitySnapshot(
      createEmptyActivityState(projectId),
      snapshot([
        entity("agent:artemis", { role: "primary", label: "Artemis" }),
        entity("runtime:lmstudio:deepseek", {
          kind: "runtime",
          role: "local",
          label: "deepseek/deepseek-r1",
          status: "idle",
          parentEntityId: "agent:artemis"
        }),
        entity("task:conversation-turn", {
          kind: "task",
          role: "turn",
          label: "task",
          status: "processing"
        }),
        entity("context_fusion:turn", {
          kind: "context-source",
          role: "context",
          label: "context_fusion",
          status: "completed"
        })
      ]),
      "cursor-3"
    );
    const scene = deriveActivityScene(graph, { selectedNodeId: null, reducedMotion: false, focused: true });

    expect(scene.nodes.map((node) => node.id)).toEqual(["agent:artemis", "runtime:lmstudio:deepseek"]);
    expect(scene.nodes[0]?.metadata.workLog).toContain("task: processing");
    expect(scene.nodes[0]?.metadata.workLog).toContain("context_fusion: completed");
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
    expect(scene.nodes).toHaveLength(4);
    expect(scene.nodes.find((node) => node.id === "worker:1")?.category).toBe("worker");
    expect(scene.nodes.find((node) => node.id === "tool:tests")?.category).toBe("tool");
    expect(scene.nodes.find((node) => node.id === "memory:ctx")?.category).toBe("resource");
    expect(scene.edges).toHaveLength(3);
    expect(scene.edges[2]).toMatchObject({ sourceId: "memory:ctx", targetId: "agent:primary" });
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

    expect(scene.nodes).toHaveLength(2);
    expect(scene.edges).toHaveLength(1);
    expect(scene.flows).toHaveLength(1);
    expect(scene.flows[0]?.edgeId).toBe("edge-1");
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
        kind: "parent", active: false
      })
    ]);
  });

  it("bounds real active swarm participants without inventing extra agents", () => {
    const many = Array.from({ length: activityPerformanceBudget.normal.maxNodes + 7 }, (_, index) =>
      entity(`worker:${index}`, { kind: "worker", role: "coding", status: "running" })
    );
    const graph = applyActivitySnapshot(
      createEmptyActivityState(projectId),
      snapshot([entity("agent:primary", { role: "primary" }), ...many]),
      "cursor-3"
    );
    const scene = deriveActivityScene(graph, { selectedNodeId: null, reducedMotion: true, focused: false });

    expect(scene.nodes).toHaveLength(activityPerformanceBudget.reduced.maxNodes + 1);
    expect(scene.nodes.at(-1)?.aggregateCount).toBe(many.length + 1 - activityPerformanceBudget.reduced.maxNodes);
    expect(scene.nodes[0]?.id).toBe("agent:primary");
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
