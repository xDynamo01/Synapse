import { useEffect, useMemo, useRef } from "react";
import type { PresenceSceneState } from "../shared/presenceAdapter.js";
import type { FrontendThemePreference } from "../shared/settingsPreferences.js";

interface PresenceProps {
  scene: PresenceSceneState;
  theme?: FrontendThemePreference;
}

interface Particle {
  angle: number;
  radius: number;
  size: number;
  alpha: number;
  speed: number;
  twinkle: number;
  depth: number;
  trail: number;
}

interface Marker {
  angle: number;
  radius: number;
  size: number;
  speed: number;
  hollow: boolean;
}

const particles = makeParticles(340);
const externalParticles = makeExternalParticles(74);
const markers = makeMarkers();

export function Presence({ scene, theme = "synapse" }: PresenceProps): React.ReactElement {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const sceneRef = useRef(scene);
  useEffect(() => { sceneRef.current = scene; }, [scene]);
  const className = useMemo(() => `presence canvas ${scene.state}`, [scene.state]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return undefined;
    }
    const context = canvas.getContext("2d", { alpha: true });
    if (!context) {
      return undefined;
    }

    let frame = 0;
    let running = true;
    let width = 0;
    let height = 0;
    let deviceScale = 1;
    let envelope = 0;
    let previousTime = 0;

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      deviceScale = Math.min(window.devicePixelRatio || 1, 2);
      width = Math.max(1, Math.floor(rect.width));
      height = Math.max(1, Math.floor(rect.height));
      canvas.width = Math.floor(width * deviceScale);
      canvas.height = Math.floor(height * deviceScale);
      context.setTransform(deviceScale, 0, 0, deviceScale, 0, 0);
    };

    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(canvas);
    resize();

    const render = (timestamp: number) => {
      if (!running) {
        return;
      }
      const current = sceneRef.current;
      const elapsed = Math.min(0.1, (timestamp - previousTime) / 1000);
      previousTime = timestamp;
      const target = current.state === "speaking" ? current.amplitude : 0;
      // Fast attack and softer release follow syllables without jumping at each UI update.
      envelope += (target - envelope) * (1 - Math.exp(-elapsed / (target > envelope ? 0.035 : 0.14)));
      drawPresence(context, width, height, timestamp / 1000, { ...current, amplitude: envelope }, canvas);
      frame = requestAnimationFrame(render);
    };
    frame = requestAnimationFrame(render);

    return () => {
      running = false;
      cancelAnimationFrame(frame);
      resizeObserver.disconnect();
    };
  }, []);

  return (
    <section className={className} aria-label={scene.label} data-theme={theme}>
      <canvas ref={canvasRef} className="presence-canvas" aria-hidden="true" />
      <p className="presence-accessible-state">{scene.label}</p>
    </section>
  );
}

function drawPresence(
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
  time: number,
  scene: PresenceSceneState,
  canvas: HTMLCanvasElement
): void {
  const size = Math.min(width, height);
  const centerX = width / 2;
  const centerY = height / 2 - size * 0.035;
  const amplitude = Math.max(0, Math.min(scene.amplitude ?? 0, 1));
  const radius = size * 0.44 * (1 + amplitude * 0.045);
  const energy = scene.state === "speaking" ? 0.95 + amplitude * 1.1 : scene.state === "processing" || scene.state === "listening" ? 1.12 : 0.82;
  const palette = paletteFromCanvas(canvas);

  context.clearRect(0, 0, width, height);
  context.globalCompositeOperation = "lighter";

  glow(context, centerX, centerY, radius * 0.68, palette.primary, 0.055 * energy);
  drawExternalParticles(context, centerX, centerY, radius, time, palette);
  drawOuterOrbits(context, centerX, centerY, radius, time, palette, energy);
  drawInternalField(context, centerX, centerY, radius, time, palette, energy, amplitude);
  drawTechnicalRing(context, centerX, centerY, radius * 0.36, time, palette, energy, amplitude);
  drawCore(context, centerX, centerY, radius, time, palette, energy, amplitude);
  drawSynapseFires(context, centerX, centerY, radius, time, palette, energy);
  drawMarkers(context, centerX, centerY, radius, time, palette);

  context.globalCompositeOperation = "source-over";
}

