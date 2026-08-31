# Model Recommendations

Status: **Implemented / Frozen**.

`ModelCapabilityRuntime` reads only the public ModelHub registry snapshot and a
`HardwareRuntime` snapshot. It never scans model folders, probes network services,
starts providers, or downloads models.

Recommendations are generated for chat, swarm, coding, vision, speech, reasoning,
and embedding. Candidates must be registered, available, attached to an online
registered provider, capability-compatible, and fit measured free RAM/VRAM.
Among fitting candidates the engine prefers task capability, the configured
route, and the largest fitting registered model. A VRAM reduction can therefore
move selection to a smaller model. CPU fallback is allowed only when the model's
registered capability says it is CPU-compatible.

With no fitting registered model the result is `unavailable`; no familiar model
name is invented or hardcoded. Model Router consumes this runtime directly and
does not inspect hardware.
