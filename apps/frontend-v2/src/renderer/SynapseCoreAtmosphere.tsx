import { useEffect, useRef } from "react";
import workshopBackground from "../../assets/media/backgrounds/synapse-inventor-workshop.jpg";

interface SynapseCoreAtmosphereProps {
  active: boolean;
  reducedMotion: boolean;
  focused: boolean;
  state: string;
  amplitude: number;
}

interface Plane {
  x: number;
  y: number;
  width: number;
  height: number;
  depth: number;
  phase: number;
  drift: number;
}

interface Route {
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
  bend: number;
  phase: number;
  speed: number;
  signal: boolean;
}

interface DataNode {
  x: number;
  y: number;
  phase: number;
  size: number;
  signal: boolean;
}

type ScreenEffectKind = "code" | "telemetry" | "cad";
interface ScreenRegion {
  id: string;
  kind: ScreenEffectKind;
  points: readonly [number, number][];
}

const workshopScreens: readonly ScreenRegion[] = [
  { id: "right-code", kind: "code", points: [[0.695, 0.174], [0.768, 0.175], [0.766, 0.244], [0.694, 0.243]] },
  { id: "right-cad", kind: "cad", points: [[0.779, 0.181], [0.892, 0.183], [0.885, 0.338], [0.777, 0.329]] },
  { id: "far-monitor", kind: "telemetry", points: [[0.906, 0.181], [0.982, 0.188], [0.978, 0.266], [0.902, 0.254]] },
  { id: "lower-code", kind: "code", points: [[0.692, 0.264], [0.765, 0.266], [0.762, 0.326], [0.689, 0.324]] },
  { id: "lower-cad", kind: "cad", points: [[0.900, 0.277], [0.979, 0.291], [0.975, 0.370], [0.895, 0.352]] },
  { id: "desk-monitor", kind: "code", points: [[0.738, 0.355], [0.793, 0.361], [0.790, 0.409], [0.736, 0.403]] },
  { id: "desk-diagram", kind: "telemetry", points: [[0.806, 0.365], [0.858, 0.375], [0.855, 0.421], [0.802, 0.411]] },
  { id: "desk-right", kind: "code", points: [[0.908, 0.389], [0.960, 0.403], [0.955, 0.454], [0.903, 0.439]] }
];

const cyan = [84, 255, 244] as const;
const ice = [210, 249, 255] as const;
const amber = [255, 209, 102] as const;

function seededRandom(seed: number): () => number {
  let value = seed >>> 0;
  return () => {
    value = (Math.imul(value, 1664525) + 1013904223) >>> 0;
    return value / 4294967296;
  };
}

function makePlanes(random: () => number): Plane[] {
  return Array.from({ length: 16 }, (_, index) => ({
    x: 0.15 + random() * 0.7,
    y: 0.12 + random() * 0.67,
    width: 0.12 + random() * 0.18,
    height: 0.055 + random() * 0.13,
    depth: 0.42 + random() * 0.75,
    phase: random() * Math.PI * 2,
    drift: (index % 2 === 0 ? 1 : -1) * (0.0015 + random() * 0.003)
  }));
}

function makeRoutes(random: () => number): Route[] {
  return Array.from({ length: 24 }, (_, index) => {
    const fromLeft = index % 2 === 0;
    return {
      fromX: fromLeft ? 0.08 + random() * 0.2 : 0.72 + random() * 0.2,
      fromY: 0.14 + random() * 0.7,
      toX: 0.43 + random() * 0.14,
      toY: 0.27 + random() * 0.45,
      bend: (random() - 0.5) * 0.22,
      phase: random(),
      speed: 0.035 + random() * 0.08,
      signal: index % 6 === 0
    };
  });
}

function makeNodes(random: () => number): DataNode[] {
  return Array.from({ length: 78 }, (_, index) => ({
    x: 0.12 + random() * 0.76,
    y: 0.1 + random() * 0.72,
    phase: random() * Math.PI * 2,
    size: 0.65 + random() * 1.4,
    signal: index % 13 === 0
  }));
}

function rgba(color: readonly [number, number, number], alpha: number): string {
  return `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${Math.max(0, Math.min(1, alpha))})`;
}