function drawCore(
  context: CanvasRenderingContext2D,
  centerX: number,
  centerY: number,
  radius: number,
  time: number,
  palette: ReturnType<typeof paletteFromCanvas>,
  energy: number,
  amplitude: number
): void {
  const breathe = 1 + Math.sin(time * 1.3) * 0.018 + amplitude * 0.65;
  glow(context, centerX, centerY, radius * 0.018, palette.white, 1);
  glow(context, centerX, centerY, radius * 0.05 * breathe, palette.bright, 0.72 * energy);
  glow(context, centerX, centerY, radius * 0.105 * breathe, palette.primary, 0.34 * energy);
  glow(context, centerX, centerY, radius * 0.19 * breathe, palette.primary, 0.12 * energy);
}

function drawInternalField(
  context: CanvasRenderingContext2D,
  centerX: number,
  centerY: number,
  radius: number,
  time: number,
  palette: ReturnType<typeof paletteFromCanvas>,
  energy: number,
  amplitude: number
): void {
  for (const particle of particles) {
    const drift = time * particle.speed * (0.55 + particle.depth * 0.55);
    const wobble = Math.sin(time * 0.7 + particle.twinkle) * radius * 0.006 * particle.depth;
    const angle = particle.angle + drift;
    const distance = radius * particle.radius + wobble;
    const x = centerX + Math.cos(angle) * distance * (1 + particle.depth * 0.025);
    const y = centerY + Math.sin(angle) * distance * (0.92 + particle.depth * 0.03);
    const twinkle = 0.62 + Math.sin(time * (1.1 + particle.depth * 1.7) + particle.twinkle) * 0.38;
    const alpha = particle.alpha * twinkle * energy * (1 + amplitude * 0.45);
    const size = particle.size * (0.86 + particle.depth * 0.42);
    if (particle.trail > 0.58) {
      const tangent = angle + Math.PI / 2;
      context.beginPath();
      context.strokeStyle = rgba(palette.primary, alpha * 0.42);
      context.lineWidth = Math.max(0.45, size * 0.42);
      context.moveTo(x - Math.cos(tangent) * particle.trail * 6, y - Math.sin(tangent) * particle.trail * 6);
      context.lineTo(x + Math.cos(tangent) * particle.trail * 4, y + Math.sin(tangent) * particle.trail * 4);
      context.stroke();
    }
    dot(context, x, y, size, particle.depth > 0.78 ? palette.bright : palette.primary, alpha);
  }
}

function drawTechnicalRing(
  context: CanvasRenderingContext2D,
  centerX: number,
  centerY: number,
  ringRadius: number,
  time: number,
  palette: ReturnType<typeof paletteFromCanvas>,
  energy: number,
  amplitude: number
): void {
  ring(context, centerX, centerY, ringRadius * 0.82, 0, Math.PI * 2, palette.primary, 0.34, 0.7);
  ring(context, centerX, centerY, ringRadius * 1.14, 0, Math.PI * 2, palette.primary, 0.42, 0.9);
  ring(context, centerX, centerY, ringRadius * 1.28, Math.PI * 0.16 + time * 0.08, Math.PI * 1.55 + time * 0.08, palette.bright, 0.28, 1);
  const tickCount = 136;
  for (let index = 0; index < tickCount; index += 1) {
    const angle = (index / tickCount) * Math.PI * 2 + time * 0.17;
    const variance = 0.72 + ((index * 37) % 17) / 56;
    const inner = ringRadius * (0.94 + variance * 0.015);
    const outer = ringRadius * (1.08 + variance * 0.04 + amplitude * (0.15 + variance * 0.28));
    context.beginPath();
    context.strokeStyle = rgba(index % 9 === 0 ? palette.bright : palette.primary, 0.52 * variance * energy);
    context.lineWidth = index % 11 === 0 ? 1.55 : 1.05;
    context.moveTo(centerX + Math.cos(angle) * inner, centerY + Math.sin(angle) * inner);
    context.lineTo(centerX + Math.cos(angle) * outer, centerY + Math.sin(angle) * outer);
    context.stroke();
  }
  for (let index = 0; index < 44; index += 1) {
    const angle = (index / 44) * Math.PI * 2 - time * 0.11;
    const r = ringRadius * (1.24 + ((index * 19) % 9) * 0.01);
    dot(context, centerX + Math.cos(angle) * r, centerY + Math.sin(angle) * r, 1, palette.primary, 0.46, 5);
  }
}

