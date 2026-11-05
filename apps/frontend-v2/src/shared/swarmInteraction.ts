import type { ConversationMessage, SwarmInteractionRequest } from "./types.js";

export function pendingSwarmConfirmation(
  messages: ConversationMessage[]
): SwarmInteractionRequest | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const interaction = messages[index]?.payload.interaction;
    if (!interaction || typeof interaction !== "object") continue;
    const request = (interaction as { request?: unknown }).request;
    if (!request || typeof request !== "object") continue;
    const candidate = request as Partial<SwarmInteractionRequest>;
    if (typeof candidate.request_id !== "string" || typeof candidate.status !== "string") continue;
    return candidate.status === "pending" ? candidate as SwarmInteractionRequest : null;
  }
  return null;
}
