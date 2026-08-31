# ADR 0078: Provider Plugin Runtime

## Status

Accepted.

## Context

Synapse has Provider Runtime and speech/audio/vision contracts, but those layers should not know how future external implementations are packaged, installed, enabled, or disabled. Without a plugin catalog, integrations such as faster-whisper, Piper, Kokoro, MediaPipe, or OpenCV would risk leaking installation and adapter concerns into core runtimes.

## Decision

Introduce `ProviderPluginRuntime` as a local-first catalog for provider plugin manifests and install state.

The runtime manages:

- `ProviderPluginManifest`
- `ProviderPluginInstallState`
- `ProviderPluginHealth`
- `ProviderPluginSummary`

Plugin manifests are persisted under:

```text
DATA_DIR/provider_plugins/manifests/
```

Local install/enable state is persisted under:

```text
DATA_DIR/provider_plugins/states/
```

Policy lives in:

```text
DATA_DIR/config/provider_plugin_policy.yaml
```

The seed manifests are placeholders for future integrations:

- `faster_whisper_plugin`
- `piper_plugin`
- `kokoro_plugin`
- `mediapipe_plugin`
- `opencv_plugin`

They do not import, install, download, or execute any provider code.

## Boundaries

Provider Runtime answers which provider can implement a capability.

Provider Plugin Runtime answers which local plugin package could provide adapters/providers and whether that plugin is installed, enabled, disabled, incompatible, or unavailable.

This runtime does not:

- install packages
- import plugin modules
- execute providers
- download models
- access microphone, camera, GPU, network, or speech engines
- create a marketplace

## Consequences

Future provider work can attach real install/load behavior behind a stable manifest and policy model without changing speech, vision, or multimodal contracts.

The current health/readiness integration is diagnostic only. A not-installed seed plugin is expected and does not make the system unavailable by itself.