function drawOuterOrbits(
  context: CanvasRenderingContext2D,
  centerX: number,
  centerY: number,
  radius: number,
  time: number,
  palette: ReturnType<typeof paletteFromCanvas>,
  energy: number
): void {
  const arcs = [
    [0.48, 0.2, 1.62, 0.16, 0.7, -2, 3],
    [0.55, 2.35, 4.42, -0.08, 0.42, 6, -4],
    [0.62, -0.42, 0.95, 0.06, 0.72, -8, -2],
    [0.67, 1.12, 2.78, -0.04, 0.36, 3, 8],
    [0.74, 3.08, 4.85, 0.025, 0.44, -7, 7],
    [0.82, -0.1, 1.02, -0.035, 0.6, 9, -7],
    [0.88, 2.62, 5.06, 0.02, 0.5, -3, 1],
    [0.98, 0.72, 2.1, -0.018, 0.34, 10, 4],
    [1.04, 3.44, 5.55, 0.012, 0.42, -11, -9]
  ];
  for (const [scale, start, end, speed, alpha, dx, dy] of arcs) {
    ring(
      context,
      centerX + dx,
      centerY + dy,
      radius * scale,
      start + time * speed,
      end + time * speed,
      palette.primary,
      alpha * energy * 1.55,
      scale > 0.8 ? 0.9 : 0.7
    );
  }
}

function drawExternalParticles(
  context: CanvasRenderingContext2D,
  centerX: number,
  centerY: number,
  radius: number,
  time: number,
  palette: ReturnType<typeof paletteFromCanvas>
): void {
  for (const particle of externalParticles) {
    const angle = particle.angle + time * particle.speed;
    const x = centerX + Math.cos(angle) * radius * particle.radius;
    const y = centerY + Math.sin(angle) * radius * particle.radius * 0.9;
    const alpha = particle.alpha * (0.52 + Math.sin(time * 0.8 + particle.twinkle) * 0.24);
    dot(context, x, y, particle.size, particle.depth > 0.7 ? palette.bright : palette.primary, alpha);
  }
}

function drawSynapseFires(
  context: CanvasRenderingContext2D,
  centerX: number,
  centerY: number,
  radius: number,
  time: number,
  palette: ReturnType<typeof paletteFromCanvas>,
  energy: number
): void {
  const fires = [
    [0.16, 0.22, 0.44, 0],
    [1.2, 0.15, 0.34, 0.7],
    [2.6, 0.18, 0.38, 1.3],
    [4.9, 0.14, 0.32, 2.1],
    [5.7, 0.12, 0.27, 2.8]
  ];
  for (const [angle, from, to, delay] of fires) {
    const pulse = Math.max(0, Math.sin((time * 1.45 + delay) * Math.PI));
    if (pulse < 0.68) {
      continue;
    }
    context.beginPath();
    context.strokeStyle = rgba(palette.bright, (pulse - 0.64) * 0.95 * energy);
    context.lineWidth = 0.8;
    context.moveTo(centerX + Math.cos(angle) * radius * from, centerY + Math.sin(angle) * radius * from);
    context.lineTo(centerX + Math.cos(angle) * radius * to, centerY + Math.sin(angle) * radius * to);
    context.stroke();
  }
}

function drawMarkers(
  context: CanvasRenderingContext2D,
  centerX: number,
  centerY: number,
  radius: number,
  time: number,
  palette: ReturnType<typeof paletteFromCanvas>
): void {
  for (const marker of markers) {
    const angle = marker.angle + time * marker.speed;
    const x = centerX + Math.cos(angle) * radius * marker.radius;
    const y = centerY + Math.sin(angle) * radius * marker.radius * 0.94;
    if (marker.hollow) {
      context.beginPath();
      context.strokeStyle = rgba(palette.bright, 0.72);
      context.lineWidth = 1.1;
      context.arc(x, y, marker.size, 0, Math.PI * 2);
      context.stroke();
      continue;
    }
    dot(context, x, y, marker.size, palette.bright, 0.8);
  }
}

function ring(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  radius: number,
  start: number,
  end: number,
  color: Rgb,
  alpha: number,
  width: number
): void {
  context.beginPath();
  context.strokeStyle = rgba(color, alpha);
  context.lineWidth = width;
  context.shadowColor = rgba(color, Math.min(alpha * 0.9, 0.8));
  context.shadowBlur = alpha > 0.35 ? 8 : 3;
  context.arc(x, y, radius, start, end);
  context.stroke();
  context.shadowBlur = 0;
}

