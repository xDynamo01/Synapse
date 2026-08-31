import { describe, expect, it } from "vitest";
import { assetsForTheme } from "../src/shared/themeAssets";

describe("theme asset resolver", () => {
  it("changes navigation and notification sources for every theme", () => {
    const themes = ["synapse", "violet", "amber", "blue", "neutral"] as const;
    const sources = themes.map((theme) => assetsForTheme(theme));
    expect(new Set(sources.map((value) => value.navigation.constellation)).size).toBe(5);
    expect(new Set(sources.map((value) => value.navigation.history)).size).toBe(5);
    expect(new Set(sources.map((value) => value.navigation.settings)).size).toBe(5);
    expect(new Set(sources.map((value) => value.notifications.idle)).size).toBe(5);
    expect(new Set(sources.map((value) => value.notifications.active)).size).toBe(5);
    expect(assetsForTheme("synapse").navigation.constellation).toContain("/synapse/");
  });
});
