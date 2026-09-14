import { describe, expect, it } from "vitest";
import { clusterPoints, ConstellationLayout, curveControl, curvePoint, identityColor, streamPoint, nebulaBreath } from "../src/renderer/constellationGeometry";
import type { ActivitySceneEdge, ActivitySceneNode } from "../src/shared/activityAdapter";

const node = (id: string): ActivitySceneNode => ({ id, label: id, category: "agent", color: "teal", status: "idle",
  motion: "quiet", halo: "none", x: 0, y: 0, radius: 28,
  metadata: { title: id, subtitle: null, currentTask: null, currentOperation: null, resourceSummary: null, modelSummary: null, workLog: [] } });
const edge: ActivitySceneEdge = { id: "request", sourceId: "agent", targetId: "model", kind: "communication", active: true, motion: "active" };

describe("constellation geometry", () => {
  it("keeps currents anchored and bounded without moving endpoints", () => {
    const a = {x: 0, y: 0}, b = {x: 200, y: 200};
    for (const strand of [-1,0,1]) {
      expect(streamPoint(a,b,"flow",0,strand)).toEqual(a);
      expect(streamPoint(a,b,"flow",1,strand).x).toBeCloseTo(b.x);
      expect(streamPoint(a,b,"flow",1,strand).y).toBeCloseTo(b.y);
    }
  });
  it("breathes much more during work but never flashes with reduced motion", () => {
    const samples = (energy: number) => Array.from({length:1000},(_,i)=>nebulaBreath(i/30,energy,0,false));
    const range = (values:number[]) => Math.max(...values)-Math.min(...values);
    expect(range(samples(1))).toBeGreaterThan(range(samples(0))*5);
    expect(Math.min(...samples(1))).toBeGreaterThan(0.89);
    expect(Math.max(...samples(1))).toBeLessThan(1.11);
    expect(nebulaBreath(10,1,0,true)).toBe(1);
  });
  it("uses stable, identity-specific particle distributions and theme colors", () => {
    expect(clusterPoints("a", 220, 64)).toEqual(clusterPoints("a", 220, 64));
    expect(clusterPoints("a", 220, 64)).not.toEqual(clusterPoints("b", 220, 64));
    expect(identityColor("a", "synapse")).not.toBe(identityColor("a", "violet"));
    const neutral = identityColor("a", "neutral");
    expect(Math.abs((neutral >> 16) - (neutral & 255))).toBeLessThan(20);
  });
  it("does not move existing identities during refresh, reordered data or incremental insertion", () => {
    const layout = new ConstellationLayout();
    layout.sync([node("agent"), node("model")], [edge]);
    const initial = JSON.stringify([...layout.positions]);
    layout.sync([node("model"), node("agent")], [edge]);
    expect(JSON.stringify([...layout.positions])).toBe(initial);
    const position = { ...layout.positions.get("agent")! };
    layout.sync([node("model"), node("agent"), node("tool")], [edge,
      { ...edge, id: "tool-use", targetId: "tool" }]);
    expect(layout.positions.get("agent")).toEqual(position);
    expect(layout.positions.size).toBe(3);
    layout.sync([node("agent"), node("model")], [edge]);
    expect(layout.positions.size).toBe(2);
  });
  it("encodes source-to-target travel without synthesizing a return", () => {
    const a = { x: 20, y: 30 }, b = { x: 240, y: 170 };
    const control = curveControl(a, b, edge.id);
    expect(curvePoint(a, control, b, 0)).toEqual(a);
    expect(curvePoint(a, control, b, 1)).toEqual(b);
    expect(control).not.toEqual({ x: 130, y: 100 });
  });
});
