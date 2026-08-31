# Perception, Multimodal, and Vision

The local perceptual pipeline is:

`authorized source -> Perception ingest -> observation -> optional multimodal fusion -> Context Fusion`

For visual inputs, capture and interpretation remain separate:

`explicit image/screenshot/camera frame -> CaptureRuntime -> VisionProvider -> PerceptionRuntime`

All stages work offline. Optional semantic vision, OCR, and camera providers
advertise health/capabilities independently. Perception records evidence and
uncertainty; it does not create World State, run an agent loop, or choose an
action. See the backend Perception, Vision, Multimodal, and Visual Privacy
documents for contracts and policy.

## Factual authority and taxonomy

Perception owns perceptual artifacts, not conversational meaning. Every newly
ingested durable signal is classified as one of four closed kinds:

- `raw_observation`: a sensor/provider measurement with no derived meaning;
- `derived_feature`: a deterministic or measurable transformation whose input
  identities remain in `input_references`/`lineage`;
- `model_inference`: a probabilistic or heuristic output with explicit provider,
  model, model version, provenance, and provider-supplied confidence when one
  exists;
- `contextual_interpretation`: only a reference to an externally owned
  interpretation. It requires both the external owner and reference. Perception
  does not become the reasoning authority.

Generic `type` and `values` do not override this classification. In particular,
emotion and engagement are not raw face/body facts. Temporal correlation and
multimodal aggregation preserve the original input identities and do not imply
semantic inference.

Durable artifacts preserve source, occurrence range, provenance, sensitivity,
retention class, policy/version fields, and causal/input references when
available. Raw deterministic measurements do not need a fabricated confidence.

## Retention and privacy

`transient_only` covers live buffers such as PCM, VAD frames, and default camera
frames. `policy_persistable` covers permitted metadata, features, observations,
inferences, and correlation records. `raw_media_explicit_only` covers microphone
audio, screenshots, and camera frames and is never enabled by default.

With `persist_raw_visual: false`, decoded image bytes are held only in a process
temporary directory and no raw payload is written under `vision/raw`. When the
policy explicitly enables raw visual persistence, the input records sensitivity,
expiry, retention class, checksum, and capture provenance. Existing historical
media is not deleted or reclassified by this behavior.

Voice remains authoritative for voice sessions, utterances, turn-taking,
barge-in, STT, and TTS lifecycle. Perception may consume VAD/activity facts and
derive acoustic features. Context Fusion only reads facts, features, inferences,
and their lineage; Conversation/Agents retain contextual reasoning authority.

## Local non-verbal producers

The Slice 9 acoustic producer is `synapse_local_dsp`, algorithm version
`prosody-v1`. It operates on canonical mono PCM in memory and persists only
derived artifacts. It reports normalized RMS energy, normalized peak amplitude,
silence ratio, utterance/speech/unvoiced duration in milliseconds, voiced ratio,
pause count and duration, voiced-segment rate, median F0, and F0 range.

Analysis uses non-overlapping 20 ms frames, an RMS silence threshold of `0.01`,
and a minimum pause duration of 200 ms. `voiced_segment_rate` is measured in
voiced segments per second; it is not a word, syllable, or transcript-derived
rate. Pitch uses local deterministic autocorrelation over 60-400 Hz with a
minimum normalized correlation of 0.3. Frames that do not meet those criteria
remain unavailable; pitch is never replaced by zero and has no fabricated
confidence. Thresholds are explicitly configurable through
`AcousticAnalysisConfig`.

VAD and speech-start/speech-end remain Voice-owned facts. Perception consumes
their identities and occurrence time but does not own session or turn-taking
lifecycle. Acoustic aggregation produces measurements only and cannot emit
psychological labels.

### Capability matrix

| Capability | Status | Implementation |
| --- | --- | --- |
| Acoustic features | supported | local deterministic DSP |
| Pitch | supported | local autocorrelation DSP |
| Pause analysis | supported | thresholded frame energy |
| Speech rate | supported | voiced segments/second only |
| Face detection | not configured | no operational detector present |
| Head pose | unavailable | no implementation present |
| Gaze | unavailable | no implementation present |
| Body pose | unavailable | no implementation present |
| Gesture | unavailable | no implementation present |

The existing local image provider validates files, dimensions, and checksums; it
is not a face or non-verbal inference provider. No camera is activated, no model
is downloaded, raw audio/frame persistence remains disabled by default, and no
external processing or egress is introduced. Slice 10 may add explicitly
configured real providers without weakening the inference rules above.