function coverTransform(width: number, height: number): { scale: number; offsetX: number; offsetY: number } {
  const scale = Math.max(width / 2752, height / 1536);
  return { scale, offsetX: (width - 2752 * scale) / 2, offsetY: (height - 1536 * scale) / 2 };
}

function screenPoint(point: readonly [number, number], transform: { scale: number; offsetX: number; offsetY: number }): [number, number] {
  return [transform.offsetX + point[0] * 2752 * transform.scale, transform.offsetY + point[1] * 1536 * transform.scale];
}

function drawWorkshopScreenEffects(context: CanvasRenderingContext2D, width: number, height: number, time: number, reducedMotion: boolean): void {
  context.clearRect(0, 0, width, height);
  const transform = coverTransform(width, height);
  drawWorkshopLeftEffects(context, transform, reducedMotion ? 0 : time);
  if (!reducedMotion) drawWorkshopRobotEffects(context, transform, time);
  for (const screen of workshopScreens) {
    const points = screen.points.map((point) => screenPoint(point, transform));
    context.save();
    context.beginPath();
    points.forEach(([x, y], index) => index === 0 ? context.moveTo(x, y) : context.lineTo(x, y));
    context.closePath();
    context.clip();
    const left = Math.min(...points.map(([x]) => x));
    const right = Math.max(...points.map(([x]) => x));
    const top = Math.min(...points.map(([, y]) => y));
    const bottom = Math.max(...points.map(([, y]) => y));
    const screenWidth = right - left;
    const screenHeight = bottom - top;
    const phase = reducedMotion ? 0 : time;
    context.fillStyle = "rgba(3, 20, 27, 0.65)";
    context.fillRect(left, top, screenWidth, screenHeight);
    context.strokeStyle = "rgba(153, 218, 227, 0.85)";
    context.lineWidth = Math.max(0.7, width / 1900);
    if (screen.kind === "code") {
      const lines = ["// WORKSHOP SIM", "const drone = {", "  rotor: [1, 2, 3, 4],", "  axis: vector(x,y,z)", "};", "render(drone);", "// DECORATIVE LOOP", "update(view);"];
      const spacing = screenHeight / 7;
      const cycle = spacing * lines.length;
      context.font = `${Math.max(3, screenWidth * 0.055)}px monospace`;
      context.fillStyle = "rgba(171, 222, 226, 0.9)";
      for (let line = 0; line < lines.length; line += 1) {
        const y = ((line * spacing + phase * screenHeight / 10) % cycle) - spacing;
        context.fillText(lines[line], left + screenWidth * 0.06, top + y, screenWidth * 0.88);
      }
    } else if (screen.kind === "cad") {
      const cx = left + screenWidth * 0.5;
      const cy = top + screenHeight * 0.52;
      context.translate(cx, cy);
      context.strokeRect(-screenWidth * 0.08, -screenHeight * 0.10, screenWidth * 0.16, screenHeight * 0.20);
      for (const dx of [-1, 1]) for (const dy of [-1, 1]) {
        const x = dx * screenWidth * 0.25;
        const y = dy * screenHeight * 0.22;
        context.beginPath(); context.moveTo(0, 0); context.lineTo(x, y); context.stroke();
        context.beginPath(); context.ellipse(x, y, screenWidth * 0.09, screenHeight * 0.07, 0, 0, Math.PI * 2); context.stroke();
      }
      context.beginPath();
      context.moveTo(-screenWidth * 0.36, 0);
      context.lineTo(screenWidth * 0.36, 0);
      context.moveTo(0, -screenHeight * 0.3);
      context.lineTo(0, screenHeight * 0.3);
      context.stroke();
      // Stationary drone with decorative diagnostic probes; no real telemetry.
      for (let probe = 0; probe < 4; probe += 1) {
        const x = (probe % 2 === 0 ? -1 : 1) * screenWidth * 0.25;
        const y = (probe < 2 ? -1 : 1) * screenHeight * 0.22;
        const intensity = 0.25 + 0.55 * (0.5 + 0.5 * Math.sin(phase * 1.3 - probe * Math.PI / 2));
        context.fillStyle = `rgba(255, 191, 91, ${intensity})`;
        context.beginPath();
        context.arc(x, y, Math.max(1, screenWidth * 0.018), 0, Math.PI * 2);
        context.fill();
        context.fillRect(-screenWidth * 0.35 + probe * screenWidth * 0.19, screenHeight * 0.36, screenWidth * 0.13 * intensity, Math.max(1, screenHeight * 0.018));
      }
    } else {
      context.beginPath();
      for (let index = 0; index < 12; index += 1) {
        const x = left + index * screenWidth / 11;
        const y = top + screenHeight * (0.54 + Math.sin(phase * 0.8 + index * 0.9) * 0.2);
        index === 0 ? context.moveTo(x, y) : context.lineTo(x, y);
      }
      context.stroke();
      context.fillStyle = "rgba(255, 209, 102, 0.5)";
      context.beginPath();
      context.arc(left + screenWidth * (0.5 + Math.sin(phase * 0.35) * 0.35), top + screenHeight * 0.24, Math.max(1.2, width / 900), 0, Math.PI * 2);
      context.fill();
    }
    context.restore();
  }
}

