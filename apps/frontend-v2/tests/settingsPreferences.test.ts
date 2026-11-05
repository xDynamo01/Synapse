import { describe, expect, it, beforeEach, vi } from "vitest";
import {
  effectiveReducedMotion,
  loadFrontendSettingsPreferences,
  saveFrontendSettingsPreferences
} from "../src/shared/settingsPreferences";

describe("settings preferences", () => {
  const store = new Map<string, string>();

  beforeEach(() => {
    store.clear();
    vi.stubGlobal("window", {
      localStorage: {
        clear: () => store.clear(),
        getItem: (key: string) => store.get(key) ?? null,
        setItem: (key: string, value: string) => store.set(key, value)
      }
    });
    window.localStorage.clear();
  });

  it("persists and restores the frontend-owned reduced motion preference", () => {
    saveFrontendSettingsPreferences({ reducedMotion: "reduce", theme: "synapse" });

    expect(loadFrontendSettingsPreferences()).toEqual({ reducedMotion: "reduce", theme: "synapse" });
    expect(effectiveReducedMotion("reduce", false)).toBe(true);
  });

  it("normalizes invalid stored preferences back to system", () => {
    window.localStorage.setItem("synapse.frontend-v2.settings", JSON.stringify({ reducedMotion: "theme-dark", theme: "unknown" }));

    expect(loadFrontendSettingsPreferences()).toEqual({ reducedMotion: "system", theme: "synapse" });
    expect(effectiveReducedMotion("system", true)).toBe(true);
    expect(effectiveReducedMotion("system", false)).toBe(false);
  });

  it("keeps the single default theme when an old theme is supplied", () => {
    saveFrontendSettingsPreferences({ reducedMotion: "system", theme: "cyberpunk" });

    expect(loadFrontendSettingsPreferences()).toEqual({ reducedMotion: "system", theme: "synapse" });
  });
});
