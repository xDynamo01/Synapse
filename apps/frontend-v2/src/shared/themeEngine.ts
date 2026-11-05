/** Bundled presentation data only. Theme packs cannot execute code or load remote assets. */
export type ThemeId = "synapse";
export type IconFamily = ThemeId;
export interface ThemePack {
  readonly version: 1;
  readonly id: ThemeId;
  readonly label: string;
  readonly description: string;
  readonly colors: {
    readonly background: string; readonly deep: string; readonly panel: string;
    readonly accent: string; readonly secondary: string; readonly text: string;
    readonly muted: string; readonly signal: string;
  };
  readonly typography: { readonly ui: string; readonly code: string };
  readonly surfaces: { readonly radius: number; readonly controlRadius: number; readonly glow: number };
  readonly icons: IconFamily;
  readonly background: { readonly pattern: "holographic"; readonly duration: number };
  readonly presence: { readonly style: "jarvis"; readonly speed: number };
  readonly swarm: readonly [string, string, string, string, string, string];
}

const ui = 'Inter, "Segoe UI", system-ui, sans-serif';
const code = 'ui-monospace, "Cascadia Code", Consolas, monospace';
const core: ThemePack = {
  version: 1, id: "synapse", label: "Synapse Core",
  description: "Interface de núcleo tático, energia ciano e sinais operacionais âmbar.",
  colors: { background: "#0c2029", deep: "#06131a", panel: "#15313b", accent: "#54fff4", secondary: "#8ee5ed", text: "#e7fbff", muted: "#a9c7cf", signal: "#ffd166" },
  typography: { ui, code }, surfaces: { radius: 14, controlRadius: 7, glow: 18 },
  icons: "synapse", background: { pattern: "holographic", duration: 48 },
  presence: { style: "jarvis", speed: 1 },
  swarm: ["#54fff4", "#b987ff", "#ff79ae", "#4ce6b2", "#ffd166", "#7cbbff"]
};

export const themePacks: readonly ThemePack[] = [core];

export function resolveTheme(value: unknown): ThemePack {
  return themePacks.find((theme) => theme.id === value) ?? core;
}

export function themeVariables(pack: ThemePack): Record<`--${string}`, string> {
  const c = pack.colors;
  const blend = (color: string, percent: number) => `color-mix(in srgb, ${color} ${percent}%, transparent)`;
  return {
    "--app-bg": c.background, "--app-bg-deep": c.deep,
    "--surface-bg": blend(c.panel, 85), "--panel-bg-a": c.panel, "--panel-bg-b": c.deep,
    "--primary-accent": c.accent, "--secondary-accent": c.secondary,
    "--signal-accent": c.signal,
    "--text-color": c.text, "--text-muted": c.muted, "--border-color": blend(c.secondary, 28),
    "--control-bg": c.panel, "--control-bg-hover": blend(c.accent, 12), "--control-disabled": blend(c.text, 45),
    "--rail-bg": c.deep, "--shell-nav-bg": c.panel, "--shell-nav-bg-hover": blend(c.accent, 16),
    "--shell-nav-bg-active": blend(c.accent, 22), "--shell-nav-border": blend(c.accent, 30),
    "--shell-nav-border-active": blend(c.accent, 60), "--shell-nav-glow": blend(c.accent, 12),
    "--theme-font-ui": pack.typography.ui, "--theme-font-code": pack.typography.code,
    "--theme-radius": `${pack.surfaces.radius}px`, "--theme-control-radius": `${pack.surfaces.controlRadius}px`,
    "--theme-glow": `${pack.surfaces.glow}px`, "--theme-duration": `${pack.background.duration}s`,
    "--shell-gradient-start": "#020609", "--shell-gradient-mid": "#061e23", "--shell-gradient-end": "#0a3035",
    "--rail-gradient-start": "#0a3035", "--rail-gradient-end": "#020609",
    ...Object.fromEntries(pack.swarm.map((color, i) => [`--theme-agent-${i}`, color]))
  };
}

export function themeMotion(reduced: boolean, focused: boolean, hidden: boolean): { animate: boolean; fps: number } {
  return { animate: !reduced && focused && !hidden, fps: hidden ? 0 : !focused ? 8 : reduced ? 12 : 30 };
}

/** One application boundary: sets all tokens on every switch, so values cannot leak. */
export function applyTheme(root: HTMLElement, value: unknown, reduced: boolean, focused: boolean): void {
  const pack = resolveTheme(value);
  for (const [key, token] of Object.entries(themeVariables(pack))) root.style.setProperty(key, token);
  root.dataset.theme = pack.id;
  root.dataset.themeBackground = pack.background.pattern;
  root.dataset.themeMotion = themeMotion(reduced, focused, false).animate ? "running" : "paused";
  root.dataset.themeReduced = String(reduced);
}