// Decorative light only: coordinates share the photograph's cover transform.
function drawWorkshopLeftEffects(
  context: CanvasRenderingContext2D,
  transform: ReturnType<typeof coverTransform>,
  time: number
): void {
  context.save();
  context.translate(transform.offsetX, transform.offsetY);
  context.scale(transform.scale, transform.scale);
  context.globalCompositeOperation = "screen";
  context.save();
  // Inside the open engine bay; keep the hood and bodywork untouched.
  context.beginPath();
  context.moveTo(0.257 * 2752, 0.451 * 1536);
  context.lineTo(0.345 * 2752, 0.438 * 1536);
  context.lineTo(0.399 * 2752, 0.500 * 1536);
  context.lineTo(0.296 * 2752, 0.533 * 1536);
  context.closePath();
  context.clip();
  const pulse = 0.5 + 0.5 * Math.sin(time * Math.PI * 2 / 8);
  const glow = context.createRadialGradient(900, 747, 3, 900, 747, 145);
  glow.addColorStop(0, `rgba(255, 181, 65, ${0.16 + pulse * 0.19})`);
  glow.addColorStop(0.5, `rgba(226, 89, 30, ${0.05 + pulse * 0.08})`);
  glow.addColorStop(1, "rgba(226, 89, 30, 0)");
  context.fillStyle = glow;
  context.fillRect(700, 640, 440, 220);
  context.restore();
  // Warm underbody light falls on the floor below the front bumper.
  const carLight = 0.86 + 0.14 * Math.sin(time * Math.PI * 2 / 10);
  context.save();
  context.translate(0.323 * 2752, 0.644 * 1536);
  context.rotate(-0.13);
  context.scale(235, 30);
  const underglow = context.createRadialGradient(0, 0, 0, 0, 0, 1);
  underglow.addColorStop(0, `rgba(255, 170, 52, ${carLight * 0.35})`);
  underglow.addColorStop(0.45, `rgba(245, 105, 25, ${carLight * 0.18})`);
  underglow.addColorStop(1, "rgba(245, 105, 25, 0)");
  context.fillStyle = underglow;
  context.fillRect(-1, -1, 2, 2);
  context.restore();
  // Light is clipped to the existing raised headlamp faces.
  const lamps = [
    [[0.309, 0.524], [0.330, 0.519], [0.331, 0.536], [0.310, 0.542]],
    [[0.384, 0.491], [0.400, 0.484], [0.402, 0.501], [0.386, 0.508]]
  ];
  for (const lamp of lamps) {
    context.save();
    context.beginPath();
    lamp.forEach(([x, y], index) => index === 0 ? context.moveTo(x * 2752, y * 1536) : context.lineTo(x * 2752, y * 1536));
    context.closePath();
    context.clip();
    const x = (lamp[0][0] + lamp[2][0]) / 2 * 2752;
    const y = (lamp[0][1] + lamp[2][1]) / 2 * 1536;
    const light = context.createRadialGradient(x, y, 0, x, y, 36);
    light.addColorStop(0, `rgba(255, 231, 180, ${carLight * 0.72})`);
    light.addColorStop(1, "rgba(255, 180, 75, 0)");
    context.fillStyle = light;
    context.fillRect(x - 40, y - 40, 80, 80);
    context.restore();
  }
  // Dust follows slow periodic paths beneath the left overhead lamp.
  // Opacity reaches zero at each wrap, so particles never visibly teleport.
  for (let index = 0; index < 26; index += 1) {
    const progress = (time / (19 + index % 7) + index * 0.61803398875) % 1;
    const opacity = Math.sin(progress * Math.PI) ** 2 * 0.38;
    const x = 360 + ((index * 83) % 380) + Math.sin(progress * Math.PI * 2 + index) * 12;
    const y = 170 + progress * 340;
    context.fillStyle = `rgba(218, 226, 218, ${opacity})`;
    context.beginPath();
    context.arc(x, y, 0.8 + (index % 3) * 0.4, 0, Math.PI * 2);
    context.fill();
  }
  context.restore();
}

