import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ProjectManifestSummary, SwarmInteractionRequest } from "../shared/types";
import { SwarmConfirmationCard } from "./SwarmConfirmationCard";
import type { SwarmConfirmationAction } from "./SwarmConfirmationCard";
import { filterCommands } from "../shared/commandDiscovery";
import type { CommandDiscoveryItem } from "../shared/types";

type TraceEvent = Record<string, unknown>;

interface WorkspacePanelProps {
  projects: ProjectManifestSummary[];
  showProjects: boolean;
  swarms: Array<Record<string, unknown>>;
  activeProjectId: string | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  onRefresh: () => void;
  onSelectProject: (projectId: string) => void;
  onOpenFiles: () => void;
  onSwarmAction: (swarmId: string, action: "start" | "pause" | "resume" | "cancel") => void;
  selectedSwarmId: string | null;
  swarmDetail: Record<string, unknown> | null;
  swarmTrace: Record<string, unknown> | null;
  onSelectSwarm: (swarmId: string) => void;
  swarmAgents: Array<Record<string, unknown>>;
  swarmTools: Record<string, string[]>;
  onSubmitWork: (request: string) => void;
  onExecuteCommand: (request: string) => Promise<{ status: string; message?: string }>;
  commandOutput: Array<{ input: string; output: string }>;
  agentName: string;
  primaryAgentId: string | null;
  modelName: string;
  swarmResult: Record<string, unknown> | null;
  demoActive: boolean;
  swarmConfirmation: SwarmInteractionRequest | null;
  swarmConfirmationBusy: boolean;
  onResolveSwarmConfirmation: (action: SwarmConfirmationAction) => void;
  commands?: CommandDiscoveryItem[];
}

function traceEvents(trace: Record<string, unknown> | null): TraceEvent[] {
  return Array.isArray(trace?.events)
    ? trace.events.filter((event): event is TraceEvent => Boolean(event) && typeof event === "object")
    : [];
}

function eventLine(event: TraceEvent): string {
  const time = typeof event.timestamp === "string" ? event.timestamp.slice(11, 19) : "--:--:--";
  const type = String(event.event_type ?? "evento");
  const status = event.status ? ` · ${String(event.status)}` : "";
  const tools = Array.isArray(event.tool_ids) && event.tool_ids.length > 0 ? ` · ${event.tool_ids.map(String).join(", ")}` : "";
  return `[${time}] ${type}${status}${tools}`;
}

