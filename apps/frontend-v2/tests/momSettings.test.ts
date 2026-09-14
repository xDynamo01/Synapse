import { afterEach, describe, expect, it, vi } from "vitest";
import { SynapseFrontendClient } from "../src/shared/frontendClient";
import { momModelChoices, momOperations, routeKey } from "../src/renderer/MoMSettings";
import type { SettingsSnapshot } from "../src/shared/types";

afterEach(() => vi.unstubAllGlobals());

describe("Primary MoM settings", () => {
  it("reads and saves exact routes and revision without touching default models", async () => {
    const calls: Array<[string, RequestInit | undefined]> = [];
    const stored = { workspace_id: "my workspace", primary_agent_id: "artemis", enabled: true, revision: 4,
      routes: [{ operation: "coding", provider: "synapse_local", model: "DeepSeek" }] };
    vi.stubGlobal("fetch", async (url: unknown, init?: RequestInit) => {
      calls.push([String(url), init]); return new Response(JSON.stringify(stored), { status: 200 });
    });
    const client = new SynapseFrontendClient("http://localhost:1234");
    expect(await client.momConfiguration("my workspace")).toEqual(stored);
    const payload = { workspace_id: "default", enabled: true, expected_revision: 3, routes: [] };
    expect(await client.saveMoMConfiguration(payload)).toEqual(stored);
    expect(calls.map(([url]) => url)).toEqual([
      "http://localhost:1234/api/primary/mom/configuration?workspace_id=my%20workspace",
      "http://localhost:1234/api/primary/mom/configuration"
    ]);
    expect(calls[1][1]?.method).toBe("PUT");
    expect(JSON.parse(String(calls[1][1]?.body))).toEqual(payload);
  });

  it("surfaces save errors instead of treating drafts as persisted", async () => {
    vi.stubGlobal("fetch", async () => new Response(JSON.stringify({ detail: "StorageRevisionConflict" }), { status: 500 }));
    await expect(new SynapseFrontendClient("http://localhost").saveMoMConfiguration({
      workspace_id: "default", enabled: false, expected_revision: 1, routes: []
    })).rejects.toThrow();
  });

  it("offers four specialists separately from the default generalist", () => {
    expect(momOperations.map((operation) => operation.id)).toEqual(["coding", "reasoning", "review", "summary"]);
    const snapshot = { models: { catalog: [
      { name: "same", provider: "a", chat_usable: true, status: "available" },
      { name: "same", provider: "b", chat_usable: true, status: "available" },
      { name: "embed", provider: "a", chat_usable: false, status: "available" }
    ], providers: [{ provider_id: "a", display_name: "A" }, { provider_id: "b", display_name: "B" }],
    provider_settings: [{ provider_id: "b", enabled: false }] } } as SettingsSnapshot;
    const choices = momModelChoices(snapshot);
    expect(choices).toHaveLength(2);
    expect(choices[0].value).toBe(routeKey({ provider: "a", model: "same" }));
    expect(choices[0].disabled).toBe(false);
    expect(choices[1].value).not.toBe(choices[0].value);
    expect(choices[1].disabled).toBe(true);
  });
});
