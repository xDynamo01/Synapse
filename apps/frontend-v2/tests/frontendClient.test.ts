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
  it("saves personality through the agent owner and previews the selected voice without saving it", async () => {
    const requests: Array<{ url: string; method?: string; body: unknown }> = [];
    vi.stubGlobal("fetch", async (input: RequestInfo | URL, init: RequestInit) => {
      requests.push({ url: String(input), method: init.method, body: JSON.parse(String(init.body)) });
      return jsonResponse(String(input).endsWith("synthesize")
        ? { audio_base64: "UklGRg==", audio_format: "audio/wav" }
        : { updated: true, status: "applied" });
    });
    const client = new SynapseFrontendClient("http://127.0.0.1:8717");
    await client.updatePersonality("artemis", " Aurora ", " Responda em português. ");
    const result = await client.previewVoice("Eu sou Aurora.", "cadu", "piper", "pt-BR");
    expect(requests).toEqual([
      { url: "http://127.0.0.1:8717/api/agents/artemis", method: "PATCH", body: { display_name: "Aurora", system_prompt: "Responda em português." } },
      { url: "http://127.0.0.1:8717/api/audio/synthesize", method: "POST", body: { text: "Eu sou Aurora.", voice_id: "cadu", provider_id: "piper", language: "pt-BR" } }
    ]);
    expect(result.audio_base64).toBe("UklGRg==");
  });

  it("loads personalization from the current primary agent when settings opens without an agent id", async () => {
    const calls: string[] = [];
    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
      const url = String(input);
      calls.push(url);
      if (url.endsWith("/api/frontend/bootstrap")) {
        return jsonResponse({
          schema: "frontend-v2-bootstrap-v1",
          primary_agent: { agent_id: "synapse", name: "Synapse", role: "primary_agent", kind: "persistent" }
        });
      }
      if (url.endsWith("/api/agents/synapse")) {
        return jsonResponse({
          agent_id: "synapse",
          display_name: "Aurora",
          system_prompt: "Responda sem emojis."
        });
      }
      return jsonResponse([]);
    });
    const client = new SynapseFrontendClient("http://127.0.0.1:8717");

    const snapshot = await client.settingsSnapshot();

    expect(snapshot.personalization).toEqual({
      agent_id: "synapse",
      display_name: "Aurora",
      system_prompt: "Responda sem emojis."
    });
    expect(calls).toContain("http://127.0.0.1:8717/api/frontend/bootstrap");
    expect(calls).toContain("http://127.0.0.1:8717/api/agents/synapse");
  });

  it("does not report pending personalization as saved or empty speech as playable", async () => {
    vi.stubGlobal("fetch", async () => jsonResponse({ updated: false, status: "awaiting_approval" }));
    const client = new SynapseFrontendClient("http://127.0.0.1:8717");
    await expect(client.updatePersonality("a", "Aurora", "Direct")).rejects.toThrow("not applied");
    vi.stubGlobal("fetch", async () => jsonResponse({ audio_base64: null }));
    await expect(client.previewVoice("Eu sou Aurora.", "cadu", "piper", "pt-BR")).rejects.toThrow("playable audio");
  });

  it("reads local and LM Studio telemetry from the provider routes", async () => {
    const calls: string[] = [];
    const telemetry = { recent: [{ raw_line: "prompt eval time = 452.88 ms" }] };
    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
      calls.push(String(input));
      return jsonResponse({ telemetry });
    });
    const client = new SynapseFrontendClient("http://127.0.0.1:8717");
    expect((await client.synapseLocalStatus("DeepSeek Q4_K_M")).telemetry).toEqual(telemetry);
    await client.lmstudioStatus();
    expect(calls).toEqual([
      "http://127.0.0.1:8717/api/providers/synapse-local/status?model=DeepSeek%20Q4_K_M",
      "http://127.0.0.1:8717/api/providers/lmstudio/status"
    ]);
  });

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
    await client.projectKnowledgeDocuments("backend", "default");
    await client.reindexProjectKnowledgeDocument("document-1", "default");
    await client.removeProjectKnowledgeDocument("document-1", "default");
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
      "http://127.0.0.1:8717/api/project-knowledge/documents?project_id=backend&workspace_id=default",
      "http://127.0.0.1:8717/api/project-knowledge/documents/document-1/reindex",
      "http://127.0.0.1:8717/api/project-knowledge/documents/document-1/remove",
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
  it("delivers fragmented voice text separately from the final voice result", async () => {
    const finalResult = { conversation_id: "c", status: "completed", transcript: "oi" };
    const encoded = new TextEncoder().encode(
      JSON.stringify({ type: "chunk_received", content: "Olá" }) + "\n" +
      JSON.stringify({ type: "generation_completed", content: JSON.stringify(finalResult) }) + "\n"
    );
    const stream = new ReadableStream({ start(controller) {
      for (const byte of encoded) controller.enqueue(new Uint8Array([byte]));
      controller.close();
    } });
    const abort = new AbortController();
    const fetchMock = vi.fn(async () => new Response(stream));
    vi.stubGlobal("fetch", fetchMock);
    const chunks: string[] = [];
    const client = new SynapseFrontendClient("http://127.0.0.1:8717");
    const result = await client.voiceConversationTurn({
      audio_base64: "AA==", audio_format: "wav", workspace_id: "default", conversation_id: "c"
    }, (text) => chunks.push(text), abort.signal);
    expect(chunks).toEqual(["Olá"]);
    expect(result).toEqual(finalResult);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8717/api/frontend/voice/conversation-turn/stream",
      expect.objectContaining({ signal: abort.signal })
    );
    expect(stream.locked).toBe(false);
  });

  it("rejects an incomplete voice response instead of reporting success", async () => {
    vi.stubGlobal("fetch", async () => new Response('{"type":"chunk_received","content":"partial"}\n'));
    const client = new SynapseFrontendClient("http://127.0.0.1:8717");
    await expect(client.voiceConversationTurn({
      audio_base64: "AA==", audio_format: "wav", workspace_id: "default", conversation_id: "c"
    }, () => undefined)).rejects.toThrow("before completion");
  });

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