export function WorkspacePanel({
  projects, showProjects, swarms, activeProjectId, loading, error, onClose, onRefresh,
  onSelectProject, onOpenFiles, onSwarmAction, selectedSwarmId, swarmDetail, swarmTrace,
  onSelectSwarm, swarmAgents, swarmTools, onSubmitWork, onExecuteCommand, commandOutput,
  agentName, primaryAgentId, modelName, swarmResult, demoActive,
  swarmConfirmation, swarmConfirmationBusy, onResolveSwarmConfirmation
  , commands
}: WorkspacePanelProps): React.ReactElement {
  const [request, setRequest] = useState("");
  const [focusedWindow, setFocusedWindow] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const input = inputRef.current;
    if (!input) return;
    const resize = () => {
      input.style.height = "0px";
      input.style.height = `${input.scrollHeight}px`;
    };
    resize();
    let width = input.getBoundingClientRect().width;
    const observer = new ResizeObserver(() => {
      const nextWidth = input.getBoundingClientRect().width;
      if (nextWidth !== width) { width = nextWidth; resize(); }
    });
    observer.observe(input);
    return () => observer.disconnect();
  }, [request, selectedSwarmId, focusedWindow]);
  const [commandOpen, setCommandOpen] = useState(false);
  const [hiddenAgents, setHiddenAgents] = useState<string[]>([]);
  useEffect(() => {
    setFocusedWindow(null);
    setHiddenAgents([]);
  }, [selectedSwarmId]);
  const selectedSwarm = swarms.find((swarm) => String(swarm.swarm_id) === selectedSwarmId);
  const swarmMode = Boolean(selectedSwarmId && (selectedSwarm || demoActive));
  const status = String(swarmDetail?.status ?? selectedSwarm?.status ?? "created");
  const members = swarmAgents.filter((agent) => String(agent.agent_id ?? "") !== primaryAgentId);
  const events = traceEvents(swarmTrace);
  const leaderId = String(swarmDetail?.leader_agent_id ?? selectedSwarm?.leader_agent_id ?? primaryAgentId ?? "");
  const primaryEvents = events.filter((event) => !event.agent_id || event.agent_id === primaryAgentId || event.agent_id === leaderId);
  const visibleMembers = members.filter((agent) => !hiddenAgents.includes(String(agent.agent_id)));
  const filteredCommands = filterCommands(commands ?? [], request);

  function submit(event: React.FormEvent): void {
    event.preventDefault();
    const value = request.trim();
    if (!value) return;
    if (value.startsWith("/")) void onExecuteCommand(value);
    else onSubmitWork(value);
    setRequest("");
  }

  function toggleFocus(id: string): void {
    setFocusedWindow((current) => current === id ? null : id);
  }

  return (
    <section className={`workspace-panel ${swarmMode ? "workspace-panel--swarm" : ""}`} aria-label="Workspace" role="dialog" aria-modal="false">
      {!swarmMode ? <header className="workspace-panel-header">
        <span className="workspace-eyebrow"><i /> WORKSPACE CLI</span>
        <div className="workspace-panel-actions">
          <button type="button" onClick={onRefresh} disabled={loading} aria-label="Atualizar workspace">↻</button>
          <button type="button" onClick={onClose} aria-label="Fechar workspace">×</button>
        </div>
      </header> : null}
      <div className="workspace-panel-body">
        {swarms.length > 0 && !demoActive ? <div className="workspace-swarm-switcher">
          <label htmlFor="workspace-swarm-select">Swarm</label>
          <select id="workspace-swarm-select" value={selectedSwarmId ?? ""} onChange={(event) => event.target.value && onSelectSwarm(event.target.value)}>
            <option value="">Selecionar execução</option>
            {swarms.map((swarm) => <option key={String(swarm.swarm_id)} value={String(swarm.swarm_id)}>
              {String(swarm.mission_id ?? swarm.swarm_id)} · {String(swarm.status ?? "created")}
            </option>)}
          </select>
        </div> : null}
        {demoActive ? <div className="workspace-demo-indicator">SIMULAÇÃO VISUAL · sem execução de agentes</div> : null}
        {hiddenAgents.length > 0 && swarmMode ? <div className="workspace-hidden-agents" aria-label="Janelas ocultas">
          {members.filter((agent) => hiddenAgents.includes(String(agent.agent_id))).map((agent) => <button key={String(agent.agent_id)} type="button" onClick={() => setHiddenAgents((current) => current.filter((id) => id !== agent.agent_id))}>
            Mostrar {String(agent.display_name ?? agent.agent_id)}
          </button>)}
        </div> : null}
        <div className={`workspace-terminal-grid ${swarmMode ? "workspace-terminal-grid--swarm" : "workspace-terminal-grid--solo"} ${focusedWindow ? "workspace-terminal-grid--focused" : ""}`}>
          {(focusedWindow === null || focusedWindow === "primary") ? <article className={`workspace-terminal-window workspace-terminal-window--primary ${focusedWindow === "primary" ? "workspace-terminal-window--focused" : ""}`} aria-label={`Terminal de ${agentName}`}>
            {swarmMode ? <header className="workspace-window-header">
              <div className="workspace-window-identity"><i /><div><strong>1 · {agentName}</strong><small>{status} · {modelName || "modelo não configurado"}</small></div></div>
              <div className="workspace-window-actions">
                <button type="button" onClick={() => toggleFocus("primary")} aria-label={focusedWindow === "primary" ? "Restaurar grade" : `Expandir ${agentName}`}>{focusedWindow === "primary" ? "▣" : "□"}</button>
                <button type="button" onClick={onRefresh} disabled={loading || demoActive} aria-label="Atualizar swarm">↻</button>
                <button type="button" onClick={onClose} aria-label="Fechar workspace">×</button>
              </div>
            </header> : null}
            <div className="workspace-window-screen">
              {!swarmMode ? <div className="workspace-terminal-intro">
                <div>Synapse Workspace CLI <span>v0.1.0</span></div>
                <div>Agente ativo: <strong>{agentName}</strong></div>
                <div>Modelo: <strong>{modelName || "não configurado"}</strong></div>
              </div> : null}
              {swarmMode ? <div className="workspace-window-meta">synapse@swarm:~$ <span>{demoActive ? "demonstração" : String(selectedSwarm?.mission_id ?? "execução em andamento")}</span></div> : null}
              {primaryEvents.length > 0 ? <div className="workspace-event-lines" aria-label="Eventos do agente principal">
                {primaryEvents.slice(-40).map((item, index) => <div key={String(item.id ?? index)}>{eventLine(item)}</div>)}
              </div> : null}
              {commandOutput.length > 0 ? <div className="workspace-command-output" aria-live="polite">
                {commandOutput.map((entry, index) => <div key={`${entry.input}-${index}`}><div className="workspace-command-echo"><b>synapse</b>@workspace:~$ {entry.input}</div><div className="workspace-command-result">{entry.output}</div></div>)}
              </div> : null}
              {swarmConfirmation ? (
                <SwarmConfirmationCard
                  request={swarmConfirmation}
                  busy={swarmConfirmationBusy}
                  onResolve={onResolveSwarmConfirmation}
                />
              ) : null}
              {swarmResult && swarmMode ? <pre className="workspace-result-text">{JSON.stringify(swarmResult, null, 2)}</pre> : null}
              <form className="workspace-command-form" onSubmit={submit}>
                <span className="workspace-prompt"><b>synapse</b>@{swarmMode ? "swarm" : "workspace"}:~$</span>
                <div className="workspace-command-input-wrap">
                  {commandOpen && request.startsWith("/") && filteredCommands.length > 0 ? <div className="workspace-command-discovery" role="listbox">
                    {filteredCommands.map((command) => <button type="button" key={command.tool_id} onMouseDown={(event) => event.preventDefault()} onClick={() => { setRequest(`/${command.tool_id} `); setCommandOpen(false); }}>
                      <b>/{command.tool_id}</b><small>{command.description}</small>
                    </button>)}
                  </div> : null}
                  <textarea ref={inputRef} rows={1} value={request}
                    onFocus={() => setCommandOpen(request.startsWith("/"))}
                    onChange={(event) => { setRequest(event.target.value); setCommandOpen(event.target.value.startsWith("/")); }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                        event.preventDefault();
                        event.currentTarget.form?.requestSubmit();
                      }
                    }}
                    placeholder="Digite um comando ou tarefa…" aria-label="Workspace command" />
                </div>
                <button type="submit" disabled={!request.trim()} aria-label="Executar comando">↵</button>
              </form>
            </div>
          </article> : null}
          {swarmMode && !focusedWindow && members.length === 0 ? <p className="workspace-state">Carregando agentes desta execução…</p> : null}
          {swarmMode && visibleMembers.map((agent, index) => {
            const id = String(agent.agent_id ?? `agent-${index}`);
            if (focusedWindow && focusedWindow !== id) return null;
            const name = String(agent.display_name ?? id);
            const agentEvents = events.filter((event) => event.agent_id === id).slice(-40);
            return <article className={`workspace-terminal-window workspace-terminal-window--member workspace-terminal-window--color-${index % 6} ${focusedWindow === id ? "workspace-terminal-window--focused" : ""}`} key={id} aria-label={`Terminal de ${name}`}>
              <header className="workspace-window-header">
                <div className="workspace-window-identity"><i /><div><strong>{index + 2} · {name}</strong><small>{status} · {String(agent.preferred_model ?? "modelo não definido")}</small></div></div>
                <div className="workspace-window-actions">
                  <button type="button" onClick={() => toggleFocus(id)} aria-label={focusedWindow === id ? "Restaurar grade" : `Expandir ${name}`}>{focusedWindow === id ? "▣" : "□"}</button>
                  <button type="button" onClick={() => { setFocusedWindow(null); setHiddenAgents((current) => [...current, id]); }} aria-label={`Ocultar ${name}`}>×</button>
                </div>
              </header>
              <div className="workspace-window-screen">
                <div className="workspace-window-meta">synapse@swarm:~$ <span>{demoActive ? "tarefa simulada" : `agente ${id}`}</span></div>
                {agentEvents.length > 0 ? <div className="workspace-event-lines">{agentEvents.map((item, eventIndex) => <div key={String(item.id ?? eventIndex)}>{eventLine(item)}</div>)}</div>
                  : <p className="workspace-window-idle">Aguardando eventos deste agente.</p>}
                {(swarmTools[id] ?? []).length > 0 ? <div className="workspace-window-tools">Ferramentas: {swarmTools[id].join(", ")}</div> : null}
                <div className="workspace-window-cursor" aria-hidden="true">synapse@swarm:~$ ▌</div>
              </div>
            </article>;
          })}
        </div>
        {error ? <p className="workspace-state error">{error}</p> : null}
        {loading ? <p className="workspace-state">Carregando workspace…</p> : null}
        {swarmMode && !demoActive && selectedSwarmId && status !== "completed" && status !== "cancelled" ? <div className="workspace-swarm-controls">
          <span>Execução: {status}</span>
          {status === "created" ? <button type="button" onClick={() => onSwarmAction(selectedSwarmId, "start")}>Iniciar</button> : null}
          {status === "running" ? <button type="button" onClick={() => onSwarmAction(selectedSwarmId, "pause")}>Pausar</button> : null}
          {status === "paused" ? <button type="button" onClick={() => onSwarmAction(selectedSwarmId, "resume")}>Retomar</button> : null}
        </div> : null}
        {showProjects ? <div className="workspace-project-results">
          <div className="workspace-section-heading"><span>Projetos</span><small>{projects.length}</small></div>
          {projects.length === 0 && !loading ? <p className="workspace-state">Nenhum projeto registrado.</p> : null}
          {projects.map((project) => <button type="button" key={project.project_id} className={`workspace-project ${activeProjectId === project.project_id ? "active" : ""}`} onClick={() => onSelectProject(project.project_id)}>
            <strong>{project.name || project.project_id}</strong><small>{project.project_id} · {project.status || "active"}</small>
          </button>)}
          {activeProjectId ? <button type="button" className="workspace-action" onClick={onOpenFiles}>Arquivos do projeto atual</button> : null}
        </div> : null}
      </div>
    </section>
  );
}
