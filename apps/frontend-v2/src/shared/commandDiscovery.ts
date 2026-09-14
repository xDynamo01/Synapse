import type { CommandDiscoveryItem } from "./types.js";

const frontendCommands: CommandDiscoveryItem[] = [
  {
    tool_id: "activity",
    display_name: "Activity",
    description: "Toggle the central Presence/Activity surface.",
    category: "ui",
    available: true,
    requires_approval: false,
    risk_level: "low",
    execution_kind: "ui",
    argument_schema: "none",
    opens_surface: "activity",
    requires_backend_authority: false
  },
  {
    tool_id: "insight",
    display_name: "Insight",
    description: "Open the existing Insight surface.",
    category: "ui",
    available: true,
    requires_approval: false,
    risk_level: "low",
    execution_kind: "ui",
    argument_schema: "none",
    opens_surface: "insight",
    requires_backend_authority: false
  },
  {
    tool_id: "settings",
    display_name: "Settings",
    description: "Open the existing Settings surface.",
    category: "ui",
    available: true,
    requires_approval: false,
    risk_level: "low",
    execution_kind: "ui",
    argument_schema: "none",
    opens_surface: "settings",
    requires_backend_authority: false
  },
  {
    tool_id: "project",
    display_name: "Project",
    description: "Switch to a real project scope. Usage: /project <project_id>.",
    category: "project",
    available: true,
    requires_approval: false,
    risk_level: "low",
    execution_kind: "project_scope",
    argument_schema: "project_id",
    opens_surface: null,
    requires_backend_authority: true
  },
  {
    tool_id: "project.files",
    display_name: "Project Files",
    description: "Open Project Files for the active project without running retrieval.",
    category: "project",
    available: true,
    requires_approval: false,
    risk_level: "low",
    execution_kind: "ui",
    argument_schema: "none",
    opens_surface: "project_files",
    requires_backend_authority: false
  }
];

export interface ParsedSlashIntent {
  command: string;
  args: string[];
  rawArgs: string;
}

export type SlashIntentResolution =
  | { kind: "plain_text" }
  | { kind: "unknown"; command: string; message: string }
  | { kind: "missing_argument"; command: CommandDiscoveryItem; message: string }
  | { kind: "invalid_argument"; command: CommandDiscoveryItem; message: string }
  | { kind: "unavailable"; command: CommandDiscoveryItem; message: string }
  | { kind: "ready"; command: CommandDiscoveryItem; args: Record<string, string> };

export function isSlashDiscoveryInput(value: string): boolean {
  return value.startsWith("/");
}

export function slashQuery(value: string): string {
  return isSlashDiscoveryInput(value) ? value.slice(1).trim().toLowerCase() : "";
}

export function commandName(command: CommandDiscoveryItem): string {
  return command.tool_id.replace(/[^a-zA-Z0-9_.:-]+/g, "-");
}

export function buildCommandRegistry(discoveredTools: CommandDiscoveryItem[]): CommandDiscoveryItem[] {
  const registeredNames = new Set(frontendCommands.map((command) => commandName(command)));
  const unsupportedTools = discoveredTools
    .filter((tool) => !registeredNames.has(commandName(tool)))
    .map((tool) => ({
      ...tool,
      available: false,
      reason_unavailable: tool.reason_unavailable ?? "Tool catalog item is not directly executable from the composer yet.",
      execution_kind: "unsupported" as const,
      argument_schema: "none" as const,
      opens_surface: null,
      requires_backend_authority: true
    }));
  return [...frontendCommands, ...unsupportedTools];
}

export function filterCommands(commands: CommandDiscoveryItem[], input: string): CommandDiscoveryItem[] {
  const query = slashQuery(input);
  return commands.filter((command) => {
    const haystack = `${commandName(command)} ${command.display_name} ${command.description}`.toLowerCase();
    return haystack.includes(query);
  });
}

export function moveCommandSelection(current: number, direction: 1 | -1, total: number): number {
  if (total <= 0) {
    return 0;
  }
  return Math.max(0, Math.min(current + direction, total - 1));
}

export function applyCommandSelection(command: CommandDiscoveryItem | undefined): string | null {
  return command ? `/${commandName(command)} ` : null;
}

export function parseSlashIntent(value: string): ParsedSlashIntent | null {
  if (!isSlashDiscoveryInput(value)) {
    return null;
  }
  const commandLine = value.trim();
  const withoutSlash = commandLine.slice(1).trim();
  if (!withoutSlash) {
    return null;
  }
  const [command = "", ...args] = withoutSlash.split(/\s+/);
  const rawArgs = withoutSlash.slice(command.length).trim();
  return { command: command.toLowerCase(), args, rawArgs };
}

export function resolveSlashIntent(value: string, commands: CommandDiscoveryItem[]): SlashIntentResolution {
  const parsed = parseSlashIntent(value);
  if (!parsed) {
    return isSlashDiscoveryInput(value)
      ? { kind: "unknown", command: "", message: "Choose a slash command before executing." }
      : { kind: "plain_text" };
  }
  const command = commands.find((item) => commandName(item).toLowerCase() === parsed.command);
  if (!command) {
    return { kind: "unknown", command: parsed.command, message: `Unknown slash command: /${parsed.command}` };
  }
  if (!command.available) {
    return {
      kind: "unavailable",
      command,
      message: command.reason_unavailable ?? `/${commandName(command)} is unavailable in this context.`
    };
  }
  if (command.argument_schema === "project_id") {
    if (parsed.args.length === 0) {
      return {
        kind: "missing_argument",
        command,
        message: "Missing project id. Usage: /project <project_id>"
      };
    }
    if (parsed.args.length > 1 || !isSafeProjectId(parsed.args[0])) {
      return {
        kind: "invalid_argument",
        command,
        message: "Invalid project id. Use letters, numbers, dots, underscores or hyphens."
      };
    }
    return { kind: "ready", command, args: { project_id: parsed.args[0] } };
  }
  if (parsed.args.length > 0) {
    return {
      kind: "invalid_argument",
      command,
      message: `/${commandName(command)} does not accept arguments.`
    };
  }
  return { kind: "ready", command, args: {} };
}

function isSafeProjectId(value: string): boolean {
  return /^[a-zA-Z0-9_.-]{1,96}$/.test(value);
}
