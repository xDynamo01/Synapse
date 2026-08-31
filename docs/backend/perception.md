# Perception Runtime

`PerceptionRuntime` is the canonical local ingestion boundary for voice, audio,
vision, screen, camera, system, interaction, and multimodal signals. It validates
source, modality, timestamp, confidence, sensitivity, serialized size, and
retention before persistence. Accepted signals create separate structured
observations; exact duplicates return the existing signal and never create a
second observation.

Signals and observations live under `DATA_DIR/perception/` as metadata records.
Transcript text is omitted or redacted unless policy explicitly permits it.
Confidence is never defaulted to 1. Relevance uses documented linear recency
decay from 1 to 0 over one hour. Observation validity is capped by the earlier
of signal expiry and observation retention. Cleanup supports dry-run and is
idempotent.

The Voice bridge implements the existing `VoicePerceptionSink` protocol and
uses `ingest_signal`; it stores no raw audio. Context Fusion consumes active
observations, including provenance, sensitivity, confidence, relevance, and
validity, rather than reconstructing context from raw provider payloads.
