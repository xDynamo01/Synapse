import { Application, Container, Graphics, Sprite, Text, Texture } from "pixi.js";
// Pixi's CSP polyfill replaces generated functions; it does NOT relax script-src.
import "pixi.js/unsafe-eval";
import type { ActivitySceneEdge, ActivitySceneNode, ActivitySceneState } from "../shared/activityAdapter";
import { clusterPoints, clusterRadius, ConstellationLayout, streamPoint, nebulaBreath, identityColor, seedFor } from "./constellationGeometry";

interface Cluster {
  node: ActivitySceneNode;
  root: Container;
  dust: Graphics;
  halo: Container;
  body: Container;
  label: Text;
  energy: number;
  opacity: number;
  departingAt: number | null;
}
import { particleCount } from "./constellationGeometry";

/** Owns GPU resources and the animation clock. React only supplies factual snapshots. */
export class ConstellationCanvas {
  private app = new Application();
  private world = new Container();
  private wires = new Graphics();
  private pulses = new Graphics();
  private lightTexture: Texture | null = null;
  private nebulaTexture: Texture | null = null;
  private clusters = new Map<string, Cluster>();
  private layout = new ConstellationLayout();
  private scene: ActivitySceneState | null = null;
  private theme = "synapse";
  private seenFlows = new Set<string>();
  private flights = new Map<string, { edgeId: string; born: number }>();
  private connections = new Map<string, { edge: ActivitySceneEdge; opacity: number; retiringAt: number | null }>();
  private disposed = false;
  private initialized = false;
  private observer: ResizeObserver | null = null;
  private camera = { x: 0, y: 0, scale: 1 };
  private target = { x: 0, y: 0, scale: 1 };
  private pointer: { x: number; y: number; moved: boolean; id: number } | null = null;
  private lastTime = 0;
  private animationTime = 0;

  constructor(private host: HTMLElement, private select: (id: string | null) => void) {}

  async init(): Promise<void> {
    await this.app.init({ backgroundAlpha: 0, antialias: true, autoDensity: true,
      resolution: Math.min(devicePixelRatio || 1, 2), resizeTo: this.host, preference: "webgl" });
    this.initialized = true;
    if (this.disposed) { this.app.destroy(true, { children: true }); return; }
    // Same radial falloff as Presence, cached once and shared by every light sprite.
    const light = document.createElement("canvas");
    light.width = light.height = 128;
    const context = light.getContext("2d");
    if (!context) throw new Error("Local light texture is unavailable");
    const gradient = context.createRadialGradient(64, 64, 0, 64, 64, 64);
    gradient.addColorStop(0, "rgba(255,255,255,1)");
    gradient.addColorStop(0.42, "rgba(255,255,255,0.38)");
    gradient.addColorStop(1, "rgba(255,255,255,0)");
    context.fillStyle = gradient;
    context.fillRect(0, 0, 128, 128);
    this.lightTexture = Texture.from(light);
    const nebula = new Image();
    await new Promise<void>((resolve, reject) => {
      nebula.onload = () => resolve();
      nebula.onerror = () => reject(new Error("Nebula texture is unavailable"));
      nebula.src = new URL("../../assets/media/nebula-stream.png", import.meta.url).href;
    });
    if (this.disposed) return;
    // Convert the authored luminance mask to coverage once. This avoids opaque
    // black quads across renderer/blend backends and keeps theme tint independent.
    const mask = document.createElement("canvas");
    mask.width = nebula.naturalWidth; mask.height = nebula.naturalHeight;
    const maskContext = mask.getContext("2d");
    if (!maskContext) throw new Error("Nebula mask is unavailable");
    maskContext.drawImage(nebula, 0, 0);
    const pixels = maskContext.getImageData(0, 0, mask.width, mask.height);
    for (let i = 0; i < pixels.data.length; i += 4) {
      pixels.data[i + 3] = Math.round(255 * (Math.max(pixels.data[i], pixels.data[i + 1], pixels.data[i + 2]) / 255) ** 0.64);
      pixels.data[i] = pixels.data[i + 1] = pixels.data[i + 2] = 255;
    }
    maskContext.putImageData(pixels, 0, 0);
    this.nebulaTexture = Texture.from(mask);
    this.pulses.blendMode = "add";
    this.host.appendChild(this.app.canvas);
    this.app.canvas.setAttribute("aria-hidden", "true");
    this.world.addChild(this.wires, this.pulses);
    this.app.stage.addChild(this.world);
    this.app.ticker.maxFPS = 36;
    this.app.ticker.add(this.tick);
    this.host.addEventListener("pointerdown", this.down);
    this.host.addEventListener("pointermove", this.move);
    this.host.addEventListener("pointerup", this.up);
    this.host.addEventListener("pointercancel", this.cancel);
    this.host.addEventListener("keydown", this.key);
    document.addEventListener("visibilitychange", this.visibility);
    this.observer = new ResizeObserver(() => this.fit());
    this.observer.observe(this.host);
    if (this.scene) this.update(this.scene, this.theme);
  }

