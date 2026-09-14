import React, { useEffect, useRef, useState } from "react";
import type { SynapseFrontendClient } from "../shared/frontendClient";
import type { MoMConfiguration } from "../shared/types";

export function MoMToggle({ client, workspaceId, onBusy }: {
  client: SynapseFrontendClient; workspaceId: string; onBusy: (busy: boolean) => void;
}): React.ReactElement {
  const [configuration, setConfiguration] = useState<MoMConfiguration | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const lock = useRef(false);
  useEffect(() => {
    let active = true;
    const reload = () => {
      if (lock.current) return;
      void client.momConfiguration(workspaceId).then((saved) => {
        if (active) { setConfiguration(saved); setError(""); }
      }).catch(() => { if (active) { setConfiguration(null); setError("MoM indisponível. Clique para recarregar."); } });
    };
    reload();
    window.addEventListener("synapse-mom-changed", reload);
    window.addEventListener("focus", reload);
    return () => { active = false; window.removeEventListener("synapse-mom-changed", reload); window.removeEventListener("focus", reload); };
  }, [client, workspaceId]);

  async function toggle(): Promise<void> {
    if (lock.current) return;
    lock.current = true; setPending(true); onBusy(true); setError("");
    try {
      // Read back on every action; the settings panel or another window may have saved.
      const current = await client.momConfiguration(workspaceId);
      if (!configuration) { setConfiguration(current); return; }
      if (!current.enabled && !current.routes.some((route) => route.operation !== "conversation")) {
        setConfiguration(current); setError("Configure um especialista em Settings > MoM antes de ativar."); return;
      }
      const saved = await client.saveMoMConfiguration({ workspace_id: workspaceId,
        enabled: !current.enabled, routes: current.routes, expected_revision: current.revision });
      setConfiguration(saved);
    } catch {
      setConfiguration(null);
      setError("Não foi possível confirmar o MoM. Clique para recarregar antes de tentar novamente.");
    } finally { lock.current = false; setPending(false); onBusy(false); }
  }

  return <div className="composer-modes">
    <button className="composer-action composer-mom" type="button" aria-pressed={configuration?.enabled ?? false} disabled={pending}
      aria-label={pending ? "Salvando MoM" : configuration ? `MoM ${configuration.enabled ? "ligado" : "desligado"}` : "Recarregar MoM"}
      title={`${configuration?.enabled ? "MoM ligado" : "MoM desligado"} — especialistas sob demanda. Clique para alternar. Pode aumentar o tempo de resposta.`}
      onClick={() => void toggle()}>
      <span className="brain-icon" aria-hidden="true" />
      <span className="sr-only">{pending ? "Salvando…" : configuration ? `MoM ${configuration.enabled ? "ligado" : "desligado"}` : "Recarregar MoM"}</span>
    </button>
    {error ? <span className="mom-feedback" role="status">{error}</span> : null}
  </div>;
}
