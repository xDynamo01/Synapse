import React from "react";
import type { SwarmInteractionRequest } from "../shared/types";

export type SwarmConfirmationAction = "accept_recommended" | "keep_requested" | "cancel";

interface SwarmConfirmationCardProps {
  request: SwarmInteractionRequest;
  busy: boolean;
  onResolve: (action: SwarmConfirmationAction) => void;
}

export function SwarmConfirmationCard({
  request,
  busy,
  onResolve
}: SwarmConfirmationCardProps): React.ReactElement {
  const effectiveRequested = request.requested_agents === null
    ? null
    : Math.max(request.requested_agents, request.explicit_models.length);
  const canKeepRequested = effectiveRequested !== null
    && effectiveRequested < request.recommended_agents;

  return (
    <section className="swarm-confirmation-card" aria-label="Confirmar criação do Swarm">
      <div className="swarm-confirmation-heading">
        <span className="swarm-confirmation-mark" aria-hidden="true">◎</span>
        <div>
          <strong>Iniciar Swarm?</strong>
          <small>O agente principal recomenda {request.recommended_agents} agentes temporários.</small>
        </div>
      </div>
      <p>{request.task}</p>
      {request.explicit_models.length > 0 ? (
        <div className="swarm-confirmation-models">
          {request.explicit_models.map((model) => <span key={model}>{model}</span>)}
        </div>
      ) : null}
      <div className="swarm-confirmation-actions">
        <button type="button" disabled={busy} onClick={() => onResolve("accept_recommended")}>
          {busy ? "Preparando…" : `Iniciar com ${request.recommended_agents}`}
        </button>
        {canKeepRequested ? (
          <button type="button" className="secondary" disabled={busy} onClick={() => onResolve("keep_requested")}>
            Manter {effectiveRequested}
          </button>
        ) : null}
        <button type="button" className="quiet" disabled={busy} onClick={() => onResolve("cancel")}>
          Cancelar
        </button>
      </div>
    </section>
  );
}