  update(scene: ActivitySceneState, theme: string): void {
    const first = this.scene === null;
    const themeChanged = theme !== this.theme;
    this.scene = scene;
    this.theme = theme;
    if (!this.initialized || !this.nebulaTexture || this.disposed) return;
    const edgeIds = new Set(scene.edges.map((edge) => edge.id));
    for (const edge of scene.edges) {
      const previous = this.connections.get(edge.id);
      this.connections.set(edge.id, { edge, opacity: previous?.opacity ?? 0, retiringAt: null });
    }
    for (const [id, connection] of this.connections) {
      if (!edgeIds.has(id) && connection.retiringAt === null) connection.retiringAt = performance.now();
    }
    this.app.ticker.maxFPS = scene.focused ? scene.budget.focusedFps : scene.budget.unfocusedFps;
    const oldIds = new Set(this.clusters.keys());
    const ids = new Set(scene.nodes.map((node) => node.id));
    this.layout.sync(scene.nodes, scene.edges);
    for (const node of scene.nodes) {
      let cluster = this.clusters.get(node.id);
      if (cluster && themeChanged) {
        cluster.root.destroy({ children: true }); this.clusters.delete(node.id); cluster = undefined;
      }
      if (!cluster) {
        cluster = this.createCluster(node);
        this.clusters.set(node.id, cluster);
        this.world.addChild(cluster.root);
      }
      cluster.node = node;
      cluster.label.text = node.metadata.title.length > 32 ? `${node.metadata.title.slice(0, 29)}…` : node.metadata.title;
      cluster.departingAt = null;
      const point = this.layout.positions.get(node.id)!;
      cluster.root.position.set(point.x, point.y);
    }
    for (const [id, cluster] of this.clusters) {
      if (!ids.has(id) && cluster.departingAt === null) cluster.departingAt = performance.now();
    }
    for (const flow of scene.flows) {
      if (!this.seenFlows.has(flow.id) && !first && !scene.reducedMotion && ["ready", "degraded"].includes(scene.status)) {
        for (const [id, flight] of this.flights) if (flight.edgeId === flow.edgeId) this.flights.delete(id);
        this.flights.set(flow.id, { edgeId: flow.edgeId, born: performance.now() });
      }
      this.seenFlows.add(flow.id);
    }
    // Replay suppression is bounded independently of the transient GPU objects.
    this.seenFlows = new Set([...this.seenFlows].slice(-256));
    if (scene.reducedMotion || !["ready", "degraded"].includes(scene.status)) this.flights.clear();
    if (oldIds.size === 0 || scene.nodes.some((node) => !oldIds.has(node.id))) this.fit();
  }

  private createCluster(node: ActivitySceneNode): Cluster {
    const root = new Container();
    const dust = new Graphics();
    const body = new Container();
    const halo = new Container();
    const lights = new Container();
    const core = new Graphics();
    const color = identityColor(node.id, this.theme);
    const radius = clusterRadius(node);
    const points = clusterPoints(node.id, particleCount(node), radius);
    dust.blendMode = "add";
    core.blendMode = "add";
    // Illuminate the space BETWEEN particles, not only the tiny luminous points.
    // Every lobe fades to zero locally; no viewport-sized background light.
    const cloud = new Sprite(this.nebulaTexture!);
    cloud.anchor.set(0.5);
    cloud.width = radius * 4; cloud.height = radius * 3.3;
    cloud.tint = color; cloud.blendMode = "add"; cloud.alpha = 0.95;
    halo.addChild(cloud);
    lights.addChild(this.light(radius * 0.4, color, 0.22), this.light(radius * 0.14, color, 0.42),
      this.light(radius * 0.055, color, 0.85));
    // All geometry is generated once per identity/theme. No per-particle React work.
    points.forEach((point, index) => {
      dust.circle(point.x, point.y, point.size).fill({ color, alpha: point.alpha });
      if (index % 3 === 0) dust.circle(point.x, point.y, point.size * 0.48).fill({ color: 0xf0f9ff, alpha: 0.72 });
      if (index % 6 === 0) {
        const spark = this.light(point.size * 3.2, color, 0.36 * point.alpha);
        spark.position.set(point.x, point.y);
        lights.addChild(spark);
      }
    });
    core.circle(0, 0, node.category === "primary" ? 3.1 : 2.1).fill({ color: 0xeaffff, alpha: 0.92 });
    const label = new Text({ text: node.metadata.title, style: { fontFamily: "Segoe UI, sans-serif", fontSize: 12,
      fill: this.theme === "amber" ? 0xe6d9c2 : this.theme === "violet" ? 0xe0d8ef : 0xd7e2e7 } });
    label.anchor.set(0.5, 0);
    label.position.set(0, radius * 1.3 + 8);
    body.addChild(halo, lights, dust, core);
    root.addChild(body, label);
    root.alpha = 0;
    return { node, root, body, dust, halo, label, energy: 0, opacity: 0, departingAt: null };
  }