function drawWorkshopRobotEffects(
  context: CanvasRenderingContext2D,
  transform: ReturnType<typeof coverTransform>,
  time: number
): void {
  context.save();
  context.translate(transform.offsetX, transform.offsetY);
  context.scale(transform.scale, transform.scale);
  context.globalCompositeOperation = "screen";
  // One gentle red eye pulse every twelve seconds, with smooth dark endpoints.
  const cycle = time % 12;
  const pulse = cycle < 2.4 ? Math.sin(cycle / 2.4 * Math.PI) ** 2 : 0;
  for (const [x, y] of [[0.5586 * 2752, 0.2246 * 1536], [0.5660 * 2752, 0.2250 * 1536]]) {
    const glow = context.createRadialGradient(x, y, 0, x, y, 12);
    glow.addColorStop(0, `rgba(255, 43, 28, ${pulse * 0.95})`);
    glow.addColorStop(0.3, `rgba(235, 15, 12, ${pulse * 0.6})`);
    glow.addColorStop(1, "rgba(220, 8, 5, 0)");
    context.fillStyle = glow;
    context.fillRect(x - 12, y - 12, 24, 24);
  }
  // Small intermittent sparks from the exposed side joint, falling and fading.
  // The robot photograph itself stays completely stationary.
  for (let index = 0; index < 7; index += 1) {
    const age = cycle - 2.8 - index * 0.11;
    if (age < 0 || age > 1.7) continue;
    const originX = 0.568 * 2752;
    const originY = 0.329 * 1536;
    const velocityX = (index % 2 ? 1 : -1) * (8 + index * 3);
    const x = originX + velocityX * age;
    const y = originY - 16 * age + 80 * age * age;
    const alpha = Math.min(1, age * 12) * (1 - age / 1.7);
    context.strokeStyle = `rgba(255, 173, 67, ${alpha * 0.8})`;
    context.lineWidth = 1.3;
    context.beginPath();
    context.moveTo(x, y);
    context.lineTo(x - velocityX * 0.025, y - Math.max(2, age * 5));
    context.stroke();
  }
  context.restore();
}

function cubicPoint(
  fromX: number,
  fromY: number,
  controlX: number,
  controlY: number,
  toX: number,
  toY: number,
  t: number
): [number, number] {
  const inverse = 1 - t;
  const x = inverse * inverse * fromX + 2 * inverse * t * controlX + t * t * toX;
  const y = inverse * inverse * fromY + 2 * inverse * t * controlY + t * t * toY;
  return [x, y];
}

