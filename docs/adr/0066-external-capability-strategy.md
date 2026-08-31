# ADR 0066: External Capability Strategy

## Status

Accepted.

## Context

Synapse will need voice, vision, perception, search, model, and multimodal capabilities. These areas should not be implemented directly inside the core runtime. The core must orchestrate capabilities and enforce permissions, while specialized engines remain replaceable external providers.

## Decision

Introduce a provider foundation with:

- `ProviderManifest`
- `ProviderRegistry`
- `ProviderRuntime`
- `ProviderHealth`
- `CapabilityProvider`
- local provider policy in `DATA_DIR/config/provider_policy.yaml`

This stage registers only mock/unconfigured providers:

- `mock_stt`
- `mock_tts`
- `mock_vision`

They do not execute STT, TTS, camera, video, or network calls.

## Definitions

Core:
The Synapse runtime, policy, persistence, permissions, events, commands, and API. Core decides whether an agent may use a capability and which provider should be selected.

Adapter:
A thin translation layer between a provider-specific API and a Synapse provider contract.

Provider:
A registered implementation candidate for a capability. A provider has a manifest, health status, provider type, capability mapping, and policy constraints.

Plugin:
A future distributable package that may contain one or more adapters/providers plus metadata. Plugins are not implemented in this stage.

Capability Pack:
A future curated bundle of capabilities, provider manifests, policy defaults, and documentation. Capability packs are not implemented in this stage.

## Separation From Capability Runtime

Capability Runtime answers:

```text
Can this agent use this capability?
```

Provider Runtime answers:

```text
Which provider implements this capability?
```

These responsibilities stay separate. Provider selection does not grant agent authorization.

## Consequences

Benefits:

- The core remains independent from heavy libraries such as Whisper, Piper, MediaPipe, or OpenCV.
- Future multimodal systems can register providers without changing core policy semantics.
- Homelab deployments can prefer local providers and block network/GPU providers by policy.

Limitations:

- No real provider execution exists yet.
- Provider health is manifest/policy based and returns `unconfigured` for mocks.
- Dynamic plugin loading is intentionally out of scope.

## Future Strategy

Audio contracts, vision contracts, perception signals, and context fusion consume Provider Runtime rather than importing provider-specific libraries into core modules. Frontend visualization remains outside backend provider authority.
