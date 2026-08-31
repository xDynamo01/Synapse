# ADR 0108 — Conversational Voice Loop

## Status

Implemented as an opt-in alpha loop. Text chat and one-shot microphone capture remain unchanged.

## Decision

Continuous conversation is controlled by the frontend because microphone capture and user consent belong to the WebView. A lightweight amplitude detector segments speech locally. Each completed utterance is sent to one atomic backend operation, `POST /api/voice/conversation/turn`.

The endpoint composes existing runtimes instead of adding another runtime:

1. `AudioRuntime` resolves the configured STT adapter and invokes Faster-Whisper.
2. `PerceptionRuntime` records the objective transcript and speech features.
3. `ChatRuntime.local_chat` performs model selection, conversation persistence, agent context loading, memory persistence, and the LLM request.
4. `ContextFusionRuntime` builds a persisted snapshot after the turn, when both the speech signal and conversation messages exist.
5. The response contains a TTS placeholder only. It never plays audio.

The frontend `ConversationLoop` owns these states: `idle`, `listening`, `recording`, `processing`, `responding`, and `error`. It uses `getUserMedia({ audio: true })`, Web Audio amplitude samples, and one second of silence as the turn boundary. Continuous mode is a separate explicit button beside one-shot capture and can be stopped at any time.

## Existing modules: real versus placeholder

| Module | Current use in the loop |
| --- | --- |
| AudioRuntime / SpeechAdapterRuntime | Real STT execution through Faster-Whisper |
| PerceptionRuntime | Real speech signal and `SpeechFeatures` persistence |
| ChatRuntime | Real LLM request, conversation history persistence, agent context and memory paths |
| ContextFusionRuntime | Real post-turn fused snapshot; it is not itself an LLM executor |
| SpeechPipelineRuntime | Existing session/turn model is currently mock-oriented and is not forced into the real path |
| VoiceRuntime | Real settings/provider/model resolution |
| TTS | Placeholder metadata and technical log only |
| Vision / camera | Not connected |

## Consequences

- Activation and every captured turn require an explicit user action to start the loop.
- VAD is deliberately simple and dependency-free; threshold tuning may be required for noisy rooms.
- Network or STT failures return the loop to listening while exposing an actionable error.
- No audio is retained by this feature beyond the existing backend transcription handling.
- A future stage may move real input/output turns into `SpeechPipelineRuntime` after it supports non-mock adapters without duplicating AudioRuntime.
