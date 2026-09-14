import { describe, expect, it } from "vitest";
import {
  applyCommandSelection,
  buildCommandRegistry,
  commandName,
  filterCommands,
  isSlashDiscoveryInput,
  moveCommandSelection,
  parseSlashIntent,
  resolveSlashIntent,
  slashQuery
} from "../src/shared/commandDiscovery";
import type { CommandDiscoveryItem } from "../src/shared/types";

const commands: CommandDiscoveryItem[] = [
  {
    tool_id: "agent.status",
    display_name: "Agent status",
    description: "Show agent runtime status.",
    category: "agents",
    available: true,
    requires_approval: false,
    risk_level: "low"
  },
  {
    tool_id: "task.create",
    display_name: "Create task",
    description: "Create a governed task.",
    category: "tasks",
    available: false,
    requires_approval: true,
    risk_level: "medium",
    reason_unavailable: "Approval required"
  }
];

describe("slash command discovery", () => {
  it("keeps plain text in conversation mode", () => {
    expect(isSlashDiscoveryInput("hello")).toBe(false);
    expect(isSlashDiscoveryInput("/")).toBe(true);
    expect(slashQuery("hello")).toBe("");
  });

  it("opens the full list for / and filters partial input", () => {
    expect(filterCommands(commands, "/").map(commandName)).toEqual(["agent.status", "task.create"]);
    expect(filterCommands(commands, "/agent").map(commandName)).toEqual(["agent.status"]);
    expect(filterCommands(commands, "/create").map(commandName)).toEqual(["task.create"]);
  });

  it("supports bounded keyboard navigation", () => {
    expect(moveCommandSelection(0, 1, 2)).toBe(1);
    expect(moveCommandSelection(1, 1, 2)).toBe(1);
    expect(moveCommandSelection(1, -1, 2)).toBe(0);
    expect(moveCommandSelection(0, -1, 2)).toBe(0);
  });

  it("applies Enter selection safely and ignores unknown selection", () => {
    expect(applyCommandSelection(commands[0])).toBe("/agent.status ");
    expect(applyCommandSelection(undefined)).toBeNull();
  });

  it("builds a typed registry from frontend commands and factual backend tools", () => {
    const registry = buildCommandRegistry(commands);

    expect(registry.map(commandName).slice(0, 5)).toEqual(["activity", "insight", "settings", "project", "project.files"]);
    expect(registry.find((item) => commandName(item) === "activity")?.execution_kind).toBe("ui");
    expect(registry.find((item) => commandName(item) === "project")?.argument_schema).toBe("project_id");
    expect(registry.find((item) => commandName(item) === "project.files")?.opens_surface).toBe("project_files");
    expect(registry.find((item) => commandName(item) === "agent.status")?.execution_kind).toBe("unsupported");
    expect(registry.find((item) => commandName(item) === "agent.status")?.available).toBe(false);
  });

  it("parses and validates slash intents without treating them as shell strings", () => {
    const registry = buildCommandRegistry(commands);

    expect(parseSlashIntent("/project backend")).toEqual({ command: "project", args: ["backend"], rawArgs: "backend" });
    expect(resolveSlashIntent("hello", registry)).toEqual({ kind: "plain_text" });
    expect(resolveSlashIntent("/unknown", registry)).toMatchObject({ kind: "unknown", command: "unknown" });
    expect(resolveSlashIntent("/project", registry)).toMatchObject({ kind: "missing_argument" });
    expect(resolveSlashIntent("/project bad/id", registry)).toMatchObject({ kind: "invalid_argument" });
    expect(resolveSlashIntent("/activity now", registry)).toMatchObject({ kind: "invalid_argument" });
    expect(resolveSlashIntent("/activity", registry)).toMatchObject({ kind: "ready", args: {} });
    expect(resolveSlashIntent("/project.files", registry)).toMatchObject({ kind: "ready", args: {} });
    expect(resolveSlashIntent("/project backend", registry)).toMatchObject({
      kind: "ready",
      args: { project_id: "backend" }
    });
  });

  it("keeps unavailable backend catalog tools unavailable for direct composer execution", () => {
    const registry = buildCommandRegistry(commands);

    expect(resolveSlashIntent("/agent.status", registry)).toMatchObject({
      kind: "unavailable",
      message: "Tool catalog item is not directly executable from the composer yet."
    });
  });
});
