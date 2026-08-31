# Audio Backend

`AudioRuntime` owns audio content and hardware boundaries. It validates bytes by
container signature, decodes with PyAV, normalizes to mono PCM16 at 16 kHz, and
calculates duration, SHA-256, RMS, peak, and silence ratio. STT and TTS execution
belong to `SpeechAdapterRuntime`, not this runtime.

Supported containers are WAV PCM, WebM/Opus, and OGG/Opus. Empty, truncated,
unsupported, MIME-mismatched, too-short, oversized, over-duration, and optionally
silent inputs return structured validation errors. Client MIME and blob size are
never treated as authoritative duration.

`DeviceRuntime` uses PortAudio through `sounddevice`. Discovery returns stable
descriptors derived from backend, host API, name, direction, and channel count.
Input diagnostics open a real capture, count frames, and report RMS, peak,
clipping, and silence. Output diagnostics play a low-volume controlled tone.
Missing hardware is `unavailable` and does not prevent backend startup.

Production never creates mock devices. Hardware controllers are injected only
in tests. The backend never changes the operating-system default device.
