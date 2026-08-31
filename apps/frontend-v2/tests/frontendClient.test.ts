import { describe, expect, it, vi } from "vitest";
import { consumeNdjson, SynapseFrontendClient, SynapseClientError } from "../src/shared/frontendClient";

function jsonResponse(payload: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init
  });
}

describe("SynapseFrontendClient", () => {
  it("centralizes bootstrap, first-agent and conversation endpoints", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
      calls.push(String(input));
      return jsonResponse({ schema: "ok" });
    });
    const client = new SynapseFrontendClient("http://127.0.0.1:8717");

    await client.bootstrap();
    await client.createFirstAgent({
      agent_id: "synapse",
      display_name: "Synapse",
      role: "primary_agent",
      workspace_id: "default",
      default_provider: "mock",
      default_model: "synapse-test"
    });
    await client.openConversation({ workspace_id: "default" });
    await client.commandCatalog();
    await client.projects();
    await client.project("backend");
    await client.submitTextTurn("conversation-1", { content: "hello", workspace_id: "default" });
    await client.cancelTextTurn("conversation-1", { workspace_id: "default", idempotency_key: "turn-1" });
    await client.stageAttachment("conversation-1", {
      filename: "note.txt",
      mime_type: "text/plain",
      size: 5,
      content_base64: "aGVsbG8=",
      workspace_id: "default"
    });
    await client.transcribeVoice({ audio_base64: "UklGRg==", audio_format: "audio/wav", workspace_id: "default" });
    await client.voiceConversationTurn({
      audio_base64: "UklGRg==",
      audio_format: "audio/wav",
      workspace_id: "default",
      conversation_id: "conversation-1"
    });
    await client.history("conversation-1", { workspace_id: "default" });
    await client.deleteConversation("conversation-1", { workspace_id: "default", confirmed: true });
    await client.clearConversationHistory({ workspace_id: "default", confirmed: true });
    await client.notifications();
    await client.markNotificationRead("notification-1");
    await client.dismissNotification("notification-1");

    expect(calls).toEqual([
      "http://127.0.0.1:8717/api/frontend/bootstrap",
      "http://127.0.0.1:8717/api/frontend/first-agent",
      "http://127.0.0.1:8717/api/frontend/conversations/open",
      "http://127.0.0.1:8717/api/tools/catalog",
      "http://127.0.0.1:8717/api/projects",
      "http://127.0.0.1:8717/api/projects/backend",
      "http://127.0.0.1:8717/api/frontend/conversations/conversation-1/turns",
      "http://127.0.0.1:8717/api/frontend/conversations/conversation-1/turns/cancel",
      "http://127.0.0.1:8717/api/frontend/conversations/conversation-1/attachments/stage",
      "http://127.0.0.1:8717/api/frontend/voice/transcriptions",
      "http://127.0.0.1:8717/api/frontend/voice/conversation-turn",
      "http://127.0.0.1:8717/api/frontend/conversations/conversation-1/history?workspace_id=default",
      "http://127.0.0.1:8717/api/frontend/conversations/conversation-1?workspace_id=default&confirmed=true",
      "http://127.0.0.1:8717/api/frontend/conversations?workspace_id=default&confirmed=true",
      "http://127.0.0.1:8717/api/notifications",
      "http://127.0.0.1:8717/api/notifications/notification-1/read",
      "http://127.0.0.1:8717/api/notifications/notification-1"
    ]);
  });

  it("parses progressive NDJSON stream events", async () => {
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('{"schema":"frontend-v2-text-stream-event-v1","type":"turn_started","conversation_id":"c","workspace_id":"default","project_id":null,"session_id":null}\n'));
        controller.enqueue(new TextEncoder().encode('{"schema":"frontend-v2-text-stream-event-v1","type":"chunk_received","conversation_id":"c","workspace_id":"default","project_id":null,"session_id":null,"content":"hello"}\n'));
        controller.close();
      }
    });
    vi.stubGlobal("fetch", async () => new Response(stream, { status: 200 }));
    const client = new SynapseFrontendClient("http://127.0.0.1:8717");
    const events: string[] = [];

    await client.streamTextTurn("c", { content: "hello", workspace_id: "default" }, (event) => {
      events.push(event.type);
    });

    expect(events).toEqual(["turn_started", "chunk_received"]);
  });

  it("keeps stream chunks ordered through completion", async () => {
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('{"schema":"frontend-v2-text-stream-event-v1","type":"chunk_received","conversation_id":"c","workspace_id":"default","project_id":null,"session_id":null,"content":"a"}\n'));
        controller.enqueue(new TextEncoder().encode('{"schema":"frontend-v2-text-stream-event-v1","type":"chunk_received","conversation_id":"c","workspace_id":"default","project_id":null,"session_id":null,"content":"b"}\n'));
        controller.enqueue(new TextEncoder().encode('{"schema":"frontend-v2-text-stream-event-v1","type":"generation_completed","conversation_id":"c","workspace_id":"default","project_id":null,"session_id":null}\n'));
        controller.close();
      }
    });
    vi.stubGlobal("fetch", async () => new Response(stream, { status: 200 }));
    const client = new SynapseFrontendClient("http://127.0.0.1:8717");
    const events: string[] = [];

    await client.streamTextTurn("c", { content: "hello", workspace_id: "default" }, (streamEvent) => {
      events.push(`${streamEvent.type}:${streamEvent.content ?? ""}`);
    });

    expect(events).toEqual(["chunk_received:a", "chunk_received:b", "generation_completed:"]);
  });

  it("preserves frontend-safe backend errors", async () => {
    vi.stubGlobal("fetch", async () => jsonResponse({ detail: "boom" }, { status: 503 }));
    const client = new SynapseFrontendClient("http://127.0.0.1:8717");

    await expect(client.bootstrap()).rejects.toBeInstanceOf(SynapseClientError);
  });

  it("releases stream reader lock after interrupted stream", async () => {
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('{"schema":"frontend-v2-text-stream-event-v1","type":"chunk_received","conversation_id":"c","workspace_id":"default","project_id":null,"session_id":null,"content":"a"}\n'));
        controller.error(new TypeError("network"));
      }
    });
    vi.stubGlobal("fetch", async () => new Response(stream, { status: 200 }));
    const client = new SynapseFrontendClient("http://127.0.0.1:8717");

    await expect(
      client.streamTextTurn("c", { content: "hello", workspace_id: "default" }, () => undefined)
    ).rejects.toBeInstanceOf(TypeError);
    expect(stream.locked).toBe(false);
  });
});

describe("consumeNdjson", () => {
  it("keeps incomplete trailing data for later chunks", () => {
    const events: string[] = [];
    const remainder = consumeNdjson(
      '{"schema":"frontend-v2-text-stream-event-v1","type":"turn_started","conversation_id":"c","workspace_id":"default","project_id":null,"session_id":null}\n{"schema"',
      (event) => events.push(event.type)
    );

    expect(events).toEqual(["turn_started"]);
    expect(remainder).toBe('{"schema"');
  });
});