function drawAtmosphere(
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
  time: number,
  energy: number,
  amplitude: number,
  planes: Plane[],
  routes: Route[],
  nodes: DataNode[]
): void {
  context.clearRect(0, 0, width, height);
  context.save();
  context.globalCompositeOperation = "lighter";

  const centerX = width * 0.5;
  const centerY = height * 0.43;
  const verticalGlow = context.createLinearGradient(0, height * 0.05, 0, height * 0.84);
  verticalGlow.addColorStop(0, rgba(cyan, 0));
  verticalGlow.addColorStop(0.45, rgba(cyan, 0.21 * energy));
  verticalGlow.addColorStop(1, rgba(cyan, 0));
  context.fillStyle = verticalGlow;
  context.fillRect(centerX - width * 0.09, 0, width * 0.18, height);

  for (let membrane = -2; membrane <= 2; membrane += 1) {
    const phase = time * (0.09 + Math.abs(membrane) * 0.012) + membrane;
    const membraneX = centerX + membrane * width * 0.055 + Math.sin(phase) * width * 0.008;
    const membraneWidth = width * (0.018 + (2 - Math.abs(membrane)) * 0.01);
    const membraneGradient = context.createLinearGradient(0, height * 0.12, 0, height * 0.82);
    membraneGradient.addColorStop(0, rgba(cyan, 0));
    membraneGradient.addColorStop(0.48, rgba(membrane === 1 ? amber : cyan, (membrane === 1 ? 0.065 : 0.095) * energy));
    membraneGradient.addColorStop(1, rgba(cyan, 0));
    context.fillStyle = membraneGradient;
    context.fillRect(membraneX - membraneWidth / 2, height * 0.08, membraneWidth, height * 0.78);
  }

  for (let index = 0; index < 13; index += 1) {
    const ratio = index / 12;
    const offset = (ratio - 0.5) * width * 0.28;
    const phase = time * (0.13 + (index % 3) * 0.025) + index * 0.71;
    const alpha = 0.055 + (0.5 + Math.sin(phase) * 0.5) * 0.14 * energy;
    context.strokeStyle = rgba(index % 4 === 0 ? ice : cyan, alpha);
    context.lineWidth = index % 4 === 0 ? 1.15 : 0.65;
    context.shadowColor = rgba(cyan, alpha * 1.8);
    context.shadowBlur = index % 4 === 0 ? 8 : 3;
    context.beginPath();
    context.moveTo(centerX + offset, height * (0.06 + (index % 4) * 0.018));
    context.lineTo(centerX + offset * 0.37, centerY);
    context.lineTo(centerX + offset * 0.72, height * 0.86);
    context.stroke();
  }

  const nexusGlow = context.createRadialGradient(centerX, centerY, 0, centerX, centerY, width * 0.12);
  nexusGlow.addColorStop(0, rgba(ice, 0.2 * energy));
  nexusGlow.addColorStop(0.28, rgba(cyan, 0.13 * energy));
  nexusGlow.addColorStop(1, rgba(cyan, 0));
  context.fillStyle = nexusGlow;
  context.fillRect(centerX - width * 0.12, centerY - width * 0.12, width * 0.24, width * 0.24);

  for (let stream = 0; stream < 12; stream += 1) {
    const side = stream % 2 === 0 ? -1 : 1;
    const lane = Math.floor(stream / 2);
    const startX = centerX + side * width * (0.035 + lane * 0.045);
    const startY = height * (0.05 + (stream % 3) * 0.018);
    const endX = centerX + side * width * (0.16 + lane * 0.045);
    const endY = height * (0.7 + (stream % 3) * 0.045);
    const color = stream % 5 === 0 ? amber : stream % 3 === 0 ? ice : cyan;
    const pulse = 0.65 + Math.sin(time * (0.34 + lane * 0.025) + stream) * 0.35;
    context.strokeStyle = rgba(color, (0.11 + pulse * 0.1) * energy);
    context.lineWidth = stream % 3 === 0 ? 1.35 : 0.8;
    context.shadowColor = rgba(color, 0.42 * energy);
    context.shadowBlur = stream % 3 === 0 ? 13 : 7;
    context.beginPath();
    context.moveTo(startX, startY);
    context.bezierCurveTo(
      startX - side * width * 0.08,
      centerY - height * 0.18,
      centerX + side * width * 0.035,
      centerY - height * 0.04,
      centerX,
      centerY
    );
    context.bezierCurveTo(
      centerX + side * width * 0.045,
      centerY + height * 0.08,
      endX - side * width * 0.08,
      endY - height * 0.16,
      endX,
      endY
    );
    context.stroke();
  }

  const deckLevels = [-0.31, -0.17, 0.02, 0.21, 0.37];
  for (let deck = 0; deck < deckLevels.length; deck += 1) {
    const level = deckLevels[deck];
    const float = Math.sin(time * (0.16 + deck * 0.018) + deck) * height * 0.008;
    const deckY = centerY + level * height + float;
    const deckWidth = width * (0.19 + (deck % 3) * 0.045);
    const deckHeight = height * (0.035 + (deck % 2) * 0.012);
    const skew = deckWidth * 0.14;
    const deckColor = deck === 3 ? amber : deck % 2 === 0 ? ice : cyan;
    context.fillStyle = rgba(deckColor, (deck === 3 ? 0.018 : 0.026) * energy);
    context.strokeStyle = rgba(deckColor, (deck === 3 ? 0.34 : 0.27) * energy);
    context.lineWidth = deck === 2 ? 1.2 : 0.8;
    context.shadowColor = rgba(deckColor, 0.28 * energy);
    context.shadowBlur = deck === 2 ? 11 : 6;
    context.beginPath();
    context.moveTo(centerX - deckWidth / 2 + skew, deckY - deckHeight / 2);
    context.lineTo(centerX + deckWidth / 2, deckY - deckHeight / 2);
    context.lineTo(centerX + deckWidth / 2 - skew, deckY + deckHeight / 2);
    context.lineTo(centerX - deckWidth / 2, deckY + deckHeight / 2);
    context.closePath();
    context.fill();
    context.stroke();
    for (let column = 1; column < 8; column += 1) {
      const ratio = column / 8;
      const dotX = centerX - deckWidth / 2 + skew + ratio * (deckWidth - skew * 1.8);
      const dotY = deckY + Math.sin(column * 1.9 + deck) * deckHeight * 0.13;
      context.fillStyle = rgba(deckColor, (0.16 + ((column + deck) % 3) * 0.09) * energy);
      context.fillRect(dotX, dotY, 1.1, 1.1);
    }
  }

  for (const [planeIndex, plane] of planes.entries()) {
    const float = Math.sin(time * 0.18 + plane.phase) * height * 0.006;
    const x = (plane.x + Math.sin(time * plane.drift + plane.phase) * 0.008) * width;
    const y = plane.y * height + float;
    const planeWidth = plane.width * width / plane.depth;
    const planeHeight = plane.height * height / plane.depth;
    const skew = planeWidth * 0.17;
    const alpha = (0.105 + (1.15 - plane.depth) * 0.145) * energy;
    const planeColor = planeIndex % 4 === 0 ? ice : cyan;
    context.strokeStyle = rgba(planeColor, alpha);
    context.lineWidth = 0.75;
    context.shadowColor = rgba(planeColor, alpha * 1.8);
    context.shadowBlur = 4;
    context.beginPath();
    context.moveTo(x - planeWidth / 2 + skew, y - planeHeight / 2);
    context.lineTo(x + planeWidth / 2, y - planeHeight / 2);
    context.lineTo(x + planeWidth / 2 - skew, y + planeHeight / 2);
    context.lineTo(x - planeWidth / 2, y + planeHeight / 2);
    context.closePath();
    context.fillStyle = rgba(planeColor, alpha * 0.09);
    context.fill();
    context.stroke();
    for (let row = 1; row < 4; row += 1) {
      const rowY = y - planeHeight / 2 + (planeHeight * row) / 4;
      context.strokeStyle = rgba(planeColor, alpha * 0.5);
      context.beginPath();
      context.moveTo(x - planeWidth / 2 + skew * (1 - row / 4), rowY);
      context.lineTo(x + planeWidth / 2 - skew * (row / 4), rowY);
      context.stroke();
    }
  }

  for (const [routeIndex, route] of routes.entries()) {
    const fromX = route.fromX * width;
    const fromY = route.fromY * height;
    const toX = route.toX * width;
    const toY = route.toY * height;
    const controlX = (fromX + toX) / 2 + route.bend * width;
    const controlY = (fromY + toY) / 2 - Math.abs(route.bend) * height * 0.42;
    const color = route.signal ? amber : routeIndex % 5 === 0 ? ice : cyan;
    context.strokeStyle = rgba(color, (route.signal ? 0.34 : 0.17) * energy);
    context.lineWidth = route.signal ? 1.05 : 0.7;
    context.shadowColor = rgba(color, 0.22 * energy);
    context.shadowBlur = route.signal ? 8 : 3;
    context.beginPath();
    context.moveTo(fromX, fromY);
    context.quadraticCurveTo(controlX, controlY, toX, toY);
    context.stroke();

    const travel = (route.phase + time * route.speed * energy) % 1;
    const [pulseX, pulseY] = cubicPoint(fromX, fromY, controlX, controlY, toX, toY, travel);
    context.fillStyle = rgba(color, 0.48 + amplitude * 0.34);
    context.shadowColor = rgba(color, 0.75);
    context.shadowBlur = 8 + amplitude * 12;
    context.beginPath();
    context.arc(pulseX, pulseY, route.signal ? 1.8 : 1.15, 0, Math.PI * 2);
    context.fill();
  }

  for (const [nodeIndex, node] of nodes.entries()) {
    const pulse = 0.45 + Math.sin(time * 0.55 + node.phase) * 0.35;
    const color = node.signal ? amber : nodeIndex % 9 === 0 ? ice : cyan;
    const x = node.x * width;
    const y = node.y * height;
    context.fillStyle = rgba(color, (0.16 + pulse * 0.34) * energy);
    context.shadowColor = rgba(color, 0.42);
    context.shadowBlur = 5 + pulse * 5;
    context.fillRect(x - node.size / 2, y - node.size / 2, node.size, node.size);
  }

  context.restore();
}

