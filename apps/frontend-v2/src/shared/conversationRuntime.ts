import { SynapseClientError } from "./frontendClient.js";
import type {
  ConversationMessage,
  ConversationRuntimeState,
  FrontendConversationError,
  TextStreamEvent
} from "./types.js";

export interface ConversationRuntimeSnapshot {
  status: ConversationRuntimeState;
  messages: ConversationMessage[];
  partialAssistant: string;
  error: FrontendConversationError | null;
  lastDraft: string;
}

export function emptyConversationRuntime(): ConversationRuntimeSnapshot {
  return {
    status: "idle",
    messages: [],
    partialAssistant: "",
    error: null,
    lastDraft: ""
  };
}

export function beginTurn(
  snapshot: ConversationRuntimeSnapshot,
  userMessage: ConversationMessage,
  draft: string
): ConversationRuntimeSnapshot {
  return {
    ...snapshot,
    status: "sending",
    messages: mergeMessages(snapshot.messages, [userMessage]),
    partialAssistant: "",
    error: null,
    lastDraft: draft
  };
}

export function applyStreamEvent(
  snapshot: ConversationRuntimeSnapshot,
  event: TextStreamEvent
): ConversationRuntimeSnapshot {
  if (event.type === "confirmation_required" || event.type === "swarm_started") {
    return { ...snapshot, status: "streaming", error: null };
  }
  if (event.type === "turn_started" || event.type === "generation_started") {
    return { ...snapshot, status: "streaming", error: null };
  }
  if (event.type === "chunk_received") {
    return {
      ...snapshot,
      status: "streaming",
      partialAssistant: `${snapshot.partialAssistant}${event.content ?? ""}`,
      error: null
    };
  }
  if (event.type === "generation_completed") {
    return { ...snapshot, status: "completed", error: null };
  }
  if (event.type === "generation_cancelled") {
    return {
      ...snapshot,
      status: "cancelled",
      error: {
        code: "stream_interrupted",
        message: "Generation was cancelled before completion.",
        retryable: true
      }
    };
  }
  return {
    ...snapshot,
    status: "failed",
    error: {
      code: "generation_failed",
      message: event.error?.message ?? "The backend reported a generation failure.",
      retryable: true
    }
  };
}

export function markCancelled(snapshot: ConversationRuntimeSnapshot): ConversationRuntimeSnapshot {
  return {
    ...snapshot,
    status: "cancelled",
    error: {
      code: "stream_interrupted",
      message: "Generation was cancelled before completion.",
      retryable: true
    }
  };
}

export function prependOlderHistory(
  snapshot: ConversationRuntimeSnapshot,
  olderMessages: ConversationMessage[]
): ConversationRuntimeSnapshot {
  return {
    ...snapshot,
    messages: mergeMessages(olderMessages, snapshot.messages)
  };
}

export function reconcileHistory(
  snapshot: ConversationRuntimeSnapshot,
  historyMessages: ConversationMessage[],
  options: { completed: boolean }
): ConversationRuntimeSnapshot {
  return {
    ...snapshot,
    status: options.completed ? "completed" : snapshot.status,
    messages: historyMessages.length > 0 ? mergeMessages([], historyMessages) : snapshot.messages,
    partialAssistant: options.completed ? "" : snapshot.partialAssistant,
    error: options.completed ? null : snapshot.error
  };
}

export function interruptedStream(snapshot: ConversationRuntimeSnapshot, error: unknown): ConversationRuntimeSnapshot {
  return {
    ...snapshot,
    status: isDisconnectedError(error) ? "disconnected" : "failed",
    error: normalizeConversationError(error, "stream_interrupted")
  };
}

export function restoreFailed(snapshot: ConversationRuntimeSnapshot, error: unknown): ConversationRuntimeSnapshot {
  return {
    ...snapshot,
    status: "failed",
    error: normalizeConversationError(error, "history_restore_failure")
  };
}

export function mergeMessages(
  current: ConversationMessage[],
  incoming: ConversationMessage[]
): ConversationMessage[] {
  const byId = new Map<string, ConversationMessage>();
  for (const message of [...current, ...incoming]) {
    byId.set(messageIdentity(message), message);
  }
  return Array.from(byId.values()).sort(compareMessages);
}

export function messageIdentity(message: ConversationMessage): string {
  return message.message_id || `${message.conversation_id}:${message.role}:${message.created_at ?? ""}:${message.payload.body ?? ""}`;
}

export function normalizeConversationError(
  error: unknown,
  fallback: FrontendConversationError["code"] = "unknown"
): FrontendConversationError {
  if (error instanceof DOMException && error.name === "AbortError") {
    return { code: "stream_interrupted", message: "The stream was interrupted before completion.", retryable: true };
  }
  if (error instanceof SynapseClientError) {
    return {
      code: codeFromBackendError(error),
      message: error.message,
      retryable: error.status >= 500 || error.status === 0 || error.status === 409
    };
  }
  if (error instanceof TypeError) {
    return { code: "network_disconnected", message: "Backend connection was interrupted.", retryable: true };
  }
  if (error instanceof Error) {
    return { code: fallback, message: error.message, retryable: true };
  }
  return { code: fallback, message: "Conversation failed with an unknown error.", retryable: true };
}

function codeFromBackendError(error: SynapseClientError): FrontendConversationError["code"] {
  const text = `${error.message} ${JSON.stringify(error.details)}`.toLowerCase();
  if (error.status === 404 || text.includes("conversation")) {
    return "invalid_conversation";
  }
  if (error.status === 409 || text.includes("scope")) {
    return "scope_mismatch";
  }
  if (error.status >= 500 || error.status === 503) {
    return "backend_unavailable";
  }
  return "unknown";
}

function isDisconnectedError(error: unknown): boolean {
  return error instanceof TypeError || (error instanceof SynapseClientError && error.status >= 500);
}

function compareMessages(left: ConversationMessage, right: ConversationMessage): number {
  const leftTime = left.created_at ?? left.updated_at ?? "";
  const rightTime = right.created_at ?? right.updated_at ?? "";
  if (leftTime !== rightTime) {
    return leftTime.localeCompare(rightTime);
  }
  return messageIdentity(left).localeCompare(messageIdentity(right));
}
