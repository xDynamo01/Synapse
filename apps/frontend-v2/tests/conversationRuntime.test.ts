import { describe, expect, it } from "vitest";
import {
  applyStreamEvent,
  beginTurn,
  emptyConversationRuntime,
  interruptedStream,
  markCancelled,
  mergeMessages,
  prependOlderHistory,
  reconcileHistory,
  restoreFailed
} from "../src/shared/conversationRuntime";
import type { ConversationMessage, TextStreamEvent } from "../src/shared/types";

function message(id: string, role: string, body: string, createdAt = id): ConversationMessage {
  return {
    message_id: id,
    conversation_id: "conversation-1",
    sender_agent_id: role,
    receiver_agent_id: role === "user" ? "assistant" : "user",
    role,
    status: "completed",
    payload: { body, role },
    created_at: createdAt
  };
}

function event(type: TextStreamEvent["type"], content?: string): TextStreamEvent {
  return {
    schema: "frontend-v2-text-stream-event-v1",
    type,
    conversation_id: "conversation-1",
    workspace_id: "default",
    project_id: null,
    session_id: null,
    content
  };
}

describe("conversation runtime resilience", () => {
  it("models a normal multi-chunk turn with explicit completion", () => {
    let snapshot = beginTurn(emptyConversationRuntime(), message("u1", "user", "hello"), "hello");
    expect(snapshot.status).toBe("sending");

    snapshot = applyStreamEvent(snapshot, event("turn_started"));
    snapshot = applyStreamEvent(snapshot, event("chunk_received", "hel"));
    snapshot = applyStreamEvent(snapshot, event("chunk_received", "lo"));
    snapshot = applyStreamEvent(snapshot, event("generation_completed"));

    expect(snapshot.status).toBe("completed");
    expect(snapshot.partialAssistant).toBe("hello");
  });

  it("keeps stream failure explicit and retryable", () => {
    const failed = applyStreamEvent(emptyConversationRuntime(), {
      ...event("generation_failed"),
      error: { code: "generation_failed", message: "model failed" }
    });

    expect(failed.status).toBe("failed");
    expect(failed.error).toEqual({ code: "generation_failed", message: "model failed", retryable: true });
  });

  it("keeps interactive Swarm events in the active stream instead of treating them as failures", () => {
    const confirming = applyStreamEvent(emptyConversationRuntime(), event("confirmation_required"));
    const started = applyStreamEvent(confirming, event("swarm_started"));

    expect(confirming.status).toBe("streaming");
    expect(confirming.error).toBeNull();
    expect(started.status).toBe("streaming");
    expect(started.error).toBeNull();
  });

  it("marks interrupted stream as disconnected without claiming completion", () => {
    const streaming = applyStreamEvent(emptyConversationRuntime(), event("chunk_received", "partial"));
    const interrupted = interruptedStream(streaming, new TypeError("network"));

    expect(interrupted.status).toBe("disconnected");
    expect(interrupted.partialAssistant).toBe("partial");
    expect(interrupted.error?.code).toBe("network_disconnected");
  });

  it("reconciles history without duplicate messages", () => {
    const optimistic = message("u1", "user", "hello");
    const assistant = message("a1", "assistant", "world", "u2");
    const snapshot = beginTurn(emptyConversationRuntime(), optimistic, "hello");
    const reconciled = reconcileHistory(snapshot, [optimistic, assistant, assistant], { completed: true });

    expect(reconciled.messages.map((item) => item.message_id)).toEqual(["u1", "a1"]);
    expect(reconciled.partialAssistant).toBe("");
  });

  it("replaces optimistic messages when authoritative history uses different ids", () => {
    const snapshot = emptyConversationRuntime();
    const optimistic = message("pending-1", "user", "oi");
    const persisted = message("msg-1", "user", "oi");
    const reconciled = reconcileHistory({ ...snapshot, messages: [optimistic] }, [persisted], { completed: true });
    expect(reconciled.messages).toEqual([persisted]);
  });

  it("preserves deterministic identity and order across multiple sequential turns", () => {
    const merged = mergeMessages(
      [message("u2", "user", "second", "2026-01-02"), message("u1", "user", "first", "2026-01-01")],
      [message("a1", "assistant", "answer", "2026-01-01T00:00:01")]
    );

    expect(merged.map((item) => item.message_id)).toEqual(["u1", "a1", "u2"]);
  });

  it("represents restore failure as frontend-safe history failure", () => {
    const restored = restoreFailed(emptyConversationRuntime(), new Error("history unavailable"));

    expect(restored.status).toBe("failed");
    expect(restored.error?.code).toBe("history_restore_failure");
    expect(restored.error?.message).toBe("history unavailable");
  });

  it("preserves order and avoids duplicates when older pages are prepended", () => {
    const current = {
      ...emptyConversationRuntime(),
      messages: [message("m3", "user", "current", "2026-01-03")]
    };
    const updated = prependOlderHistory(current, [
      message("m1", "user", "oldest", "2026-01-01"),
      message("m2", "assistant", "older", "2026-01-02"),
      message("m3", "user", "current", "2026-01-03")
    ]);

    expect(updated.messages.map((item) => item.message_id)).toEqual(["m1", "m2", "m3"]);
  });

  it("marks cancellation as incomplete and recoverable", () => {
    const cancelled = markCancelled(applyStreamEvent(emptyConversationRuntime(), event("chunk_received", "partial")));

    expect(cancelled.status).toBe("cancelled");
    expect(cancelled.partialAssistant).toBe("partial");
    expect(cancelled.error?.retryable).toBe(true);
  });
});
