import React, { useEffect, useRef, useState } from "react";
import type { SynapseFrontendClient } from "../shared/frontendClient";
import type { MoMConfiguration, MoMOperation, MoMRoute, SettingsSnapshot } from "../shared/types";

export const momOperations: Array<{ id: MoMOperation; label: string; description: string }> = [
  { id: "conversation", label: "Modelo de conversa", description: "Conversa cotidiana; sem seleção usa o generalista." },
  { id: "coding", label: "Modelo de código", description: "Geração e análise de código." },
  { id: "reasoning", label: "Modelo de raciocínio", description: "Problemas que exigem análise e planejamento." },
  { id: "review", label: "Modelo de revisão", description: "Revisão de propostas e resultados." },
  { id: "summary", label: "Modelo de resumo", description: "Síntese de textos e informações." }
];

type Option = { value: string; label: string; disabled?: boolean };
type SelectProps = { label: string; value: string; options: Option[]; disabled?: boolean; onChange: (value: string) => void };
export const routeKey = (route: Pick<MoMRoute, "provider" | "model">): string => JSON.stringify([route.provider, route.model]);

export function momModelChoices(snapshot: SettingsSnapshot): Option[] {
  const choices = new Map<string, Option>();
  for (const model of snapshot.models.catalog) {
    const provider = snapshot.models.providers.find((item) => item.provider_id === model.provider);
    const setting = snapshot.models.provider_settings.find((item) => item.provider_id === model.provider);
    if (!model.chat_usable || model.provider === "lmstudio_local" || !provider) continue;
    const disabled = model.status === "unavailable" || setting?.enabled === false;
    const value = routeKey({ provider: model.provider, model: model.name });
    choices.set(value, { value, label: `${model.name} · ${provider.display_name}${disabled ? " · indisponível" : ""}`, disabled });
  }
  return [...choices.values()];
}

export function MoMSettings({ client, snapshot, primaryId, workspaceId, Select }: {
  client?: SynapseFrontendClient; snapshot: SettingsSnapshot | null; primaryId?: string;
  workspaceId: string; Select: React.ComponentType<SelectProps>;
}): React.ReactElement {
  const [configuration, setConfiguration] = useState<MoMConfiguration | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "saving" | "error">("loading");
  const [message, setMessage] = useState("");
  const [reload, setReload] = useState(0);
  const generation = useRef(0);
  useEffect(() => {
    generation.current += 1;
    let active = true;
    setStatus("loading"); setConfiguration(null); setMessage("");
    if (!client) { setStatus("error"); setMessage("Conecte ao backend para configurar o MoM."); return; }
    void client.momConfiguration(workspaceId).then((saved) => {
      if (active) { setConfiguration(saved); setStatus("ready"); }
    }).catch(() => {
      if (active) { setStatus("error"); setMessage("Não foi possível carregar o MoM. Confira o backend e tente recarregar."); }
    });
    return () => { active = false; generation.current += 1; };
  }, [client, workspaceId, primaryId, snapshot, reload]);
  const choices = snapshot ? momModelChoices(snapshot) : [];
  const busy = status === "loading" || status === "saving";
  const stalePrimary = Boolean(configuration && primaryId && configuration.primary_agent_id !== primaryId);

  function choose(operation: MoMOperation, value: string): void {
    if (!configuration) return;
    const routes = configuration.routes.filter((route) => route.operation !== operation);
    // Resolve against the catalog, never infer a provider from the displayed label.
    const model = snapshot?.models.catalog.find((item) => routeKey({ provider: item.provider, model: item.name }) === value);
    if (model) routes.push({ operation, provider: model.provider, model: model.name });
    setConfiguration({ ...configuration, routes }); setMessage("");
  }

  async function save(): Promise<void> {
    if (!client || !configuration || status !== "ready") return;
    if (configuration.routes.some((route) =>
      !choices.some((option) => option.value === routeKey(route) && !option.disabled))) {
      setMessage("Remova ou substitua as escolhas indisponíveis."); return;
    }
    setStatus("saving"); setMessage("");
    const admittedGeneration = generation.current;
    try {
      const saved = await client.saveMoMConfiguration({ workspace_id: workspaceId, enabled: true,
        resource_policy: configuration.resource_policy ?? "RESPONSIVE",
        routes: configuration.routes, expected_revision: configuration.revision });
      if (generation.current !== admittedGeneration) return;
      setConfiguration(saved); setStatus("ready"); setMessage("Configuração do MoM salva.");
      window.dispatchEvent(new Event("synapse-mom-changed"));
    } catch {
      if (generation.current !== admittedGeneration) return;
      setStatus("error");
      setMessage("Não foi possível confirmar o salvamento. Recarregue para conferir o estado salvo antes de tentar novamente.");
    }
  }

  return <section className="settings-card mom-settings" aria-label="Configurações MoM">
    <header className="mom-heading">
      <h3>MoM</h3>
      <span className="muted">Roteamento sempre disponível</span>
    </header>
    {status === "loading" ? <p role="status">Carregando configuração…</p> : null}
    {message ? <p role="status" className={status === "error" ? "settings-state error" : "settings-state"}>{message}</p> : null}
    {stalePrimary ? <p className="settings-state">O Primary mudou. Salvar vinculará estas escolhas ao Primary atual.</p> : null}
    {configuration ? <>
      <div className="mom-grid">
      {momOperations.map((operation) => {
        const route = configuration.routes.find((item) => item.operation === operation.id);
        const value = route ? routeKey(route) : "";
        const missing = route && !choices.some((option) => option.value === value);
        return <div className="mom-operation" key={operation.id}>
          <span className="mom-route-state">{missing || (route && choices.find((option) => option.value === value)?.disabled) ? "Indisponível" : route ? "Configurado" : "Sem modelo"}</span>
          <Select label={operation.label.replace("Modelo de ", "").replace(/^./, (letter) => letter.toUpperCase())} value={value} disabled={status !== "ready" || !snapshot}
            options={[{ value: "", label: "Não configurado" }, ...choices,
              ...(missing ? [{ value, label: `${route.model} · ${route.provider} · fora do catálogo`, disabled: true }] : [])]}
            onChange={(selected) => choose(operation.id, selected)} />
        </div>;
      })}
      </div>
    </> : null}
    <footer className="settings-footer">
      <button type="button" disabled={busy} onClick={() => setReload((value) => value + 1)}>Recarregar MoM</button>
      <button type="button" disabled={status !== "ready" || !snapshot || !primaryId} onClick={() => void save()}>
        {status === "saving" ? "Salvando…" : "Salvar MoM"}
      </button>
    </footer>
  </section>;
}
