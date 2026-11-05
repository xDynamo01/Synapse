import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { WorkspacePanel } from "../src/renderer/WorkspacePanel";

function renderWorkspace(agentCount: number): string {
  const agents = Array.from({ length: agentCount }, (_, index) => ({
    agent_id: `agent-${index + 1}`,
    display_name: `Agent ${index + 1}`,
    preferred_model: `Model ${index + 1}`
  }));
  return renderToStaticMarkup(React.createElement(WorkspacePanel, {
    projects: [], showProjects: false,
    swarms: agentCount ? [{ swarm_id: "swarm-1", status: "running", mission_id: "mission-1" }] : [],
    activeProjectId: null, loading: false, error: null,
    onClose: () => undefined, onRefresh: () => undefined,
    onSelectProject: () => undefined, onOpenFiles: () => undefined,
    onSwarmAction: () => undefined,
    selectedSwarmId: agentCount ? "swarm-1" : null,
    swarmDetail: agentCount ? { status: "running", member_agent_ids: agents.map((agent) => agent.agent_id) } : null,
    swarmTrace: agentCount ? { events: [{ agent_id: "agent-30", event_type: "task.started", timestamp: "2026-09-28T13:00:00", status: "running" }] } : null,
    onSelectSwarm: () => undefined, swarmAgents: agents, swarmTools: {},
    onSubmitWork: () => undefined, onExecuteCommand: async () => ({ status: "completed" }),
    commandOutput: [{ input: "/ajuda", output: "Comandos disponíveis" }],
    agentName: "Artemis", primaryAgentId: "primary", modelName: "Qwen3 8B",
    swarmResult: null, demoActive: false,
    swarmConfirmation: null, swarmConfirmationBusy: false,
    onResolveSwarmConfirmation: () => undefined
  }));
}

describe("Workspace terminal layout", () => {
  it("uses the full primary terminal when no swarm is selected", () => {
    const html = renderWorkspace(0);
    expect(html).toContain("workspace-terminal-grid--solo");
    expect(html).toContain('aria-label="Terminal de Artemis"');
    expect(html).toContain("Qwen3 8B");
    expect(html).not.toContain("Terminal de Agent 1");
  });

  it("places the primary terminal and all 30 agents in one resizable grid", () => {
    const html = renderWorkspace(30);
    expect(html).toContain("workspace-terminal-grid--swarm");
    expect(html.match(/aria-label="Terminal de /g)).toHaveLength(31);
    expect(html).toContain('aria-label="Terminal de Agent 30"');
    expect(html).toContain("task.started");
    expect(html).toContain("Comandos disponíveis");
  });

  it("renders the shared Swarm confirmation inside the primary terminal", () => {
    const html = renderToStaticMarkup(React.createElement(WorkspacePanel, {
      projects: [], showProjects: false, swarms: [], activeProjectId: null,
      loading: false, error: null, onClose: () => undefined, onRefresh: () => undefined,
      onSelectProject: () => undefined, onOpenFiles: () => undefined,
      onSwarmAction: () => undefined, selectedSwarmId: null, swarmDetail: null,
      swarmTrace: null, onSelectSwarm: () => undefined, swarmAgents: [], swarmTools: {},
      onSubmitWork: () => undefined, onExecuteCommand: async () => ({ status: "completed" }),
      commandOutput: [], agentName: "Artemis", primaryAgentId: "primary", modelName: "Qwen",
      swarmResult: null, demoActive: false, swarmConfirmationBusy: false,
      onResolveSwarmConfirmation: () => undefined,
      swarmConfirmation: {
        request_id: "request-1", conversation_id: "conversation-1", workspace_id: "default",
        project_id: null, session_id: null, task: "Use um Swarm para revisar o projeto", requested_agents: null,
        recommended_agents: 3, explicit_models: ["Qwen"], status: "pending",
        mission_id: null, swarm_id: null, execution_status: null
      }
    }));
    expect(html).toContain("Confirmar criação do Swarm");
    expect(html).toContain("Iniciar com 3");
    expect(html).toContain("Qwen");
  });
});
