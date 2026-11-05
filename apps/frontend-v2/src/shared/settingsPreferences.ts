import { resolveTheme } from "./themeEngine.js";
import type { ThemeId } from "./themeEngine.js";
export type ReducedMotionPreference = "system" | "reduce";
export type FrontendThemePreference = ThemeId;

export interface FrontendSettingsPreferences {
  reducedMotion: ReducedMotionPreference;
  theme: FrontendThemePreference;
}

const storageKey = "synapse.frontend-v2.settings";
const defaults: FrontendSettingsPreferences = {
  reducedMotion: "system",
  theme: "synapse"
};

export function loadFrontendSettingsPreferences(): FrontendSettingsPreferences {
  if (typeof window === "undefined") {
    return defaults;
  }
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) {
      return defaults;
    }
    const parsed = JSON.parse(raw) as Partial<FrontendSettingsPreferences>;
    return {
      reducedMotion: parsed.reducedMotion === "reduce" ? "reduce" : "system",
      theme: normalizeTheme(parsed.theme)
    };
  } catch {
    return defaults;
  }
}

export function saveFrontendSettingsPreferences(preferences: FrontendSettingsPreferences): FrontendSettingsPreferences {
  const normalized: FrontendSettingsPreferences = {
    reducedMotion: preferences.reducedMotion === "reduce" ? "reduce" : "system",
    theme: normalizeTheme(preferences.theme)
  };
  if (typeof window !== "undefined") {
    window.localStorage.setItem(storageKey, JSON.stringify(normalized));
  }
  return normalized;
}

export function effectiveReducedMotion(preference: ReducedMotionPreference, systemReducedMotion: boolean): boolean {
  return preference === "reduce" || systemReducedMotion;
}

export function normalizeTheme(value: unknown): FrontendThemePreference {
  return resolveTheme("synapse").id;
}
