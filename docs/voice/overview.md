# Voice / Audio Foundation

This stage introduces the first local STT-oriented voice foundation for Synapse.
The first real provider is Faster-Whisper, wired through the existing Audio Runtime / Speech Adapter Runtime stack.

Speech results now include objective SpeechFeatures such as duration, segment count, pauses, silence ratio, timestamps, and provider metadata. These values are propagated to PerceptionRuntime and ContextFusionRuntime for future multimodal use, but they are not interpreted as emotion, stress, personality, or intent.

## Stored contracts

- `voice/settings.yaml` — selected provider, microphone, language, model preset, enabled flag
- `voice/recordings/{recording_id}.yaml` — persisted recording metadata
- `voice/recordings/{recording_id}.{audio_format}` — persisted audio blob

## Backend surface

- list voice settings
- update voice settings
- list microphone devices
- test a microphone device
- list STT-capable speech providers
- transcribe an uploaded audio payload into a structured transcript result
- create a manual recording
- list recordings
- fetch a recording
- attach a manual transcription to a recording

## Frontend surface

- Voice appears inside Settings as a collapsible section
- users can choose provider/device/language/model
- users can capture audio manually in Chat and send it to the backend for transcription
- users can save a recording and add a transcription later

## Explicit non-goals

- wake word
- live speech streaming
- TTS playback
- automatic agent voice execution
- voice chat loops