  private light(radius: number, color: number, alpha: number): Sprite {
    const sprite = new Sprite(this.lightTexture!);
    sprite.anchor.set(0.5);
    sprite.width = sprite.height = radius * 2;
    sprite.tint = color;
    sprite.alpha = alpha;
    sprite.blendMode = "add";
    return sprite;
  }

  private tick = (): void => {
    const scene = this.scene;
    if (!scene || this.disposed) return;
    const now = performance.now();
    const dt = Math.min(0.1, (now - (this.lastTime || now)) / 1000);
    this.lastTime = now;
    if (!scene.reducedMotion && scene.focused) this.animationTime += dt;
    const t = this.animationTime;
    const easing = 1 - Math.exp(-dt * 7);
    this.camera.x += (this.target.x - this.camera.x) * easing;
    this.camera.y += (this.target.y - this.camera.y) * easing;
    this.camera.scale += (this.target.scale - this.camera.scale) * easing;
    this.world.position.set(this.camera.x, this.camera.y);
    this.world.scale.set(this.camera.scale);
    for (const [id, cluster] of this.clusters) {
      const retiring = cluster.departingAt !== null;
      const targetEnergy = !retiring && ["ready", "degraded"].includes(scene.status) && cluster.node.motion === "active" ? 1 : 0;
      cluster.energy += (targetEnergy - cluster.energy) * easing;
      cluster.opacity += ((retiring ? 0 : 1) - cluster.opacity) * (retiring ? dt * 1.1 : easing);
      if (retiring && now - cluster.departingAt! > 3500) {
        cluster.root.destroy({ children: true }); this.clusters.delete(id); continue;
      }
      const phase = (seedFor(id) % 628) / 100;
      const breath = nebulaBreath(t, cluster.energy, phase, scene.reducedMotion);
      cluster.root.alpha = cluster.opacity * (["ready", "degraded"].includes(scene.status) ? 1 : 0.7);
      cluster.body.scale.set(breath);
      cluster.dust.rotation = scene.reducedMotion ? 0 : Math.sin(t * 0.09 + phase) * 0.028;
      cluster.dust.alpha = 0.88 + cluster.energy * 0.12;
      cluster.halo.alpha = (cluster.node.id === scene.selectedNodeId ? 1 : 0.88)
        * (1 + cluster.energy * 0.22 + (breath - 1) * 2.4);
      cluster.label.alpha = retiring ? 0 : 1;
      cluster.label.scale.set(Math.min(3, 1 / this.camera.scale));
      cluster.label.visible = this.camera.scale >= 0.65 || ["primary", "provider", "aggregate"].includes(cluster.node.category)
        || cluster.node.id === scene.selectedNodeId;
    }
    this.drawConnections(now, dt);
  };

