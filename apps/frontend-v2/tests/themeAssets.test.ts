import { describe, expect, it } from "vitest";
import { assetsForTheme } from "../src/shared/themeAssets";

describe("theme asset resolver", () => {
  it("resolves the bundled shell assets for each available theme", () => {
    const themes = ["synapse"] as const;
    const sources = themes.map((theme) => assetsForTheme(theme));
    expect(new Set(sources.map((value) => value.navigation.constellation)).size).toBe(1);
    expect(new Set(sources.map((value) => value.navigation.history)).size).toBe(1);
    expect(new Set(sources.map((value) => value.navigation.settings)).size).toBe(1);
    expect(new Set(sources.map((value) => value.notifications.idle)).size).toBe(1);
    expect(new Set(sources.map((value) => value.notifications.active)).size).toBe(1);
    expect(assetsForTheme("synapse").navigation.constellation).toContain("/synapse/");
  });
});
