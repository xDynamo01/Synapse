import type { ActivitySceneEdge, ActivitySceneNode } from "../shared/activityAdapter";

export interface Point { x: number; y: number }
export function seedFor(id: string): number {
  let seed = 2166136261;
  for (const character of id) seed = Math.imul(seed ^ character.charCodeAt(0), 16777619);
  return seed >>> 0;
}
export function randomFor(id: string): () => number {
  let seed = seedFor(id);
  return () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 4294967296;
  };
}
export function clusterRadius(node: ActivitySceneNode): number {
  return node.category === "primary" || node.category === "agent" ? 64
    : node.category === "provider" || node.category === "worker" ? 49 : 31;
}
export function particleCount(node: ActivitySceneNode): number {
  return node.category === "primary" || node.category === "agent" ? 220
    : node.category === "provider" || node.category === "worker" ? 125 : 46;
}
export function clusterPoints(id: string, count: number, radius: number): (Point & { size: number; alpha: number })[] {
  const random = randomFor(id);
  return Array.from({ length: count }, () => {
    const u = random() * 2 - 1;
    const spread = (random() + random() + random() - 1.5) * (0.16 + 0.42 * (1 - Math.abs(u)));
    return { x: u * radius * 1.3, y: radius * (u * 0.36 + Math.sin(u * 5) * 0.12 + spread),
      size: 0.35 + random() ** 3 * 1.35, alpha: 0.2 + random() * 0.65 };
  });
}

/** Static S-shaped current: decoration does not imply transmission. */
export function streamPoint(source: Point, target: Point, id: string, t: number, strand = 0): Point {
  const dx = target.x - source.x, dy = target.y - source.y;
  const distance = Math.max(1, Math.hypot(dx, dy));
  const bend = Math.sin(t * Math.PI * 2) * distance * 0.10 * (seedFor(id) % 2 ? 1 : -1)
    + Math.sin(t * Math.PI) * strand * 3;
  return { x: source.x + dx * t - dy / distance * bend, y: source.y + dy * t + dx / distance * bend };
}

/** Active energy comes exclusively from the factual scene; reduced motion is static. */
export function nebulaBreath(time: number, energy: number, phase: number, reduced: boolean): number {
  if (reduced) return 1;
  const work = Math.max(0, Math.min(1, energy));
  return 1 + Math.sin(time * (0.65 + work * 1.05) + phase) * (0.014 + work * 0.085);
}

/** Incremental layout: existing identities never get reseeded on status/log updates. */
export class ConstellationLayout {
  readonly positions = new Map<string, Point>();
  sync(nodes: ActivitySceneNode[], edges: ActivitySceneEdge[]): void {
    // Establish the selected two-participant composition once, never on refresh.
    if (this.positions.size === 0) {
      const primary = nodes.find(node => node.category === "primary");
      const model = nodes.find(node => node.category === "provider");
      if (primary && model) {
        this.positions.set(primary.id, { x: -105, y: -95 });
        this.positions.set(model.id, { x: 105, y: 95 });
      }
    }
    const ids = new Set(nodes.map((node) => node.id));
    for (const id of this.positions.keys()) if (!ids.has(id)) this.positions.delete(id);
    const added = new Set<string>();
    for (const node of [...nodes].sort((a, b) => a.id.localeCompare(b.id))) {
      if (this.positions.has(node.id)) continue;
      const random = randomFor(node.id);
      const relation = edges.find((edge) => (edge.sourceId === node.id && this.positions.has(edge.targetId))
        || (edge.targetId === node.id && this.positions.has(edge.sourceId)));
      const neighbor = relation ? this.positions.get(relation.sourceId === node.id ? relation.targetId : relation.sourceId) : null;
      const angle = random() * Math.PI * 2;
      const distance = neighbor ? 210 : 140 + random() * 130;
      this.positions.set(node.id, { x: (neighbor?.x ?? 0) + Math.cos(angle) * distance,
        y: (neighbor?.y ?? 0) + Math.sin(angle) * distance });
      added.add(node.id);
    }
    // Settle only newly introduced nodes. Stable nodes are anchors, not a live simulation.
    for (let iteration = 0; iteration < 100; iteration++) {
      for (const id of added) {
        const point = this.positions.get(id)!;
        let fx = 0, fy = 0;
        for (const [otherId, other] of this.positions) {
          if (id === otherId) continue;
          const dx = point.x - other.x, dy = point.y - other.y;
          const distance = Math.max(1, Math.hypot(dx, dy));
          const repulsion = Math.max(0, 200 - distance) * 0.12;
          fx += dx / distance * repulsion; fy += dy / distance * repulsion;
        }
        for (const edge of edges) {
          const otherId = edge.sourceId === id ? edge.targetId : edge.targetId === id ? edge.sourceId : null;
          const other = otherId ? this.positions.get(otherId) : null;
          if (!other) continue;
          const dx = other.x - point.x, dy = other.y - point.y;
          const distance = Math.max(1, Math.hypot(dx, dy));
          const spring = (distance - 235) * 0.018;
          fx += dx / distance * spring; fy += dy / distance * spring;
        }
        point.x += Math.max(-8, Math.min(8, fx)); point.y += Math.max(-8, Math.min(8, fy));
      }
    }
  }
}

export function curveControl(source: Point, target: Point, id: string): Point {
  const bend = (seedFor(id) % 2 ? 1 : -1) * 0.16;
  return { x: (source.x + target.x) / 2 - (target.y - source.y) * bend,
    y: (source.y + target.y) / 2 + (target.x - source.x) * bend };
}
export function curvePoint(source: Point, control: Point, target: Point, t: number): Point {
  return { x: (1 - t) ** 2 * source.x + 2 * (1 - t) * t * control.x + t * t * target.x,
    y: (1 - t) ** 2 * source.y + 2 * (1 - t) * t * control.y + t * t * target.y };
}

/** Identity chooses a hue, never an inferred role. Neutral deliberately desaturates all hues. */
export function identityColor(id: string, theme: string): number {
  const offsets: Record<string, number> = { synapse: 174, violet: 265, amber: 36, blue: 209, neutral: 200 };
  const hue = ((offsets[theme] ?? 174) + (seedFor(id) % 7) * 47) % 360;
  const saturation = theme === "neutral" ? 0.10 : 0.80;
  const lightness = 0.66;
  const a = saturation * Math.min(lightness, 1 - lightness);
  const channel = (n: number) => {
    const k = (n + hue / 30) % 12;
    return Math.round(255 * (lightness - a * Math.max(-1, Math.min(k - 3, 9 - k, 1))));
  };
  return (channel(0) << 16) | (channel(8) << 8) | channel(4);
}