  private drawConnections(now: number, dt: number): void {
    this.wires.clear(); this.pulses.clear();
    const scene = this.scene!;
    for (const [id, connection] of this.connections) {
      if (connection.retiringAt !== null && now - connection.retiringAt > 3500) { this.connections.delete(id); continue; }
      const edge = connection.edge;
      const targetOpacity = connection.retiringAt === null ? (edge.active && ["ready", "degraded"].includes(scene.status) ? 0.7 : 0.42) : 0;
      connection.opacity += (targetOpacity - connection.opacity) * (1 - Math.exp(-dt * 3));
      const source = this.clusters.get(edge.sourceId), target = this.clusters.get(edge.targetId);
      if (!source || !target) continue;
      const a = source.root.position, b = target.root.position;
      const color = identityColor(source.node.id, this.theme);
      const targetColor = identityColor(target.node.id, this.theme);
      const opacity = connection.opacity * Math.min(source.opacity, target.opacity);
      // Bounded layered currents. Static dust is not a fabricated flow event.
      for (let strand = -1; strand <= 1; strand++) {
        this.wires.moveTo(a.x, a.y);
        for (let step = 1; step <= 24; step++) {
          const p = streamPoint(a, b, edge.id, step / 24, strand);
          this.wires.lineTo(p.x, p.y);
        }
        this.wires.stroke({ width: strand === 0 ? 7 : 0.75,
          color: strand === 1 ? targetColor : color, alpha: opacity * (strand === 0 ? 0.15 : 0.85) });
      }
      for (let step = 1; step < 24; step++) {
        const p = streamPoint(a, b, edge.id, step / 24, Math.sin(step * 5) * 2);
        this.wires.circle(p.x, p.y, step % 5 === 0 ? 1.1 : 0.5)
          .fill({ color: step < 12 ? color : targetColor, alpha: opacity * 0.7 });
      }
    }
    for (const [id, flight] of this.flights) {
      const edge = scene.edges.find((candidate) => candidate.id === flight.edgeId);
      const progress = (now - flight.born) / 1500;
      if (!edge || progress > 1.22) { this.flights.delete(id); continue; }
      const source = this.clusters.get(edge.sourceId), target = this.clusters.get(edge.targetId);
      if (!source || !target) continue;
      for (let pulse = 0; pulse < 3; pulse++) {
        const distance = progress - pulse * 0.10;
        if (distance < 0 || distance > 1) continue;
        const point = streamPoint(source.root.position, target.root.position, edge.id, distance);
        const color = identityColor(source.node.id, this.theme);
        this.pulses.circle(point.x, point.y, 5).fill({ color, alpha: 0.09 });
        this.pulses.circle(point.x, point.y, 1.8).fill({ color, alpha: 0.9 - pulse * 0.18 });
      }
    }
  }

  fit = (): void => {
    if (!this.initialized || !this.scene?.nodes.length) return;
    const points = this.scene.nodes.map((node) => this.layout.positions.get(node.id)!).filter(Boolean);
    const left = Math.min(...points.map((p) => p.x)) - 105, right = Math.max(...points.map((p) => p.x)) + 105;
    const top = Math.min(...points.map((p) => p.y)) - 105, bottom = Math.max(...points.map((p) => p.y)) + 120;
    const width = this.host.clientWidth, height = this.host.clientHeight;
    const scale = Math.max(0.15, Math.min(1.35, (width - 100) / (right - left), (height - 140) / (bottom - top)));
    this.target = { scale, x: width / 2 - (left + right) / 2 * scale, y: height / 2 - (top + bottom) / 2 * scale };
  };
  private down = (event: PointerEvent): void => {
    if (event.button !== 0) return;
    this.pointer = { x: event.clientX, y: event.clientY, moved: false, id: event.pointerId };
    this.host.setPointerCapture(event.pointerId); this.host.focus();
  };
  private move = (event: PointerEvent): void => {
    if (!this.pointer) return;
    const dx = event.clientX - this.pointer.x, dy = event.clientY - this.pointer.y;
    if (Math.hypot(dx, dy) < 3 && !this.pointer.moved) return;
    this.pointer.moved = true;
  };
  private up = (event: PointerEvent): void => {
    if (this.pointer && !this.pointer.moved) {
      const rect = this.host.getBoundingClientRect();
      const x = (event.clientX - rect.left - this.camera.x) / this.camera.scale;
      const y = (event.clientY - rect.top - this.camera.y) / this.camera.scale;
      const hit = [...this.clusters.values()].find((cluster) => cluster.departingAt === null
        && Math.hypot(x - cluster.root.x, y - cluster.root.y) < clusterRadius(cluster.node) * 1.15);
      this.select(hit && hit.node.id !== this.scene?.selectedNodeId ? hit.node.id : null);
    }
    this.cancel();
  };
  private cancel = (): void => {
    if (this.pointer && this.host.hasPointerCapture(this.pointer.id)) this.host.releasePointerCapture(this.pointer.id);
    this.pointer = null;
  };
  private key = (event: KeyboardEvent): void => {
    if (event.key === "Escape") this.select(null);
    else return;
    event.preventDefault();
  };
  private visibility = (): void => { if (document.hidden) this.app.stop(); else { this.lastTime = 0; this.app.start(); } };
  destroy(): void {
    this.disposed = true; this.observer?.disconnect();
    this.host.removeEventListener("pointerdown", this.down); this.host.removeEventListener("pointermove", this.move);
    this.host.removeEventListener("pointerup", this.up); this.host.removeEventListener("pointercancel", this.cancel);
    this.host.removeEventListener("keydown", this.key);
    document.removeEventListener("visibilitychange", this.visibility);
    this.flights.clear(); this.clusters.clear(); this.connections.clear();
    if (this.initialized) this.app.destroy(true, { children: true });
    this.lightTexture?.destroy(true);
    this.lightTexture = null;
    this.nebulaTexture?.destroy(true);
    this.nebulaTexture = null;
  }
}