function dot(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  radius: number,
  color: Rgb,
  alpha: number,
  shadow = alpha > 0.42 ? 7 : 0
): void {
  context.beginPath();
  context.fillStyle = rgba(color, alpha);
  context.shadowColor = rgba(color, Math.min(alpha, 0.82));
  context.shadowBlur = shadow;
  context.arc(x, y, radius, 0, Math.PI * 2);
  context.fill();
  context.shadowBlur = 0;
}

function glow(context: CanvasRenderingContext2D, x: number, y: number, radius: number, color: Rgb, alpha: number): void {
  const gradient = context.createRadialGradient(x, y, 0, x, y, radius);
  gradient.addColorStop(0, rgba(color, alpha));
  gradient.addColorStop(0.42, rgba(color, alpha * 0.38));
  gradient.addColorStop(1, rgba(color, 0));
  context.fillStyle = gradient;
  context.beginPath();
  context.arc(x, y, radius, 0, Math.PI * 2);
  context.fill();
}

function makeParticles(count: number): Particle[] {
  return Array.from({ length: count }, (_, index) => {
    const random = seeded(index + 11);
    const cluster = random();
    const radius = 0.035 + Math.pow(random(), 1.7) * 0.5 + (cluster > 0.82 ? random() * 0.1 : 0);
    return {
      angle: random() * Math.PI * 2 + Math.sin(index) * 0.28,
      radius,
      size: 0.55 + Math.pow(random(), 2.5) * 2.9,
      alpha: 0.32 + random() * 0.68,
      speed: (random() > 0.46 ? 1 : -1) * (0.025 + random() * 0.095),
      twinkle: random() * Math.PI * 2,
      depth: random(),
      trail: random()
    };
  });
}

function makeExternalParticles(count: number): Particle[] {
  return Array.from({ length: count }, (_, index) => {
    const random = seeded(index + 991);
    return {
      angle: random() * Math.PI * 2,
      radius: 0.64 + random() * 0.5,
      size: 0.55 + random() * 1.9,
      alpha: 0.11 + random() * 0.34,
      speed: (random() > 0.5 ? 1 : -1) * (0.005 + random() * 0.02),
      twinkle: random() * Math.PI * 2,
      depth: random(),
      trail: 0
    };
  });
}

function makeMarkers(): Marker[] {
  return [
    { angle: 0.24, radius: 0.76, size: 2.8, speed: 0.035, hollow: false },
    { angle: 1.12, radius: 0.88, size: 5.8, speed: -0.018, hollow: true },
    { angle: 2.52, radius: 0.66, size: 2.3, speed: 0.026, hollow: false },
    { angle: 3.54, radius: 0.98, size: 7.4, speed: -0.012, hollow: true },
    { angle: 4.34, radius: 0.57, size: 1.9, speed: 0.04, hollow: false },
    { angle: 5.42, radius: 0.92, size: 2.5, speed: 0.016, hollow: false }
  ];
}

function seeded(seed: number): () => number {
  let value = seed;
  return () => {
    value = (value * 1664525 + 1013904223) % 4294967296;
    return value / 4294967296;
  };
}

interface Rgb {
  r: number;
  g: number;
  b: number;
}

function paletteFromCanvas(canvas: HTMLCanvasElement): { primary: Rgb; bright: Rgb; white: Rgb } {
  const styles = getComputedStyle(canvas);
  const primary = parseColor(styles.color) ?? { r: 0, g: 245, b: 230 };
  return {
    primary,
    bright: mix(primary, { r: 217, g: 251, b: 255 }, 0.36),
    white: { r: 244, g: 255, b: 255 }
  };
}

function parseColor(value: string): Rgb | null {
  const match = value.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
  if (!match) {
    return null;
  }
  return { r: Number(match[1]), g: Number(match[2]), b: Number(match[3]) };
}

function mix(a: Rgb, b: Rgb, amount: number): Rgb {
  return {
    r: Math.round(a.r + (b.r - a.r) * amount),
    g: Math.round(a.g + (b.g - a.g) * amount),
    b: Math.round(a.b + (b.b - a.b) * amount)
  };
}

function rgba(color: Rgb, alpha: number): string {
  return `rgba(${color.r}, ${color.g}, ${color.b}, ${Math.max(0, Math.min(alpha, 1))})`;
}
