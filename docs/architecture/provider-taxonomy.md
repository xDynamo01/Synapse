# Provider Taxonomy

Status: implemented as an internal discovery boundary; backend remains **NOT READY**.

## Canonical contract

`CanonicalProviderManifest` is the neutral cross-domain identity. It carries a
stable `provider_id`, domain, display name, version, implementation reference,
structured capabilities, availability, configuration descriptor, lifecycle
capabilities, health reference, locality/optionality, compatibility aliases and
redacted metadata. It has no generation, transcription, synthesis, vision,
capture, device or automation method.

Only domains with real implementations are admitted: model, speech-to-text,
text-to-speech, voice analysis, VAD, vision, capture, desktop automation, system
insight, notification and integration. `not_configured` is an availability state,
never a provider identity. OCR and Camera null objects therefore do not enter the
catalog.

`ProviderCapability` validates a namespaced ID plus supported state, mode,
constraints and metadata. Domain contracts remain richer and authoritative. The
base capability is a discovery claim, not permission to cast and execute.

Availability answers whether an implementation may be configured or used. Domain
health answers whether it works now. Readiness answers whether the feature can
operate. The catalog does not replace either HealthContributor or Readiness.

## Identity and compatibility

IDs are stable implementation identifiers, independent of class name, filesystem
path or registration order. Existing public IDs remain untouched. Model settings
IDs are canonical for discovery, while established execution IDs are explicit
compatibility aliases:

| Canonical discovery ID | Existing execution alias |
| --- | --- |
| `lmstudio_local` | `lmstudio` |
| `ollama_local` | `ollama` |
| `google_gemini` | `gemini` |

These aliases document the current boundary; they do not silently rewrite stored
settings or alter Model Router. A future public rename requires a domain-owned
migration.

Duplicate canonical IDs are rejected unless the repeated registration is exactly
idempotent. Capability selection by class name, substring, list position or an
unconfigured placeholder is forbidden.

## Catalog, registries and projections

`ProviderCatalog` owns discovery only: register, get, deterministic list, filters
by domain/capability/availability and availability projection. It does not load,
execute, persist settings, probe hardware or implement fallback.

Operational authorities remain unchanged:

- `ProviderRegistry` preserves the frozen generic public provider surface.
- `ModelRouter.adapters` and `ModelHubRegistry` remain model authorities.
- `SpeechAdapterRegistry` remains the speech execution authority.
- Vision, Capture, Desktop, Insight and Notification keep their domain ports and
  runtime-selected implementations.
- `ProviderPluginRegistry` describes integrations; a plugin is not itself promoted
  to an execution provider.

Bootstrap owns one catalog. Thin projections read the current owner descriptors;
they create no second settings system and no persisted copy. Model and speech
projections are registered in `ModelFeatureBuilder`; platform-selected projections
are completed in `IntegrationFeatureBuilder`, after their specialized runtimes
exist. Model Hub and System Insight receive the neutral discovery facade. Execution
continues through specialized registries and ports.

## Configuration, factories and lifecycle

`ProviderConfigurationDescriptor` describes schema version, domain/factory
validation mode and typed field metadata. Sensitive fields cannot carry defaults;
metadata rejects secret-like keys and absolute paths. Existing domain stores still
validate, apply and migrate configuration.

`ProviderFactory` establishes the common construction convention: explicit
`provider_id`, configuration validation and implementation creation. It contains no
execution signature and performs no global registration. Existing platform
factories remain explicit mappings wired by authorized runtimes/bootstrap; imports
do not start active resources.

Lifecycle flags are truthful description only: lazy load, warmup, unload, cancel,
streaming and reload. Passive providers declare none. The catalog never starts or
closes a provider; actual lifecycle stays with bootstrap and the owning runtime.

## Selection and fallback

Existing explicit desktop visual and system-insight platform fallbacks are
preserved. Their order and domain tests remain authoritative. Generic mock
manifests stay listed for frozen compatibility, but resolution rejects them unless
`SYNAPSE_DEV_MODE` or system mode `test`/`development` is explicit. Production
speech registration already follows the same rule. The canonical production
catalog never includes mock manifests.

## Preserved findings

Five historical identity conventions, four specialized registries, three concrete
platform factory families, seven prior capability representations, eight health
representations and seven settings-schema families remain in their owner domains.
The taxonomy supplies a coherent projection rather than flattening those contracts.
Storage, unrelated cycles, Agent Creator, DataDir maintenance, Tools, API, Commands,
Health/Readiness behavior, Context Fusion, SDK and frontend remain outside scope.
