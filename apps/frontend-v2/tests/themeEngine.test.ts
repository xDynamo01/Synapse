import { describe, expect, it } from "vitest";
import { applyTheme, resolveTheme, themeMotion, themePacks, themeVariables } from "../src/shared/themeEngine";
import { assetsForTheme } from "../src/shared/themeAssets";

function luminance(hex: string): number {
  const rgb = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((v) => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
  return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
}

describe("theme packs", () => {
  it("resolves unknown or corrupt saved IDs safely, including object prototype names", () => {
    for (const id of [null, {}, "__proto__", "constructor", "missing"]) expect(resolveTheme(id).id).toBe("synapse");
    for (const pack of themePacks) expect(resolveTheme(pack.id)).toBe(pack);
  });

  it("ships complete packs with readable text and resolvable bundled icons", () => {
    expect(themePacks.map((pack) => pack.id)).toEqual(["synapse"]);
    expect(new Set(themePacks.map((p) => p.id)).size).toBe(themePacks.length);
    const keys = Object.keys(themeVariables(themePacks[0])).sort();
    for (const pack of themePacks) {
      expect(Object.keys(themeVariables(pack)).sort()).toEqual(keys);
      expect(assetsForTheme(pack.id).navigation.settings).toBeTruthy();
      for (const color of Object.values(pack.colors)) expect(color).toMatch(/^#[\da-f]{6}$/i);
      for (const foreground of [pack.colors.text, pack.colors.muted, pack.colors.accent, pack.colors.signal]) {
        const ratio = (luminance(foreground) + 0.05) / (luminance(pack.colors.panel) + 0.05);
        expect(ratio).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it("defines Synapse Core as a complete tactical presentation rather than a legacy recolor", () => {
    const core = resolveTheme("synapse");
    expect(core.presence).toEqual({ style: "jarvis", speed: 1 });
    expect(core.background.pattern).toBe("holographic");
    expect(core.colors.signal).toBe("#ffd166");
    expect(core.swarm[0]).toBe(core.colors.accent);
    expect(themeVariables(core)["--signal-accent"]).toBe(core.colors.signal);
  });

  it("always resolves the single default pack and resets motion state", () => {
    const properties = new Map<string, string>();
    const root = { dataset: {}, style: { setProperty: (key: string, value: string) => properties.set(key, value) } };
    applyTheme(root as unknown as HTMLElement, "unknown", false, true);
    expect(root.dataset).toMatchObject({ theme: "synapse", themeBackground: "holographic", themeMotion: "running" });
    applyTheme(root as unknown as HTMLElement, "synapse", true, false);
    expect(Object.fromEntries(properties)).toEqual(themeVariables(resolveTheme("synapse")));
    expect(root.dataset).toMatchObject({ themeBackground: "holographic", themeReduced: "true", themeMotion: "paused" });
    applyTheme(root as unknown as HTMLElement, "synapse", false, true);
    expect(Object.fromEntries(properties)).toEqual(themeVariables(resolveTheme("synapse")));
  });

  it("stops decorative motion and limits drawing for hidden, unfocused and reduced motion modes", () => {
    expect(themeMotion(false, true, false)).toEqual({ animate: true, fps: 30 });
    expect(themeMotion(true, true, false)).toEqual({ animate: false, fps: 12 });
    expect(themeMotion(false, false, false)).toEqual({ animate: false, fps: 8 });
    expect(themeMotion(false, true, true)).toEqual({ animate: false, fps: 0 });
  });
});
