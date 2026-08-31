# Speech Backend

`SpeechAdapterRuntime` is the single provider resolver for STT, TTS, and Voice
Analysis. Capabilities and health are provider-specific; no generic voice
provider chooses between incompatible operations.

## Providers

- Faster Whisper: local STT, lazy model loading, configurable model/device/compute
  type, real segments and timestamps, null confidence when unavailable, and
  `no_speech_detected` for empty results. Streaming and cancellation are false.
- Piper: local executable and model configured under DATA_DIR or environment.
  It produces validated WAV output. Streaming, pitch, speed, and post-completion
  cancellation are not claimed by the implemented path.
- Local Acoustic Analysis: duration, RMS, peak, silence duration/ratio, and
  speech duration. Pitch, emotion, personality, intent, and prosody are null or
  absent because no real model provides them.
- WebRTC VAD: PCM16 frames of 10, 20, or 30 ms with speech lifecycle events.
  Confidence is null because WebRTC VAD returns a binary decision.

Mock adapters are registered only when `SYNAPSE_DEV_MODE=true`. They are absent
from production selection, API, commands, health defaults, and OpenAPI.
