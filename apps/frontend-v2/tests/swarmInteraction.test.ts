import { describe, expect, it } from "vitest";
import { pendingSwarmConfirmation } from "../src/shared/swarmInteraction";
import type { ConversationMessage, SwarmInteractionRequest } from "../src/shared/types";

function message(status: string): ConversationMessage {
  const request: SwarmInteractionRequest = {
    request_id: "request-1",
    conversation_id: "conversation-1",
    workspace_id: "default",
    project_id: null,
    session_id: null,
    task: "Use um Swarm",
    requested_agents: null,
    recommended_agents: 3,
    explicit_models: [],
    status,
    mission_id: null,
    swarm_id: null,
    execution_status: null
  };
  return {
    message_id: `message-${status}`,
    conversation_id: "conversation-1",
    sender_agent_id: "artemis",
    receiver_agent_id: "local_chat",
    role: "assistant",
    status: "completed",
    payload: { body: "Swarm", interaction: { type: "swarm_confirmation", request } }
  };
}

describe("persisted Swarm confirmation", () => {
  it("restores a pending confirmation from conversation history", () => {
    expect(pendingSwarmConfirmation([message("pending")])?.request_id).toBe("request-1");
  });

  it("clears the card after the persisted decision is completed or cancelled", () => {
    expect(pendingSwarmConfirmation([message("pending"), message("completed")])).toBeNull();
    expect(pendingSwarmConfirmation([message("pending"), message("cancelled")])).toBeNull();
  });
});