export function SynapseCoreAtmosphere({ active, reducedMotion, focused, state, amplitude }: SynapseCoreAtmosphereProps): React.ReactElement | null {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef({ state, amplitude });
  useEffect(() => { stateRef.current = { state, amplitude }; }, [state, amplitude]);

  useEffect(() => {
    if (!active) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d", { alpha: true });
    if (!context) return;

    const random = seededRandom(0x5a17c0de);
    const planes = makePlanes(random);
    const routes = makeRoutes(random);
    const nodes = makeNodes(random);
    let width = 1;
    let height = 1;
    let frame = 0;
    let lastPaint = 0;

    const resize = (): void => {
      const bounds = canvas.getBoundingClientRect();
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5);
      width = Math.max(1, bounds.width);
      height = Math.max(1, bounds.height);
      canvas.width = Math.max(1, Math.round(width * pixelRatio));
      canvas.height = Math.max(1, Math.round(height * pixelRatio));
      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    };

    const moving = !reducedMotion;
    const render = (timestamp: number): void => {
      if (document.hidden) return;
      if (moving && timestamp - lastPaint < 1000 / (focused ? 24 : 12)) {
        frame = requestAnimationFrame(render);
        return;
      }
      lastPaint = timestamp;
      const current = stateRef.current;
      const activeState = current.state === "processing" || current.state === "listening" || current.state === "speaking";
      const energy = activeState ? 1.5 : 1.08;
      drawWorkshopScreenEffects(context, width, height, timestamp / 1000, reducedMotion);
      if (moving) frame = requestAnimationFrame(render);
    };

    const start = (): void => {
      cancelAnimationFrame(frame);
      lastPaint = 0;
      if (document.hidden) return;
      if (moving) frame = requestAnimationFrame(render);
      else render(performance.now());
    };
    const resizeObserver = new ResizeObserver(() => { resize(); if (!moving) render(performance.now()); });
    resizeObserver.observe(canvas);
    document.addEventListener("visibilitychange", start);
    resize();
    start();
    return () => {
      cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      document.removeEventListener("visibilitychange", start);
    };
  }, [active, focused, reducedMotion]);

  if (!active) return null;
  return (
    <div className="synapse-core-atmosphere" aria-hidden="true" data-motion={!reducedMotion ? "running" : "paused"}>
      <img className="synapse-core-atmosphere-image" src={workshopBackground} alt="" />
      <canvas ref={canvasRef} className="synapse-core-atmosphere-canvas" />
    </div>
  );
}
