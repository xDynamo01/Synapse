import type { FrontendThemePreference } from "./settingsPreferences.js";
import { resolveTheme } from "./themeEngine.js";

export interface ThemeAssetSet {
  navigation: { constellation: string; history: string; settings: string };
  notifications: { idle: string; active: string };
}

const themes: FrontendThemePreference[] = ["synapse"];

const themeAssetUrls: Record<FrontendThemePreference, ThemeAssetSet> = {
  synapse: {
    navigation: {
      constellation: new URL("../../assets/media/icons/navigation/synapse/constellation.png", import.meta.url).href,
      history: new URL("../../assets/media/icons/navigation/synapse/library.png", import.meta.url).href,
      settings: new URL("../../assets/media/icons/navigation/synapse/settings.png", import.meta.url).href
    },
    notifications: {
      idle: new URL("../../assets/media/icons/status/synapse/notifications-idle.png", import.meta.url).href,
      active: new URL("../../assets/media/icons/status/synapse/notifications-active.png", import.meta.url).href
    }
  },
};

export const themeAssets: Record<FrontendThemePreference, ThemeAssetSet> = Object.fromEntries(
  themes.map((theme) => [theme, themeAssetUrls[theme]])
) as Record<FrontendThemePreference, ThemeAssetSet>;

export function assetsForTheme(theme: FrontendThemePreference): ThemeAssetSet {
  const assets = themeAssets[resolveTheme(theme).icons];
  if (!assets) {
    throw new Error(`Missing shell icon registry entry for theme: ${String(theme)}`);
  }
  return assets;
}
