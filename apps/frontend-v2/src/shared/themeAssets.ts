import type { FrontendThemePreference } from "./settingsPreferences.js";

export interface ThemeAssetSet {
  navigation: { constellation: string; history: string; settings: string };
  notifications: { idle: string; active: string };
}

const themes: FrontendThemePreference[] = ["synapse", "violet", "amber", "blue", "neutral"];

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
  violet: {
    navigation: {
      constellation: new URL("../../assets/media/icons/navigation/violet/constellation.png", import.meta.url).href,
      history: new URL("../../assets/media/icons/navigation/violet/library.png", import.meta.url).href,
      settings: new URL("../../assets/media/icons/navigation/violet/settings.png", import.meta.url).href
    },
    notifications: {
      idle: new URL("../../assets/media/icons/status/violet/notifications-idle.png", import.meta.url).href,
      active: new URL("../../assets/media/icons/status/violet/notifications-active.png", import.meta.url).href
    }
  },
  amber: {
    navigation: {
      constellation: new URL("../../assets/media/icons/navigation/amber/constellation.png", import.meta.url).href,
      history: new URL("../../assets/media/icons/navigation/amber/library.png", import.meta.url).href,
      settings: new URL("../../assets/media/icons/navigation/amber/settings.png", import.meta.url).href
    },
    notifications: {
      idle: new URL("../../assets/media/icons/status/amber/notifications-idle.png", import.meta.url).href,
      active: new URL("../../assets/media/icons/status/amber/notifications-active.png", import.meta.url).href
    }
  },
  blue: {
    navigation: {
      constellation: new URL("../../assets/media/icons/navigation/blue/constellation.png", import.meta.url).href,
      history: new URL("../../assets/media/icons/navigation/blue/library.png", import.meta.url).href,
      settings: new URL("../../assets/media/icons/navigation/blue/settings.png", import.meta.url).href
    },
    notifications: {
      idle: new URL("../../assets/media/icons/status/blue/notifications-idle.png", import.meta.url).href,
      active: new URL("../../assets/media/icons/status/blue/notifications-active.png", import.meta.url).href
    }
  },
  neutral: {
    navigation: {
      constellation: new URL("../../assets/media/icons/navigation/neutral/constellation.png", import.meta.url).href,
      history: new URL("../../assets/media/icons/navigation/neutral/library.png", import.meta.url).href,
      settings: new URL("../../assets/media/icons/navigation/neutral/settings.png", import.meta.url).href
    },
    notifications: {
      idle: new URL("../../assets/media/icons/status/neutral/notifications-idle.png", import.meta.url).href,
      active: new URL("../../assets/media/icons/status/neutral/notifications-active.png", import.meta.url).href
    }
  }
};

export const themeAssets: Record<FrontendThemePreference, ThemeAssetSet> = Object.fromEntries(
  themes.map((theme) => [theme, themeAssetUrls[theme]])
) as Record<FrontendThemePreference, ThemeAssetSet>;

export function assetsForTheme(theme: FrontendThemePreference): ThemeAssetSet {
  const assets = themeAssets[theme];
  if (!assets) {
    throw new Error(`Missing shell icon registry entry for theme: ${String(theme)}`);
  }
  return assets;
}
